"""
Cross-Textbook Knowledge Graph Merger (03 / CROSS-TEXTBOOK)
跨教材知识图谱合并引擎

Pipeline:
  1. load_all_books()      → 加载7本教材的 triples + graph
  2. filter_noise()        → 过滤前导页噪音节点
  3. entity_resolution()   → FAISS语义匹配 + 规则匹配 → 概念对齐
  4. merge_relations()     → 关系合并 + 冲突检测 + 互补发现
  5. verify_quality()      → 环路检测 + 孤立节点 + 置信度评分
  6. generate_outputs()    → 合并图 + 决策日志 + 冲突报告
"""

from __future__ import annotations

import json
import os
import re
import hashlib
import itertools
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import networkx as nx
import numpy as np

# ─── Data models ────────────────────────────────────────────────────────────

@dataclass
class MergeDecision:
    """一条整合决策记录"""
    decision_id: str
    type: str                     # merge | conflict | complement | gap
    nodes: list[str]              # 涉及的节点 ID 列表
    books: list[str]              # 涉及的教材
    confidence: float             # 0-1
    rationale: str                # 自然语言理由
    evidence: list[str] = field(default_factory=list)
    resolved: bool = False
    resolution: str = ""          # approved | rejected | modified

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MergeReport:
    """整合报告"""
    total_books: int = 0
    total_nodes_before: int = 0
    total_nodes_after: int = 0
    total_edges_before: int = 0
    total_edges_after: int = 0
    merge_count: int = 0
    conflict_count: int = 0
    complement_count: int = 0
    dedup_ratio: float = 0.0
    decisions: list[MergeDecision] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["decisions"] = [dec.to_dict() for dec in self.decisions]
        return d


# ─── Noise filter ───────────────────────────────────────────────────────────

NOISE_PATTERNS = [
    r'^第\s*\d*\s*版(\s*\d+)?$',          # "第 版 10"
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
    r'^\d+$',                              # 纯数字
    r'^[\.\s·…]+$',                        # 纯标点
    r'^.*\.{3,}.*$',                       # 含省略号（TOC导引符）
    r'^推荐阅读', r'^参考文献',
    r'^Page\s+\d+$',
    r'^\d+_\w+$',                          # book_id patterns
    r'^第\s*[一二三四五六七八九十]+\s*章\s*$',
    r'^第\s*[一二三四五六七八九十]+\s*节\s*$',
]

_noise_regex = re.compile('|'.join(f'({p})' for p in NOISE_PATTERNS))


def is_noise_node(label: str) -> bool:
    """判断节点是否为前导页噪音"""
    label = label.strip()
    if len(label) < 2 or len(label) > 80:
        return True
    if _noise_regex.match(label):
        return True
    # 如果 label 以特殊字符为主
    alpha_chars = sum(1 for c in label if c.isalpha() or '\u4e00' <= c <= '\u9fff')
    if alpha_chars / max(len(label), 1) < 0.3:
        return True
    return False


# ─── Main merger ─────────────────────────────────────────────────────────────

# ─── LLM 二分类判定器 ──────────────────────────────────────────────────

class LLMBinaryClassifier:
    """使用本地 Ollama 对概念对进行二分类，判断是否为同一医学概念。

    替代纯 FAISS 阈值判定，消除烟测报告中发现的假阳性问题
    （如 "局部解剖学" ↔ "淋巴" FAISS 0.755 被误判为候选合并对）。
    """

    PROMPT = """你是一位医学知识审核员。判断以下两个概念是否为**同一医学知识点**（可用同一术语概括）。

概念 A: {label_a}
概念 B: {label_b}

来源教材: {book_a} ↔ {book_b}

判断标准:
- "同一": 两个概念本质相同，仅措辞不同（如 "心室收缩期" ≈ "心脏收缩期"）→ 回答 YES
- "不同": 两个概念属于不同医学范畴（如 "淋巴" ≠ "局部解剖学"）→ 回答 NO
- 只回答 YES 或 NO，然后一行简短理由

你的判断:"""

    def __init__(self, cache_dir: str = "生医黑客松/.llm_classify_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._call_count = 0

    def classify(self, label_a: str, label_b: str,
                 book_a: str = "", book_b: str = "") -> tuple[bool, str, float]:
        """返回 (is_same_concept: bool, rationale: str, confidence: float)"""
        import hashlib
        cache_key = hashlib.md5(f"{label_a}|{label_b}".encode()).hexdigest()[:12]
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding='utf-8'))
                return cached['is_same'], cached['rationale'], cached['confidence']
            except Exception:
                pass

        prompt = self.PROMPT.format(
            label_a=label_a, label_b=label_b,
            book_a=book_a, book_b=book_b,
        )
        response = self._llm_classify(prompt)

        is_same = False
        rationale = ""
        confidence = 0.50

        if response:
            response_upper = response.strip().upper()
            if response_upper.startswith('YES'):
                is_same = True
                confidence = 0.75
            elif response_upper.startswith('NO'):
                is_same = False
                confidence = 0.85
            else:
                # Try to find YES/NO within response
                if 'YES' in response_upper[:10]:
                    is_same = True
                    confidence = 0.70
                elif 'NO' in response_upper[:10]:
                    is_same = False
                    confidence = 0.80
            rationale = response.strip()

        # Cache
        cache_file.write_text(json.dumps({
            'is_same': is_same, 'rationale': rationale, 'confidence': confidence,
            'label_a': label_a, 'label_b': label_b,
        }, ensure_ascii=False), encoding='utf-8')

        return is_same, rationale, confidence

    def _ollama(self, prompt: str, timeout: int = 60) -> str:
        import subprocess
        try:
            result = subprocess.run(
                ['ollama', 'run', self.model, prompt],
                capture_output=True, text=True, timeout=timeout,
                encoding='utf-8', errors='replace',
            )
            self._call_count += 1
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""


class CrossTextbookMerger:
    """跨教材知识图谱合并引擎"""

    RELATION_HIERARCHY = {
        'prerequisite': 0,
        'containment': 1,
        'application': 2,
        'parallel': 3,
    }

    def __init__(self, graphs_dir: str, search_engine=None,
                 llm_classifier=None):
        self.graphs_dir = Path(graphs_dir)
        self.search_engine = search_engine
        self.llm_classifier = llm_classifier  # LLMBinaryClassifier instance or None
        self.triples: dict[str, list[dict]] = {}     # book_id → triples
        self.graphs: dict[str, nx.DiGraph] = {}       # book_id → DiGraph
        self.nodes_meta: dict[str, dict] = {}          # node_id → {label, book_ids, chapters, ...}
        self.merged_graph: nx.DiGraph = nx.DiGraph()
        self.decisions: list[MergeDecision] = []
        self._decision_counter = 0

    # ── Loading ──────────────────────────────────────────────────────────

    def load_all_books(self, book_ids: Optional[list[str]] = None) -> None:
        """加载所有教材的 triples 和图"""
        triples_files = sorted(self.graphs_dir.glob('*.triples.json'))
        if book_ids:
            triples_files = [f for f in triples_files 
                           if any(bid in f.stem for bid in book_ids)]

        for tf in triples_files:
            book_id = tf.stem.replace('.triples', '')
            with open(tf, encoding='utf-8') as fp:
                self.triples[book_id] = json.load(fp)

            graph_file = self.graphs_dir / f'{book_id}.graph.json'
            if graph_file.exists():
                with open(graph_file, encoding='utf-8') as fp:
                    graph_data = json.load(fp)
                self.graphs[book_id] = nx.node_link_graph(graph_data)
            else:
                self.graphs[book_id] = self._build_graph_from_triples(book_id)

        print(f"[LOAD] {len(self.triples)} books loaded: {list(self.triples.keys())}")
        for bid, triples in self.triples.items():
            print(f"  {bid}: {len(triples)} triples, {self.graphs[bid].number_of_nodes()} nodes")

    def filter_noise(self) -> dict[str, int]:
        """过滤所有教材中的噪音节点，返回每本书的清理统计"""
        stats = {}
        for book_id in list(self.triples.keys()):
            triples = self.triples[book_id]
            graph = self.graphs[book_id]

            # 识别噪音节点
            noise_ids = set()
            for node_id in list(graph.nodes()):
                label = graph.nodes[node_id].get('label', node_id)
                if is_noise_node(label):
                    noise_ids.add(node_id)
                # 也检查 subject/object 中未在图中出现的碎片
                # 这些通常在 triple 中存在但不在图中作为节点

            # 过滤 triples
            clean_triples = []
            removed = 0
            for t in triples:
                subj, obj = t['subject'], t['object']
                if subj in noise_ids or obj in noise_ids:
                    removed += 1
                    continue
                # 过滤 subject/object 本身是碎片的
                if is_noise_node(subj) or is_noise_node(obj):
                    removed += 1
                    continue
                clean_triples.append(t)

            # 重建图
            self.triples[book_id] = clean_triples
            self.graphs[book_id] = self._build_graph_from_triples(book_id)

            stats[book_id] = {
                'before': len(triples),
                'after': len(clean_triples),
                'noise_nodes': len(noise_ids),
                'removed_triples': removed,
            }

        print(f"[FILTER] Noise removal stats:")
        for bid, s in stats.items():
            pct = (1 - s['after'] / max(s['before'], 1)) * 100
            print(f"  {bid}: {s['before']}→{s['after']} triples ({pct:.1f}% removed), "
                  f"{s['noise_nodes']} noise nodes")

        return stats

    # ── Entity Resolution ─────────────────────────────────────────────────

    def entity_resolution(self, 
                          semantic_threshold: float = 0.70,
                          auto_merge_threshold: float = 0.85,
                          use_embedding: bool = True) -> list[MergeDecision]:
        """
        跨教材概念对齐：
        1. 精确匹配 same label → 自动合并
        2. FAISS 语义相似度 → 候选生成
        3. LLM 判定（当前用规则 fallback）
        """
        # Build node registry: label → [(book_id, node_id)]
        label_index: dict[str, list[tuple[str, str]]] = defaultdict(list)
        all_nodes: list[tuple[str, str, str]] = []  # (book_id, node_id, label)
        
        for book_id, graph in self.graphs.items():
            for node_id in graph.nodes():
                label = graph.nodes[node_id].get('label', node_id).strip()
                if not label or len(label) < 2:
                    continue
                label_index[label].append((book_id, node_id))
                all_nodes.append((book_id, node_id, label))

        book_ids = sorted(self.triples.keys())
        decisions: list[MergeDecision] = []
        merged_pairs: set[tuple[str, str]] = set()  # (bookA_node, bookB_node) already handled

        # Phase 1: Exact label match across books
        print(f"\n[RESOLVE] Phase 1: Exact label matching...")
        exact_merges = 0
        for label, occurrences in label_index.items():
            if len(occurrences) < 2:
                continue
            # Check if from different books
            books_involved = set(bid for bid, _ in occurrences)
            if len(books_involved) < 2:
                continue

            # Merge all nodes with identical labels across books
            node_ids = [nid for _, nid in occurrences]
            involved_books = list(books_involved)
            self._add_decision(
                'merge', node_ids, involved_books,
                confidence=0.95,
                rationale=f"精确匹配：多本教材共用标签「{label}」",
                evidence=[f'{bid}: {label}' for bid, _ in occurrences],
            )
            exact_merges += 1

            # Mark all pairs as merged
            for (b1, n1), (b2, n2) in itertools.combinations(occurrences, 2):
                merged_pairs.add((f"{b1}::{n1}", f"{b2}::{n2}"))

        print(f"  Exact label merges: {exact_merges}")

        # Phase 2: Semantic similarity via FAISS
        if use_embedding and self.search_engine is not None:
            print(f"\n[RESOLVE] Phase 2: Semantic similarity matching...")
            semantic_merges = 0
            candidate_count = 0

            for i, (b1, n1, label1) in enumerate(all_nodes):
                if len(label1) < 4:
                    continue
                try:
                    results = self.search_engine.search(label1, top_k=10, alpha=0.5)
                except Exception:
                    continue

                for res in results:
                    if res['score'] < semantic_threshold:
                        continue
                    # Find which book/node this chunk belongs to
                    for b2, n2, label2 in all_nodes:
                        if b2 <= b1:  # avoid duplicate pairs
                            continue
                        if n2 in res['content'] or label2 in res['content']:
                            pair_key = (f"{b1}::{n1}", f"{b2}::{n2}")
                            if pair_key in merged_pairs:
                                continue
                            candidate_count += 1
                            score = res['score']

                            if score >= auto_merge_threshold:
                                self._add_decision(
                                    'merge', [f"{b1}::{n1}", f"{b2}::{n2}"], [b1, b2],
                                    confidence=score,
                                    rationale=f"语义相似度 {score:.2f}（高置信自动合并）："
                                              f"「{label1}」↔「{label2}」",
                                    evidence=[f'FAISS score: {score:.4f}'],
                                )
                                semantic_merges += 1
                                merged_pairs.add(pair_key)
                            elif score >= semantic_threshold:
                                # LLM 二分类判定（替换纯阈值，消除假阳性）
                                if self.llm_classifier is not None:
                                    is_same, llm_rationale, llm_conf = self.llm_classifier.classify(
                                        label1, label2, b1, b2
                                    )
                                    llm_conf = min(llm_conf, score)
                                    if is_same:
                                        self._add_decision(
                                            'merge', [f"{b1}::{n1}", f"{b2}::{n2}"], [b1, b2],
                                            confidence=llm_conf,
                                            rationale=f"LLM判定为同一概念: {llm_rationale} (FAISS {score:.2f})",
                                            evidence=[f'FAISS score: {score:.4f}', f'LLM: {llm_rationale}'],
                                        )
                                        semantic_merges += 1
                                        merged_pairs.add(pair_key)
                                    else:
                                        self._add_decision(
                                            'merge', [f"{b1}::{n1}", f"{b2}::{n2}"], [b1, b2],
                                            confidence=max(0.10, score - 0.40),
                                            rationale=f"LLM判定为不同概念: {llm_rationale} (FAISS {score:.2f})",
                                            evidence=[f'FAISS score: {score:.4f}', f'LLM: {llm_rationale}'],
                                        )
                                else:
                                    self._add_decision(
                                        'merge', [f"{b1}::{n1}", f"{b2}::{n2}"], [b1, b2],
                                        confidence=score,
                                        rationale=f"语义相似度 {score:.2f}（待确认，未接入LLM）："
                                                  f"「{label1}」↔「{label2}」",
                                        evidence=[f'FAISS score: {score:.4f}'],
                                    )
                            break  # one match per pair

            print(f"  Semantic candidates: {candidate_count}, auto-merged: {semantic_merges}")

        print(f"\n[RESOLVE] Total new decisions: {self._decision_counter}")
        return decisions

    # ── Relation Merging ──────────────────────────────────────────────────

    def merge_relations(self) -> list[MergeDecision]:
        """
        关系合并：
        - 同向补充（A→B + B→C → A→B→C）
        - 冲突检测（A→B vs B→A）
        - 互补发现（book1: A→B, book2: A→C）
        """
        conflict_decisions: list[MergeDecision] = []
        complement_decisions: list[MergeDecision] = []

        # Collect all edges across books: (src, dst, relation) → books
        edge_map: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for book_id, graph in self.graphs.items():
            for u, v, data in graph.edges(data=True):
                rel = data.get('relation', 'unknown')
                key = (u.strip(), v.strip(), rel)
                edge_map[key].append(book_id)

        # Conflict detection: opposite directions
        print(f"\n[MERGE] Conflict detection...")
        directed_pairs: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
        for (u, v, rel) in edge_map:
            directed_pairs[(u, v)].append((u, v, rel))

        conflicts_found = 0
        complements_found = 0

        for (u, v), edges in directed_pairs.items():
            reverse_edges = directed_pairs.get((v, u), [])
            for e1 in edges:
                for e2 in reverse_edges:
                    if e1[2] == e2[2]:
                        # Same relation but opposite direction → CONFLICT
                        conflicts_found += 1
                        self._add_decision(
                            'conflict',
                            [f"{u}", f"{v}"],
                            edge_map.get(e1, []) + edge_map.get(e2, []),
                            confidence=0.5,
                            rationale=f"关系冲突：「{u}」{e1[2]}「{v}」"
                                      f" vs 「{v}」{e2[2]}「{u}」（不同教材方向相反）",
                            evidence=[f'{b}: {u} → {v}' for b in edge_map.get(e1, [])]
                                     + [f'{b2}: {v} → {u}' for b2 in edge_map.get(e2, [])],
                        )

        # Complement discovery: A→B in book1, A not in book2
        print(f"\n[MERGE] Complement discovery...")
        for book_id, graph in self.graphs.items():
            nodes = set(graph.nodes())
            edges = set((u, v) for u, v in graph.edges())
            other_books = [b for b in self.graphs if b != book_id]
            for other_book in other_books:
                other_nodes = set(self.graphs[other_book].nodes())
                other_edges = set((u, v) for u, v in self.graphs[other_book].edges())
                # Nodes present in both books
                shared = nodes & other_nodes
                for node in shared:
                    # Outgoing edges from book1 not in book2
                    b1_out = {(u, v) for (u, v) in edges if u == node}
                    b2_out = {(u, v) for (u, v) in other_edges if u == node}
                    for edge in b1_out - b2_out:
                        complements_found += 1
                        self._add_decision(
                            'complement',
                            [edge[1]],
                            [book_id, other_book],
                            confidence=0.7,
                            rationale=f"互补发现：「{node}」在《{other_book}》中缺少关联「{edge[1]}」"
                                      f"（《{book_id}》中存在此关系）",
                            evidence=[f'{book_id}: {node} → {edge[1]}'],
                        )

        print(f"  Conflicts: {conflicts_found}, Complements: {complements_found}")
        return conflict_decisions + complement_decisions

    # ── Quality Verification ──────────────────────────────────────────────

    def verify_quality(self) -> dict:
        """质量验证：环路检测、孤立节点、关系分布"""
        merged = self._build_merged_graph()
        report = {}

        # Cycle detection (prerequisite cycles are bad)
        cycles = list(nx.simple_cycles(merged))
        prereq_cycles = []
        for cycle in cycles:
            for i in range(len(cycle)):
                u, v = cycle[i], cycle[(i + 1) % len(cycle)]
                if merged.edges[u, v].get('relation') == 'prerequisite':
                    prereq_cycles.append(cycle)
                    break

        report['total_nodes'] = merged.number_of_nodes()
        report['total_edges'] = merged.number_of_edges()
        report['cycles_total'] = len(cycles)
        report['prerequisite_cycles'] = len(prereq_cycles)
        report['prerequisite_cycle_details'] = [
            [str(n) for n in c] for c in prereq_cycles[:10]
        ]

        # Orphan nodes (degree ≤ 1)
        orphans = [n for n in merged.nodes() if merged.degree(n) <= 1]
        report['orphan_count'] = len(orphans)
        report['orphan_examples'] = orphans[:20]

        # Relation distribution
        rel_dist = defaultdict(int)
        for u, v, data in merged.edges(data=True):
            rel_dist[data.get('relation', 'unknown')] += 1
        report['relation_distribution'] = dict(rel_dist)

        print(f"\n[VERIFY] Quality report:")
        print(f"  Nodes: {report['total_nodes']}, Edges: {report['total_edges']}")
        print(f"  Cycles: {report['cycles_total']} (prerequisite: {report['prerequisite_cycles']})")
        print(f"  Orphans (deg≤1): {report['orphan_count']}")
        print(f"  Relations: {dict(rel_dist)}")

        return report

    # ── Output Generation ─────────────────────────────────────────────────

    def generate_outputs(self, output_dir: str) -> dict:
        """生成全部输出：合并图、决策日志、冲突报告"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 1. Merged graph (node-link format)
        merged = self._build_merged_graph()
        graph_path = out / 'merged_graph.json'
        graph_data = nx.node_link_data(merged)
        with open(graph_path, 'w', encoding='utf-8') as fp:
            json.dump(graph_data, fp, ensure_ascii=False, indent=2)

        # 2. Cytoscape.js format (manual conversion)
        cyto_path = out / 'merged_cytoscape.json'
        cyto_elements = self._to_cytoscape(merged)
        with open(cyto_path, 'w', encoding='utf-8') as fp:
            json.dump(cyto_elements, fp, ensure_ascii=False, indent=2)

        # 3. Decision log
        decisions_path = out / 'merge_decisions.json'
        with open(decisions_path, 'w', encoding='utf-8') as fp:
            json.dump([d.to_dict() for d in self.decisions], fp, 
                      ensure_ascii=False, indent=2)

        # 4. Merge report
        report = MergeReport(
            total_books=len(self.triples),
            total_nodes_before=sum(g.number_of_nodes() for g in self.graphs.values()),
            total_nodes_after=merged.number_of_nodes(),
            total_edges_before=sum(g.number_of_edges() for g in self.graphs.values()),
            total_edges_after=merged.number_of_edges(),
            merge_count=sum(1 for d in self.decisions if d.type == 'merge'),
            conflict_count=sum(1 for d in self.decisions if d.type == 'conflict'),
            complement_count=sum(1 for d in self.decisions if d.type == 'complement'),
            dedup_ratio=(1 - merged.number_of_nodes() / max(
                sum(g.number_of_nodes() for g in self.graphs.values()), 1)),
            decisions=self.decisions,
        )
        report_path = out / 'merge_report.json'
        with open(report_path, 'w', encoding='utf-8') as fp:
            json.dump(report.to_dict(), fp, ensure_ascii=False, indent=2)

        print(f"\n[OUTPUT] Generated in {output_dir}:")
        print(f"  merged_graph.json      — {merged.number_of_nodes()} nodes, {merged.number_of_edges()} edges")
        print(f"  merged_cytoscape.json  — Cytoscape.js format")
        print(f"  merge_decisions.json   — {len(self.decisions)} decisions")
        print(f"  merge_report.json      — Full merge report")

        return report.to_dict()

    # ── Internals ─────────────────────────────────────────────────────────

    def _build_graph_from_triples(self, book_id: str) -> nx.DiGraph:
        """从 triples 构建 NetworkX 有向图"""
        g = nx.DiGraph()
        for t in self.triples.get(book_id, []):
            subj = t['subject'].strip()
            obj = t['object'].strip()
            if not subj or not obj:
                continue
            if not g.has_node(subj):
                g.add_node(subj, label=subj, book_id=book_id,
                          chapters=t.get('chapter', ''))
            if not g.has_node(obj):
                g.add_node(obj, label=obj, book_id=book_id,
                          chapters=t.get('chapter', ''))
            g.add_edge(subj, obj,
                       relation=t['relation'],
                       confidence=t.get('confidence', 0.5),
                       evidence=t.get('evidence', ''),
                       book_id=book_id)
        return g

    def _build_merged_graph(self) -> nx.DiGraph:
        """构建合并后的全局图谱"""
        merged = nx.DiGraph()
        for book_id, graph in self.graphs.items():
            for u, v, data in graph.edges(data=True):
                # Normalize to avoid duplicates in merged graph
                rel = data.get('relation', 'unknown')
                if not merged.has_node(u):
                    merged.add_node(u, label=u)
                if not merged.has_node(v):
                    merged.add_node(v, label=v)
                if merged.has_edge(u, v):
                    existing = merged.edges[u, v]
                    if 'books' not in existing:
                        existing['books'] = [existing.get('book_id', '')]
                    existing['books'].append(book_id)
                else:
                    merged.add_edge(u, v, relation=rel,
                                   books=[book_id],
                                   confidence=data.get('confidence', 0.5))
        return merged

    def _to_cytoscape(self, graph: nx.DiGraph) -> dict:
        """Convert NetworkX graph to Cytoscape.js elements format"""
        elements: list[dict] = []
        for node_id in graph.nodes():
            data = graph.nodes[node_id]
            elements.append({
                'data': {
                    'id': node_id,
                    'label': data.get('label', node_id),
                }
            })
        for u, v, data in graph.edges(data=True):
            elements.append({
                'data': {
                    'id': f'{u}__{v}',
                    'source': u,
                    'target': v,
                    'label': data.get('relation', ''),
                    'relation': data.get('relation', ''),
                    'books': data.get('books', []),
                }
            })
        return {'elements': elements}

    def _add_decision(self, dtype: str, nodes: list[str], books: list[str],
                      confidence: float, rationale: str, evidence: list[str] = None):
        self._decision_counter += 1
        decision = MergeDecision(
            decision_id=f"decision_{self._decision_counter:05d}",
            type=dtype,
            nodes=nodes,
            books=books,
            confidence=round(confidence, 3),
            rationale=rationale,
            evidence=evidence or [],
        )
        self.decisions.append(decision)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Cross-textbook knowledge graph merger')
    parser.add_argument('--graphs-dir', default='生医黑客松/graphs',
                       help='Directory containing .triples.json and .graph.json')
    parser.add_argument('--output-dir', default='生医黑客松/merged',
                       help='Output directory for merged results')
    parser.add_argument('--index-prefix', default='medical_index',
                       help='FAISS index prefix for semantic matching')
    parser.add_argument('--semantic-threshold', type=float, default=0.70,
                       help='Minimum FAISS score for semantic match candidates')
    parser.add_argument('--auto-merge-threshold', type=float, default=0.85,
                       help='FAISS score above which auto-merge without review')
    args = parser.parse_args()

    # Try to load search engine
    search_engine = None
    try:
        from search_engine import MedicalSearchEngine
        eng = MedicalSearchEngine()
        eng.load(args.index_prefix)
        search_engine = eng
        print("[INIT] FAISS search engine loaded.")
    except Exception as e:
        print(f"[INIT] FAISS unavailable ({e}), semantic matching disabled.")

    merger = CrossTextbookMerger(args.graphs_dir, search_engine)
    
    print("\n" + "=" * 60)
    print("STEP 1: Load all books")
    print("=" * 60)
    merger.load_all_books()
    
    print("\n" + "=" * 60)
    print("STEP 2: Filter noise")
    print("=" * 60)
    merger.filter_noise()
    
    print("\n" + "=" * 60)
    print("STEP 3: Entity resolution")
    print("=" * 60)
    merger.entity_resolution(
        semantic_threshold=args.semantic_threshold,
        auto_merge_threshold=args.auto_merge_threshold,
        use_embedding=(search_engine is not None),
    )
    
    print("\n" + "=" * 60)
    print("STEP 4: Relation merging")
    print("=" * 60)
    merger.merge_relations()
    
    print("\n" + "=" * 60)
    print("STEP 5: Quality verification")
    print("=" * 60)
    merger.verify_quality()
    
    print("\n" + "=" * 60)
    print("STEP 6: Generate outputs")
    print("=" * 60)
    merger.generate_outputs(args.output_dir)
    
    print("\n[DONE] Cross-textbook merge complete.")


if __name__ == '__main__':
    main()
