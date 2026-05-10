"""
04 / 30% ESSENCE — 精华压缩引擎
=================================
将7本医学教材的整合知识图谱压缩至原始体量30%以内，保留核心精华。

Pipeline:
  1. load()              → 加载 merged_graph.json + merge_decisions.json
  2. filter_noise()      → 过滤编辑/版权/编委等非知识节点
  3. compute_tiers()     → 基于图中心性自动分级 (Tier 1-4)
  4. map_nodes_to_chunks() → 将每个知识节点映射到原始chunk文本
  5. deduplicate()       → 基于merge_decisions合并重复节点组
  6. summarize()         → 规则提取 + 可选Ollama摘要
  7. compress_output()   → 按分级保留策略输出精华Markdown
  8. generate_report()   → 统计报告 (压缩比、覆盖率等)

分级策略 (无教学大纲时的图结构代理):
  Tier 1 (核心, top 15%): PageRank+Degree综合得分最高 → 完整保留
  Tier 2 (重点, 15-50%): 中等重要 → 保留摘要+关键段落
  Tier 3 (了解, 50-85%): 一般重要 → 仅保留摘要
  Tier 4 (拓展, bottom 15%): 边缘知识 → 一行提及
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import networkx as nx
import numpy as np

# ─── 噪音模式 (复用 cross_textbook_merger 的规则) ────────────────────────────

NOISE_PATTERNS = [
    r'^第\s*\d*\s*版(\s*\d+)?$',
    r'^版权所有', r'^侵权必究',
    r'^编委', r'^主编', r'^副主编', r'^数字编委',
    r'^主审', r'^编写秘书',
    r'^序言$', r'^前言$', r'^目录$',
    r'^新形态教材', r'^读者信息反馈',
    r'^修订说明', r'^规划教材修订',
    r'^全国高等学校',
    r'^简介$', r'^简介',
    r'^图书在版编目', r'^CIP数据',
    r'^ISBN', r'^标准书号',
    r'^定价', r'^印张', r'^字数', r'^开本',
    r'^\d+$',
    r'^[\.\s·…]+$',
    r'^推荐阅读', r'^参考文献',
    r'^Page\s+\d+$',
    r'^\d+_\w+$',
    r'^第\s*[一二三四五六七八九十]+\s*章\s*$',
    r'^第\s*[一二三四五六七八九十]+\s*节\s*$',
    r'^主\s*编',
    r'^副主编',
    r'^编\s*委',
    r'^供基础.*专业用$',
    r'^💡',
    r'^第\s*\d+\s*版',           # "第 版 10"
    r'^\d+\.\d+',                # "1.1" 类编号
    r'^[A-Za-z\s]+$',            # 纯英文标签 (可能是英文书名)
    r'^\d{2,3}$',                # 纯页码 (如 "187")
    r'^.*出版社.*$',
    r'^\s*$',                    # 空白
    r'^.*医科大学.*$',           # 编委单位
    r'^.*医学院.*$',             # 编委单位
    r'^.*大学.*学院.*$',         # 编委单位 (如 "浙江大学医学院")
    r'^.*附属.*医院.*$',         # 编委单位
    r'^.*@.*$',                  # 邮箱
]

_noise_regex = re.compile('|'.join(f'({p})' for p in NOISE_PATTERNS))


def is_noise_node(label: str) -> bool:
    """判断节点是否为前导页/版权/编委等噪音"""
    label = label.strip()
    if len(label) < 3 or len(label) > 80:
        return True
    if _noise_regex.search(label):
        return True
    alpha_chars = sum(1 for c in label if c.isalpha() or '\u4e00' <= c <= '\u9fff')
    if alpha_chars / max(len(label), 1) < 0.3:
        return True
    # 过滤句子碎片（含过多标点无实质内容的短片段）
    if len(label) < 5 and alpha_chars < 3:
        return True
    # 过滤纯标点/特殊字符占比过高的
    if alpha_chars / max(len(label), 1) < 0.5 and len(label) < 10:
        return True
    # 过滤人名模式 (2-4个中文字符，可能带空格，如 "钱亦华" "丁 强")
    stripped = label.replace(' ', '').replace('\u3000', '')
    if 2 <= len(stripped) <= 4 and all('\u4e00' <= c <= '\u9fff' for c in stripped):
        # 排除明确是医学概念的短词
        MEDICAL_SHORT_TERMS = {'心脏', '肺', '肝', '肾', '胃', '肠', '脑', '皮肤', '血液', '神经',
                               '动脉', '静脉', '淋巴', '骨骼', '肌肉', '关节', '细胞', '组织',
                               '免疫', '炎症', '肿瘤', '感染', '代谢', '激素', '基因', '蛋白'}
        if stripped not in MEDICAL_SHORT_TERMS:
            return True
    return False


# ─── 数据模型 ──────────────────────────────────────────────────────────────

@dataclass
class EssenceNode:
    """精华版知识节点"""
    node_id: str
    label: str
    tier: int = 3                     # 1=核心, 2=重点, 3=了解, 4=拓展
    centrality_score: float = 0.0     # 综合中心性得分
    pagerank: float = 0.0
    degree: int = 0
    relations: list[dict] = field(default_factory=list)  # 关联边
    chunk_paths: list[str] = field(default_factory=list)  # 映射到的chunk路径
    chunk_contents: list[str] = field(default_factory=list)  # chunk原文
    summary: str = ""                 # 一句话摘要
    key_passages: list[str] = field(default_factory=list)  # 关键段落
    source_books: list[str] = field(default_factory=list)  # 来源教材
    dedup_group: list[str] = field(default_factory=list)   # 去重组内其他节点
    is_representative: bool = True    # 是否为去重后的代表节点

    def to_dict(self) -> dict:
        d = asdict(self)
        # 截断过长内容以便JSON序列化
        if len(d.get('chunk_contents', [])) > 0:
            d['chunk_content_preview'] = d['chunk_contents'][0][:200]
            del d['chunk_contents']
        return d


@dataclass
class EssenceReport:
    """精华压缩报告"""
    total_nodes_before: int = 0
    total_nodes_after_noise_filter: int = 0
    total_nodes_after_dedup: int = 0
    tier_distribution: dict = field(default_factory=lambda: {1: 0, 2: 0, 3: 0, 4: 0})
    original_chars: int = 0           # 原始chunks总字符数
    compressed_chars: int = 0         # 精华版总字符数
    compression_ratio: float = 0.0    # 压缩比
    core_coverage: float = 0.0        # 核心知识点覆盖率
    summarization_method: str = "rule_based"
    pipeline_duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ─── 主引擎 ────────────────────────────────────────────────────────────────

class EssenceCompressor:
    """精华压缩引擎"""

    def __init__(
        self,
        merged_graph_path: str = "生医黑客松/merged/merged_graph.json",
        merge_decisions_path: str = "生医黑客松/merged/merge_decisions.json",
        chunks_dir: str = "生医黑客松/chunks",
        search_engine=None,
        use_ollama: bool = False,
        ollama_model: str = "qwen2.5:3b",
    ):
        self.merged_graph_path = Path(merged_graph_path)
        self.merge_decisions_path = Path(merge_decisions_path)
        self.chunks_dir = Path(chunks_dir)
        self.search_engine = search_engine
        self.use_ollama = use_ollama
        self.ollama_model = ollama_model

        # 内部状态
        self.graph: nx.DiGraph = nx.DiGraph()
        self.nodes: dict[str, EssenceNode] = {}
        self.merge_decisions: list[dict] = []
        self.chunk_index: dict[str, str] = {}  # chunk_path → content
        self.report = EssenceReport()

    # ── Step 1: 加载 ──────────────────────────────────────────────────────

    def load(self) -> None:
        """加载合并图和合并决策"""
        t0 = time.time()

        # 加载 merged graph
        with open(self.merged_graph_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        nodes_list = data.get('nodes', [])
        edges_list = data.get('links', data.get('edges', []))

        self.report.total_nodes_before = len(nodes_list)

        for node in nodes_list:
            nid = node.get('id', node.get('label', ''))
            label = node.get('label', nid)
            self.graph.add_node(nid, label=label)

        for edge in edges_list:
            src = edge.get('source', '')
            tgt = edge.get('target', '')
            rel = edge.get('relation', edge.get('label', ''))
            if src and tgt:
                self.graph.add_edge(src, tgt, relation=rel,
                                    books=edge.get('books', []))

        print(f"[LOAD] {self.graph.number_of_nodes()} nodes, "
              f"{self.graph.number_of_edges()} edges")

        # 加载 merge decisions
        if self.merge_decisions_path.exists():
            with open(self.merge_decisions_path, 'r', encoding='utf-8') as f:
                decisions_data = json.load(f)
            if isinstance(decisions_data, list):
                self.merge_decisions = decisions_data
            elif isinstance(decisions_data, dict):
                self.merge_decisions = decisions_data.get('decisions', [])
            print(f"[LOAD] {len(self.merge_decisions)} merge decisions")

        # 构建 chunk 索引 (延迟加载，只为需要的节点加载)
        self._build_chunk_index()

        self.report.pipeline_duration_seconds = time.time() - t0

    def _build_chunk_index(self) -> None:
        """遍历chunks目录，建立路径→内容索引"""
        count = 0
        for root, dirs, files in os.walk(self.chunks_dir):
            for fname in files:
                if fname.endswith('.md'):
                    path = os.path.join(root, fname)
                    rel_path = os.path.relpath(path, self.chunks_dir)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if len(content.strip()) > 20:
                                self.chunk_index[rel_path] = content
                                count += 1
                    except Exception:
                        pass
        print(f"[INDEX] {count} chunks indexed ({sum(len(v) for v in self.chunk_index.values()):,} chars total)")
        self.report.original_chars = sum(len(v) for v in self.chunk_index.values())

    # ── Step 2: 噪音过滤 ──────────────────────────────────────────────────

    def filter_noise(self) -> None:
        """移除编辑/版权/编委等非知识节点"""
        noise_nodes = []
        for node_id in list(self.graph.nodes()):
            label = self.graph.nodes[node_id].get('label', node_id)
            if is_noise_node(label):
                noise_nodes.append(node_id)

        self.graph.remove_nodes_from(noise_nodes)
        self.report.total_nodes_after_noise_filter = self.graph.number_of_nodes()
        removed = self.report.total_nodes_before - self.report.total_nodes_after_noise_filter
        print(f"[FILTER] {removed} noise nodes removed "
              f"({removed/max(self.report.total_nodes_before,1)*100:.1f}%), "
              f"{self.graph.number_of_nodes()} nodes remain")

    # ── Step 3: 图分析自动分级 ─────────────────────────────────────────────

    def compute_tiers(self) -> None:
        """基于图中心性指标自动分级

        综合得分 = 0.5 * PageRank_zscore + 0.3 * Degree_zscore + 0.2 * Clustering_zscore
        百分位分界:
          Tier 1 (核心): top 15%
          Tier 2 (重点): 15%-50%
          Tier 3 (了解): 50%-85%
          Tier 4 (拓展): bottom 15%
        """
        n_nodes = self.graph.number_of_nodes()
        if n_nodes == 0:
            print("[TIER] Graph is empty, skipping tier computation")
            return

        # 计算 PageRank
        try:
            pagerank = nx.pagerank(self.graph, alpha=0.85, max_iter=200)
        except Exception:
            pagerank = {n: 1.0/n_nodes for n in self.graph.nodes()}

        # 计算度中心性 (入度+出度)
        degrees = {n: self.graph.degree(n) for n in self.graph.nodes()}

        # 计算聚类系数 (转为无向图)
        ug = self.graph.to_undirected()
        try:
            clustering = nx.clustering(ug)
        except Exception:
            clustering = {n: 0.0 for n in self.graph.nodes()}

        # Z-score 标准化
        pr_vals = np.array([pagerank[n] for n in self.graph.nodes()])
        deg_vals = np.array([degrees[n] for n in self.graph.nodes()])
        cls_vals = np.array([clustering[n] for n in self.graph.nodes()])

        def zscore(arr):
            std = np.std(arr)
            if std < 1e-10:
                return np.zeros_like(arr)
            return (arr - np.mean(arr)) / std

        z_pr = zscore(pr_vals)
        z_deg = zscore(deg_vals)
        z_cls = zscore(cls_vals)

        combined = 0.5 * z_pr + 0.3 * z_deg + 0.2 * z_cls

        # 百分位分级
        percentiles = np.percentile(combined, [20, 55, 85])

        node_ids = list(self.graph.nodes())
        for i, nid in enumerate(node_ids):
            score = float(combined[i])
            if score >= percentiles[2]:   # top 15%
                tier = 1
            elif score >= percentiles[1]:  # 15-50%
                tier = 2
            elif score >= percentiles[0]:  # 50-85%
                tier = 3
            else:                          # bottom 15%
                tier = 4

            # 获取关联关系
            relations = []
            for _, tgt, data in self.graph.out_edges(nid, data=True):
                relations.append({
                    'target': tgt,
                    'relation': data.get('relation', ''),
                    'books': data.get('books', []),
                })

            node = EssenceNode(
                node_id=nid,
                label=self.graph.nodes[nid].get('label', nid),
                tier=tier,
                centrality_score=score,
                pagerank=float(pagerank.get(nid, 0)),
                degree=int(degrees.get(nid, 0)),
                relations=relations,
            )
            self.nodes[nid] = node
            self.report.tier_distribution[tier] += 1

        print(f"[TIER] Tier distribution: "
              f"T1={self.report.tier_distribution[1]}, "
              f"T2={self.report.tier_distribution[2]}, "
              f"T3={self.report.tier_distribution[3]}, "
              f"T4={self.report.tier_distribution[4]}")

    # ── Step 4: Chunk 映射 ─────────────────────────────────────────────────

    def map_nodes_to_chunks(self, max_chunks_per_node: int = 3) -> None:
        """将每个知识节点映射到最相关的原始chunk文本

        优先使用 search_engine (FAISS语义搜索)，回退到子串匹配。
        """
        eligible_nodes = [n for n in self.nodes.values() if n.tier <= 2]
        others = [n for n in self.nodes.values() if n.tier > 2]

        # Tier 1-2 节点优先生成完整映射
        for node in eligible_nodes + others:
            matched = self._find_chunks_for_label(node.label, top_k=max_chunks_per_node)
            if matched:
                node.chunk_paths = [m['path'] for m in matched]
                node.chunk_contents = [m['content'] for m in matched]

        mapped_t1 = sum(1 for n in self.nodes.values()
                        if n.tier == 1 and n.chunk_contents)
        mapped_t2 = sum(1 for n in self.nodes.values()
                        if n.tier == 2 and n.chunk_contents)
        print(f"[MAP] Chunk mapping: T1={mapped_t1}/{self.report.tier_distribution[1]}, "
              f"T2={mapped_t2}/{self.report.tier_distribution[2]}")

    def _find_chunks_for_label(self, label: str, top_k: int = 3) -> list[dict]:
        """为节点标签查找最相关的chunk"""
        results = []

        # 方法1: FAISS 语义搜索
        if self.search_engine is not None:
            try:
                sr = self.search_engine.search(label, top_k=top_k)
                for r in sr:
                    path = r.get('path', '')
                    if path and os.path.exists(path):
                        rel_path = os.path.relpath(path, self.chunks_dir)
                    else:
                        rel_path = path
                    content = self.chunk_index.get(rel_path, '')
                    if not content:
                        try:
                            with open(path, 'r', encoding='utf-8') as f:
                                content = f.read()
                        except Exception:
                            content = ''
                    if content:
                        results.append({'path': rel_path, 'content': content,
                                        'score': r.get('score', 0)})
                if results:
                    return results
            except Exception as e:
                pass  # 回退到子串匹配

        # 方法2: 子串匹配回退
        clean_label = re.sub(r'[\d\s\|｜·…]+', '', label).strip()
        if len(clean_label) < 2:
            return []

        candidates = []
        for path, content in self.chunk_index.items():
            if clean_label in content:
                # 简单评分：匹配位置越靠前越好
                pos = content.find(clean_label)
                score = 1.0 - (pos / max(len(content), 1))
                candidates.append({'path': path, 'content': content, 'score': score})

        candidates.sort(key=lambda x: x['score'], reverse=True)
        return candidates[:top_k]

    # ── Step 5: 去重 ──────────────────────────────────────────────────────

    def deduplicate(self) -> None:
        """基于merge_decisions合并重复节点组

        每个去重组保留一个代表节点（内容最丰富的），其余标记为非代表。
        """
        # 从 merge_decisions 提取去重组
        dedup_groups: list[list[str]] = []
        for dec in self.merge_decisions:
            if dec.get('type') == 'merge' and dec.get('confidence', 0) >= 0.70:
                nodes = dec.get('nodes', [])
                # 过滤掉不存在的节点
                existing = [n for n in nodes if n in self.nodes]
                if len(existing) >= 2:
                    dedup_groups.append(existing)

        print(f"[DEDUP] {len(dedup_groups)} duplicate groups from merge decisions")

        # 去重：每组选一个代表
        removed_count = 0
        for group in dedup_groups:
            # 按 chunk 内容长度排序，选最丰富的为代表
            best = max(group, key=lambda nid: sum(
                len(c) for c in self.nodes.get(nid, EssenceNode(nid, nid)).chunk_contents
            ))
            for nid in group:
                if nid != best and nid in self.nodes:
                    self.nodes[nid].is_representative = False
                    self.nodes[nid].dedup_group = group
                    removed_count += 1

        # 同时将代表节点的去重组信息填入
        for group in dedup_groups:
            best = max(group, key=lambda nid: sum(
                len(c) for c in self.nodes.get(nid, EssenceNode(nid, nid)).chunk_contents
            ))
            if best in self.nodes:
                others = [n for n in group if n != best]
                self.nodes[best].dedup_group = others

        self.report.total_nodes_after_dedup = sum(
            1 for n in self.nodes.values() if n.is_representative
        )
        print(f"[DEDUP] {removed_count} duplicate nodes suppressed, "
              f"{self.report.total_nodes_after_dedup} representative nodes remain")

    # ── Step 6: 摘要生成 ──────────────────────────────────────────────────

    def summarize(self) -> None:
        """为每个代表性节点生成摘要

        Tier 1-2: 完整摘要 (规则提取 + 可选Ollama)
        Tier 3:   简短摘要 (规则提取)
        Tier 4:   一行提及
        """
        if self.use_ollama:
            method = "ollama"
            self._summarize_with_ollama()
        else:
            method = "rule_based"
            self._summarize_rule_based()

        self.report.summarization_method = method
        summarized = sum(1 for n in self.nodes.values()
                         if n.is_representative and n.summary)
        print(f"[SUMMARIZE] {summarized} nodes summarized ({method})")

    def _summarize_rule_based(self) -> None:
        """基于规则的摘要提取

        策略:
        - 提取chunk内容中与节点标签最相关的段落
        - 取首段前2-3句作为摘要
        - 提取含关键医学术语的句子作为关键段落
        """
        # 医学术语关键词（用于提取关键句）
        MEDICAL_KEYWORDS = {
            '动脉', '静脉', '神经', '血管', '淋巴', '心脏', '肺', '肝', '肾',
            '胃', '肠', '脑', '脊髓', '骨骼', '肌肉', '关节', '皮肤',
            '细胞', '组织', '器官', '系统', '功能', '结构', '解剖',
            '病理', '生理', '临床', '诊断', '治疗', '手术', '药物',
            '感染', '炎症', '肿瘤', '免疫', '代谢', '内分泌', '遗传',
            '综合征', '疾病', '症状', '体征', '检查', '影像',
        }

        for node in self.nodes.values():
            if not node.is_representative:
                continue

            texts = node.chunk_contents
            if not texts:
                # 无chunk映射：用节点标签作为摘要
                node.summary = node.label
                continue

            # 合并所有chunk内容
            combined = '\n'.join(texts)

            # 清理markdown标记
            clean = re.sub(r'#+ ', '', combined)
            clean = re.sub(r'\*+', '', clean)
            clean = re.sub(r'[│|]', '', clean)

            # 按句号、分号、换行分割句子
            sentences = re.split(r'[。；\n]', clean)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

            # 摘要：取第1句实质内容（跳过纯标题行），限制80字
            summary_parts = []
            for s in sentences:
                if len(s) > 8 and not s.startswith('图') and not s.startswith('表'):
                    summary_parts.append(s)
                if len(summary_parts) >= 1:
                    break
            raw = '。'.join(summary_parts) + '。' if summary_parts else node.label
            node.summary = raw[:80] + ('…' if len(raw) > 80 else '')

            # 关键段落：含医学关键词的句子（最多5句）
            key_sents = []
            for s in sentences:
                if any(kw in s for kw in MEDICAL_KEYWORDS):
                    key_sents.append(s)
                if len(key_sents) >= 5:
                    break
            node.key_passages = key_sents

            # Tier 4: 截断摘要为一行
            if node.tier == 4:
                node.summary = node.summary[:80] + ('...' if len(node.summary) > 80 else '')
                node.key_passages = []

    def _summarize_with_ollama(self) -> None:
        """使用本地 Ollama 模型生成摘要"""
        try:
            import subprocess
        except ImportError:
            print("[OLLAMA] subprocess not available, falling back to rule-based")
            self._summarize_rule_based()
            return

        for node in self.nodes.values():
            if not node.is_representative or node.tier == 4:
                continue

            texts = node.chunk_contents
            if not texts:
                node.summary = node.label
                continue

            combined = '\n'.join(texts)[:1500]  # 截断以控制token数

            if node.tier <= 2:
                prompt = (
                    f"请用一句话（不超过80字）总结以下医学教材文本的核心知识点。"
                    f"知识点：{node.label}\n\n原文：\n{combined}\n\n摘要："
                )
            else:
                prompt = (
                    f"用一句话概括：{node.label}\n{combined[:500]}\n摘要："
                )

            try:
                result = subprocess.run(
                    ['ollama', 'run', self.ollama_model, prompt],
                    capture_output=True, text=True, timeout=30,
                    encoding='utf-8', errors='replace',
                )
                if result.returncode == 0 and result.stdout.strip():
                    summary = result.stdout.strip()
                    # 限制长度
                    if node.tier <= 2:
                        node.summary = summary[:150]
                    else:
                        node.summary = summary[:100]
                else:
                    # 回退到规则
                    self._rule_summary_single(node)
            except Exception:
                self._rule_summary_single(node)

        # Tier 4 用规则
        for node in self.nodes.values():
            if node.tier == 4 and node.is_representative:
                self._rule_summary_single(node)

    def _rule_summary_single(self, node: EssenceNode) -> None:
        """单节点规则摘要（供 ollama 回退使用）"""
        texts = node.chunk_contents
        if not texts:
            node.summary = node.label
            return
        clean = re.sub(r'#+ |\*+|[│|]', '', '\n'.join(texts))
        sentences = [s.strip() for s in re.split(r'[。；\n]', clean) if len(s.strip()) > 5]
        parts = [s for s in sentences if len(s) > 8 and not s.startswith(('图', '表'))][:2]
        node.summary = '。'.join(parts) + '。' if parts else node.label
        if node.tier == 4:
            node.summary = node.summary[:80]

    # ── Step 7: 精华版输出 ─────────────────────────────────────────────────

    def compress_output(self, output_dir: str = "生医黑客松/essence") -> str:
        """按分级保留策略输出精华 Markdown

        Tier 1 (核心): 完整 chunk 内容 + 摘要
        Tier 2 (重点): 摘要 + 关键段落
        Tier 3 (了解): 仅摘要
        Tier 4 (拓展): 一行提及
        """
        output_dir = str(Path(output_dir))
        os.makedirs(output_dir, exist_ok=True)

        # 按 Tier 分组，组内按中心性得分降序
        tier_groups: dict[int, list[EssenceNode]] = {1: [], 2: [], 3: [], 4: []}
        for node in self.nodes.values():
            if node.is_representative:
                tier_groups[node.tier].append(node)

        for tier in [1, 2, 3, 4]:
            tier_groups[tier].sort(key=lambda n: n.centrality_score, reverse=True)

        # 生成 Markdown
        lines: list[str] = []
        lines.append("# 医学知识精华版 (30% ESSENCE)")
        lines.append("")
        lines.append(f"> 从7本临床医学教材中压缩提取的核心知识精华")
        lines.append(f"> 压缩比目标: ≤30% | 核心覆盖率: ≥95%")
        lines.append(f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> 摘要方法: {self.report.summarization_method}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 目录
        lines.append("## 目录")
        lines.append("")
        lines.append(f"- [Tier 1 · 核心知识](#tier-1-核心知识) ({tier_groups[1].__len__()} 条)")
        lines.append(f"- [Tier 2 · 重点知识](#tier-2-重点知识) ({tier_groups[2].__len__()} 条)")
        lines.append(f"- [Tier 3 · 了解知识](#tier-3-了解知识) ({tier_groups[3].__len__()} 条)")
        lines.append(f"- [Tier 4 · 拓展知识](#tier-4-拓展知识) ({tier_groups[4].__len__()} 条)")
        lines.append("")

        total_chars = 0

        for tier in [1, 2, 3, 4]:
            nodes = tier_groups[tier]
            tier_names = {1: "核心知识", 2: "重点知识", 3: "了解知识", 4: "拓展知识"}
            tier_icons = {1: "🔴", 2: "🟡", 3: "🟢", 4: "⚪"}

            lines.append("---")
            lines.append("")
            lines.append(f"## {tier_icons[tier]} Tier {tier} · {tier_names[tier]} ({len(nodes)}条)")
            lines.append("")

            # Tier 3-4: 紧凑列表格式，大幅减少开销
            if tier >= 3:
                for node in nodes:
                    lines.append(f"- **{node.label}**: {node.summary[:60]}")
                lines.append("")
                continue

            # Tier 1-2: 详细条目
            for i, node in enumerate(nodes, 1):
                # 节标题 (简化)
                lines.append(f"### {i}. {node.label}")
                lines.append("")

                # 摘要
                if node.summary:
                    lines.append(f"> {node.summary}")
                    lines.append("")

                # Tier 1: 关键原文摘录 (缩短到200字)
                if tier == 1 and node.chunk_contents:
                    lines.append("<details>")
                    lines.append("<summary>📖 原文摘录</summary>")
                    lines.append("")
                    content = node.chunk_contents[0][:300]
                    lines.append(content)
                    if len(node.chunk_contents[0]) > 300:
                        lines.append("")
                        lines.append("*(原文已截断)*")
                    lines.append("")
                    lines.append("</details>")
                    lines.append("")

                # Tier 2: 关键段落 (最多2条)
                if tier == 2 and node.key_passages:
                    for kp in node.key_passages[:2]:
                        lines.append(f"- {kp[:120]}")
                    lines.append("")

        # 统计总字符数
        content = '\n'.join(lines)
        self.report.compressed_chars = len(content)
        self.report.compression_ratio = (
            self.report.compressed_chars / max(self.report.original_chars, 1)
        )

        # 写入文件
        output_path = os.path.join(output_dir, "essence.md")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"[OUTPUT] Essence written to {output_path}")
        print(f"[OUTPUT] {len(content):,} chars "
              f"({self.report.compression_ratio*100:.1f}% of original {self.report.original_chars:,} chars)")

        return output_path

    # ── Step 8: 报告 ──────────────────────────────────────────────────────

    def generate_report(self, output_dir: str = "生医黑客松/essence") -> dict:
        """生成压缩统计报告"""
        output_dir = str(Path(output_dir))
        os.makedirs(output_dir, exist_ok=True)

        core_count = self.report.tier_distribution[1]
        total = sum(self.report.tier_distribution.values())
        self.report.core_coverage = core_count / max(total, 1)

        report_dict = self.report.to_dict()

        # 添加节点样例
        samples = {}
        for tier in [1, 2, 3, 4]:
            tier_nodes = [n for n in self.nodes.values()
                          if n.is_representative and n.tier == tier]
            tier_nodes.sort(key=lambda n: n.centrality_score, reverse=True)
            samples[f"tier_{tier}"] = [
                {
                    'label': n.label,
                    'score': round(n.centrality_score, 4),
                    'summary': n.summary[:100] if n.summary else '',
                }
                for n in tier_nodes[:5]
            ]

        report_dict['sample_nodes'] = samples

        report_path = os.path.join(output_dir, "essence_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)

        print(f"[REPORT] Report written to {report_path}")
        return report_dict

    # ── 全管线运行 ─────────────────────────────────────────────────────────

    def run(self, output_dir: str = "生医黑客松/essence") -> dict:
        """运行完整精华压缩管线"""
        t0 = time.time()

        print("=" * 60)
        print("04 / 30% ESSENCE — 精华压缩管线")
        print("=" * 60)

        print("\n[1/7] Loading merged graph & decisions...")
        self.load()

        print("\n[2/7] Filtering noise nodes...")
        self.filter_noise()

        print("\n[3/7] Computing centrality-based tiers...")
        self.compute_tiers()

        print("\n[4/7] Mapping nodes to chunks...")
        self.map_nodes_to_chunks()

        print("\n[5/7] Deduplicating merged nodes...")
        self.deduplicate()

        print("\n[6/7] Generating summaries...")
        self.summarize()

        print("\n[7/7] Compressing and outputting essence...")
        self.compress_output(output_dir)

        report = self.generate_report(output_dir)

        elapsed = time.time() - t0
        self.report.pipeline_duration_seconds = elapsed

        print("\n" + "=" * 60)
        print("COMPRESSION SUMMARY")
        print("=" * 60)
        print(f"  Original chars:    {self.report.original_chars:>10,}")
        print(f"  Compressed chars:  {self.report.compressed_chars:>10,}")
        print(f"  Compression ratio: {self.report.compression_ratio*100:>9.1f}%")
        print(f"  Nodes before:      {self.report.total_nodes_before:>10,}")
        print(f"  Nodes after dedup: {self.report.total_nodes_after_dedup:>10,}")
        print(f"  Tier 1 (core):     {self.report.tier_distribution[1]:>10,}")
        print(f"  Tier 2 (key):      {self.report.tier_distribution[2]:>10,}")
        print(f"  Tier 3 (general):  {self.report.tier_distribution[3]:>10,}")
        print(f"  Tier 4 (extended): {self.report.tier_distribution[4]:>10,}")
        print(f"  Duration:          {elapsed:>9.1f}s")
        print("=" * 60)

        return report


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='04 / 30% ESSENCE — 医学知识精华压缩引擎'
    )
    parser.add_argument('--merged-graph', default='生医黑客松/merged/merged_graph.json',
                        help='Merged graph JSON path')
    parser.add_argument('--merge-decisions', default='生医黑客松/merged/merge_decisions.json',
                        help='Merge decisions JSON path')
    parser.add_argument('--chunks-dir', default='生医黑客松/chunks',
                        help='Chunks directory')
    parser.add_argument('--output-dir', default='生医黑客松/essence',
                        help='Output directory for essence')
    parser.add_argument('--use-ollama', action='store_true',
                        help='Use local Ollama for summarization')
    parser.add_argument('--ollama-model', default='qwen2.5:3b',
                        help='Ollama model name')
    parser.add_argument('--index-prefix', default='medical_index',
                        help='FAISS index prefix for chunk mapping')
    args = parser.parse_args()

    # 尝试加载搜索引擎
    search_engine = None
    try:
        from search_engine import MedicalSearchEngine
        eng = MedicalSearchEngine()
        eng.load(args.index_prefix)
        search_engine = eng
        print("[INIT] FAISS search engine loaded for chunk mapping.")
    except Exception as e:
        print(f"[INIT] FAISS unavailable ({e}), using substring matching fallback.")

    compressor = EssenceCompressor(
        merged_graph_path=args.merged_graph,
        merge_decisions_path=args.merge_decisions,
        chunks_dir=args.chunks_dir,
        search_engine=search_engine,
        use_ollama=args.use_ollama,
        ollama_model=args.ollama_model,
    )

    compressor.run(output_dir=args.output_dir)


if __name__ == '__main__':
    main()
