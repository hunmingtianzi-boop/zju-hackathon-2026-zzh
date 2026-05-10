from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import networkx as nx
from networkx.readwrite import json_graph


# ─── 噪声模式 (前置过滤，阻止前导页节点进入图谱) ──────────────────────────

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
    r'^\ud83d[\udca1-\udcaf]',  # 💡 emoji bullet
    r'^第\s*\d+\s*版',
    r'^\d+\.\d+',
    r'^[A-Za-z\s]+$',
    r'^\d{2,3}$',
    r'^.*出版社.*$',
    r'^\s*$',
    r'^.*医科大学.*$',
    r'^.*医学院.*$',
    r'^.*大学.*学院.*$',
    r'^.*附属.*医院.*$',
    r'^.*@.*$',
]

_noise_regex = re.compile('|'.join(f'({p})' for p in NOISE_PATTERNS))

MEDICAL_SHORT_TERMS = {
    '心脏', '肺', '肝', '肾', '胃', '肠', '脑', '皮肤', '血液', '神经',
    '动脉', '静脉', '淋巴', '骨骼', '肌肉', '关节', '细胞', '组织',
    '免疫', '炎症', '肿瘤', '感染', '代谢', '激素', '基因', '蛋白', '心电图',
}

MEDICAL_LABEL_HINTS = (
    "调节", "组织", "细胞", "上皮", "神经", "血管", "心电", "心律", "代谢",
    "反射", "分泌", "激素", "免疫", "炎症", "病理", "生理", "胚胎", "器官",
)


def is_noise_node(label: str) -> bool:
    """判断节点标签是否为前导页/版权/编委等噪音"""
    label = label.strip()
    if label in MEDICAL_SHORT_TERMS:
        return False
    if len(label) < 3 or len(label) > 80:
        return True
    if _noise_regex.search(label):
        return True
    alpha_chars = sum(1 for c in label if c.isalpha() or '\u4e00' <= c <= '\u9fff')
    if alpha_chars / max(len(label), 1) < 0.3:
        return True
    if len(label) < 5 and alpha_chars < 3:
        return True
    if alpha_chars / max(len(label), 1) < 0.5 and len(label) < 10:
        return True
    # 人名模式
    stripped = label.replace(' ', '').replace('\u3000', '')
    if 2 <= len(stripped) <= 4 and all('\u4e00' <= c <= '\u9fff' for c in stripped):
        if stripped not in MEDICAL_SHORT_TERMS and not any(hint in stripped for hint in MEDICAL_LABEL_HINTS):
            return True
    return False


def is_noise_chunk(heading: str, content: str) -> bool:
    """判断 chunk 是否为前导页噪音（标题或内容前200字匹配噪音模式）"""
    if is_noise_node(heading):
        return True
    # 检查内容前200字符是否以噪音为主
    preview = content[:200].strip()
    alpha_chars = sum(1 for c in preview if c.isalpha() or '\u4e00' <= c <= '\u9fff')
    if len(preview) > 20 and alpha_chars / max(len(preview), 1) < 0.2:
        return True
    return False


# ─── 关系类型 ────────────────────────────────────────────────────────────

RELATION_TYPES = {
    "prerequisite": "前置依赖",
    "parallel": "并列关系",
    "containment": "包含关系",
    "application": "应用关系",
}

GENERIC_CONCEPTS = {
    "从而", "一种", "系统的", "主要", "因此", "以及", "及其", "此外", "例如", "包括",
    "由于", "通过", "进行", "可以", "为了", "具有", "有关", "相关", "临床", "疾病",
    "异常", "治疗", "诊断", "预防", "评估", "应用", "作用", "功能", "特点", "结构",
    "概述", "概要", "开篇", "前言", "序言", "目录", "复习题", "思考题",
}

APPLICATION_HINTS = (
    "用于", "有助于", "有利于", "诊断", "治疗", "防治", "预防", "评估", "临床",
    "疾病", "病理", "综合征", "异常", "病例", "检查", "药物", "靶点", "手术",
)


@dataclass
class KnowledgeTriple:
    subject: str
    relation: str
    object: str
    evidence: str
    source_path: str
    book_id: str
    chapter: str
    section: str
    confidence: float = 0.75
    extractor: str = "rule_based"
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class GraphQualityReport:
    book_id: str
    nodes: int
    edges: int
    triples: int
    relation_counts: dict[str, int]
    prerequisite_cycles: list[list[str]]
    low_degree_nodes: list[str]
    invalid_triples: list[dict[str, str]]


def clean_label(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text)
    text = re.sub(r"^#+\s*", "", text.strip())
    text = re.sub(r"\.{3,}\s*\d*\s*$", "", text)
    text = re.sub(r"[_]{2,}", " ", text)
    text = re.sub(r"[_\s]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", text)
    text = re.sub(r"^[(（][一二三四五六七八九十\d]+[)）]\s*", "", text)
    text = re.sub(r"^(第\s*[一二三四五六七八九十百零〇\d]+\s*[章节篇编])\s*$", r"\1", text)
    return text.strip(" \t\r\n-—|:：，,。；;")


def natural_sort_key(text: str) -> list[object]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def valid_concept_label(text: str, allow_short_medical: bool = True) -> bool:
    label = clean_label(text)
    if not label or label in GENERIC_CONCEPTS:
        return False
    if len(label) < 4 and not (allow_short_medical and label in MEDICAL_SHORT_TERMS):
        return False
    if len(label) > 48:
        return False
    if is_noise_node(label):
        return False
    if re.search(r"(出版社|规划教材|编委|主编|副主编|ISBN|CIP|版权所有|医学院|大学|医院)", label):
        return False
    return True


def split_sentences(markdown: str) -> list[str]:
    markdown = re.sub(r"^#{1,6}\s+.*$", "", markdown, flags=re.MULTILINE)
    compact = re.sub(r"\s+", "", markdown)
    parts = re.split(r"(?<=[。；;])", compact)
    return [part for part in parts if len(part) >= 12]


def parse_chunk_identity(path: Path, book_id: str, markdown: str) -> tuple[str, str]:
    first_heading = ""
    for line in markdown.splitlines():
        if line.lstrip().startswith("#"):
            first_heading = clean_label(line)
            break

    stem = path.stem
    parts = [clean_label(part) for part in stem.split("_") if clean_label(part)]
    chapter = parts[0] if parts else book_id
    section = first_heading or (parts[-1] if parts else chapter)
    return chapter, section


class RuleBasedTripleExtractor:
    """Deterministic extractor for section-level textbook maps.

    The class intentionally favors high-precision structural relations. LLM
    extraction can be added later by producing the same KnowledgeTriple schema.
    """

    def extract_book(self, book_dir: Path) -> list[KnowledgeTriple]:
        book_id = book_dir.name
        triples: list[KnowledgeTriple] = []
        previous_section: str | None = None
        previous_source: str | None = None
        prerequisite_edges: set[tuple[str, str]] = set()

        for chunk_path, source_path, markdown in self._iter_book_chunks(book_dir):
            chapter, section = parse_chunk_identity(chunk_path, book_id, markdown)
            if is_noise_chunk(section, markdown) and len(markdown) < 1200:
                continue

            if valid_concept_label(chapter, allow_short_medical=False):
                triples.append(
                    KnowledgeTriple(
                        subject=book_id,
                        relation="containment",
                        object=chapter,
                        evidence=self._first_nonempty_line(markdown) or f"{book_id} 教材包含章节：{chapter}",
                        source_path=source_path,
                        book_id=book_id,
                        chapter=chapter,
                        section=section,
                        confidence=0.95,
                    )
                )
            if chapter != section and valid_concept_label(chapter, allow_short_medical=False) and valid_concept_label(section):
                triples.append(
                    KnowledgeTriple(
                        subject=chapter,
                        relation="containment",
                        object=section,
                        evidence=self._first_nonempty_line(markdown) or f"{chapter} 包含小节：{section}",
                        source_path=source_path,
                        book_id=book_id,
                        chapter=chapter,
                        section=section,
                        confidence=0.9,
                    )
                )

            headings = self._subheadings(markdown)
            for heading in headings:
                if not valid_concept_label(section) or not valid_concept_label(heading):
                    continue
                triples.append(
                    KnowledgeTriple(
                        subject=section,
                        relation="containment",
                        object=heading,
                        evidence=f"{section} 下设标题：{heading}",
                        source_path=source_path,
                        book_id=book_id,
                        chapter=chapter,
                        section=section,
                        confidence=0.88,
                    )
                )

            triples.extend(
                self._heading_prerequisites(
                    headings,
                    source_path,
                    book_id,
                    chapter,
                    section,
                    prerequisite_edges,
                )
            )
            triples.extend(
                self._parallel_triples(headings, source_path, book_id, chapter, section)
            )
            triples.extend(
                self._application_triples(markdown, source_path, book_id, chapter, section)
            )

            if (
                previous_section
                and previous_section != section
                and not self._would_create_prerequisite_cycle(
                    previous_section,
                    section,
                    prerequisite_edges,
                )
            ):
                triples.append(
                    KnowledgeTriple(
                        subject=previous_section,
                        relation="prerequisite",
                        object=section,
                        evidence=f"教材章节顺序：{previous_section} 位于 {section} 之前。",
                        source_path=previous_source or source_path,
                        book_id=book_id,
                        chapter=chapter,
                        section=section,
                        confidence=0.65,
                        metadata={"basis": "section_order"},
                    )
                )
                prerequisite_edges.add((previous_section, section))
            previous_section = section
            previous_source = source_path

        return deduplicate_triples(triples)

    def _iter_book_chunks(self, book_dir: Path) -> list[tuple[Path, str, str]]:
        chunk_files = sorted(book_dir.glob("*.md"), key=lambda path: natural_sort_key(path.name))
        root_md = book_dir.parent.parent / f"{book_dir.name}.md"
        if root_md.exists():
            chunk_chars = sum(path.stat().st_size for path in chunk_files)
            if len(chunk_files) <= 3 or root_md.stat().st_size > chunk_chars * 2:
                return self._virtual_chunks_from_markdown(root_md, book_dir.name)

        return [
            (path, str(path.resolve()), path.read_text(encoding="utf-8"))
            for path in chunk_files
        ]

    def _virtual_chunks_from_markdown(self, markdown_path: Path, book_id: str) -> list[tuple[Path, str, str]]:
        markdown = markdown_path.read_text(encoding="utf-8")
        chunks: list[tuple[Path, str, str]] = []
        current_title = book_id
        current_lines: list[str] = []

        def flush() -> None:
            nonlocal current_lines, current_title
            body = re.sub(r"\n{3,}", "\n\n", "\n".join(current_lines)).strip()
            if len(body) < 20:
                current_lines = []
                return
            index = len(chunks)
            virtual_path = Path(f"{markdown_path.stem}_{index:04d}_{clean_label(current_title) or 'section'}.md")
            chunks.append((virtual_path, f"{markdown_path.resolve()}#section-{index}", body))
            current_lines = []

        for raw_line in markdown.splitlines():
            line = raw_line.rstrip()
            heading = re.match(r"^(#{1,2})\s+(.+?)\s*$", line)
            if heading:
                title = clean_label(heading.group(2))
                if valid_concept_label(title, allow_short_medical=False):
                    flush()
                    current_title = title
                    current_lines = [line]
                    continue
            current_lines.append(line)
        flush()
        return chunks

    def _would_create_prerequisite_cycle(
        self,
        subject: str,
        obj: str,
        edges: set[tuple[str, str]],
    ) -> bool:
        if subject == obj:
            return True
        graph = nx.DiGraph()
        graph.add_edges_from(edges)
        if subject not in graph or obj not in graph:
            return False
        return nx.has_path(graph, obj, subject)

    def _subheadings(self, markdown: str) -> list[str]:
        headings: list[str] = []
        for line in markdown.splitlines():
            if not re.match(r"^#{2,6}\s+", line):
                continue
            heading = clean_label(line)
            if valid_concept_label(heading):
                headings.append(heading)
        return list(dict.fromkeys(headings))

    def _parallel_triples(
        self,
        headings: list[str],
        source_path: str,
        book_id: str,
        chapter: str,
        section: str,
    ) -> list[KnowledgeTriple]:
        triples: list[KnowledgeTriple] = []
        for left, right in zip(headings, headings[1:]):
            if left == right or not valid_concept_label(left) or not valid_concept_label(right):
                continue
            evidence = f"{left} 与 {right} 是 {section} 下相邻的同级标题。"
            for subject, obj in ((left, right), (right, left)):
                triples.append(
                    KnowledgeTriple(
                        subject=subject,
                        relation="parallel",
                        object=obj,
                        evidence=evidence,
                        source_path=source_path,
                        book_id=book_id,
                        chapter=chapter,
                        section=section,
                        confidence=0.78,
                        metadata={"symmetric": "true"},
                    )
                )
        return triples

    def _heading_prerequisites(
        self,
        headings: list[str],
        source_path: str,
        book_id: str,
        chapter: str,
        section: str,
        prerequisite_edges: set[tuple[str, str]],
    ) -> list[KnowledgeTriple]:
        triples: list[KnowledgeTriple] = []
        for left, right in zip(headings, headings[1:]):
            if (
                left == right
                or not valid_concept_label(left)
                or not valid_concept_label(right)
                or self._would_create_prerequisite_cycle(left, right, prerequisite_edges)
            ):
                continue
            triples.append(
                KnowledgeTriple(
                    subject=left,
                    relation="prerequisite",
                    object=right,
                    evidence=f"同一教材小节标题顺序：{left} 位于 {right} 之前。",
                    source_path=source_path,
                    book_id=book_id,
                    chapter=chapter,
                    section=section,
                    confidence=0.68,
                    metadata={"basis": "heading_order"},
                )
            )
            prerequisite_edges.add((left, right))
        return triples

    def _application_triples(
        self,
        markdown: str,
        source_path: str,
        book_id: str,
        chapter: str,
        section: str,
    ) -> list[KnowledgeTriple]:
        triples: list[KnowledgeTriple] = []
        patterns = [
            r"(?P<subject>[\u4e00-\u9fa5A-Za-z0-9α-ωΑ-Ωβγδμ\-]{2,18})(?:可|能)?用于(?P<object>[^。；;，,]{2,32})",
            r"(?P<subject>[\u4e00-\u9fa5A-Za-z0-9α-ωΑ-Ωβγδμ\-]{2,18})(?:有助于|有利于|参与|影响)(?P<object>[^。；;，,]{2,32})",
            r"(?P<subject>[\u4e00-\u9fa5A-Za-z0-9α-ωΑ-Ωβγδμ\-]{2,18})(?:是|为)(?P<object>[^。；;，,]{2,32})(?:诊断|治疗|防治|预防|评估|基础|靶点)",
            r"(?P<subject>[\u4e00-\u9fa5A-Za-z0-9α-ωΑ-Ωβγδμ\-]{2,18})(?:异常|障碍|缺陷)(?:可|会|能)?(?:导致|引起|造成)(?P<object>[^。；;，,]{2,32})",
            r"(?P<subject>[\u4e00-\u9fa5A-Za-z0-9α-ωΑ-Ωβγδμ\-]{2,18})(?:与)(?P<object>[^。；;，,]{2,32})(?:有关|相关)",
        ]
        for sentence in split_sentences(markdown):
            if not any(hint in sentence for hint in APPLICATION_HINTS):
                continue
            emitted = False
            for pattern in patterns:
                match = re.search(pattern, sentence)
                if not match:
                    continue
                subject = re.sub(r"[可能]$", "", clean_label(match.group("subject")))
                obj = clean_label(match.group("object"))
                if not self._valid_concept(subject) or not self._valid_concept(obj):
                    continue
                triples.append(
                    KnowledgeTriple(
                        subject=subject,
                        relation="application",
                        object=obj,
                        evidence=sentence[:160],
                        source_path=source_path,
                        book_id=book_id,
                        chapter=chapter,
                        section=section,
                        confidence=0.72,
                    )
                )
                emitted = True
                break
            if not emitted and valid_concept_label(section):
                topic = self._clinical_topic(sentence)
                if topic and self._valid_concept(topic):
                    triples.append(
                        KnowledgeTriple(
                            subject=section,
                            relation="application",
                            object=topic,
                            evidence=sentence[:160],
                            source_path=source_path,
                            book_id=book_id,
                            chapter=chapter,
                            section=section,
                            confidence=0.62,
                            metadata={"basis": "clinical_sentence"},
                        )
                    )
            if len(triples) >= 6:
                break
        return triples

    def _valid_concept(self, text: str) -> bool:
        return valid_concept_label(text)

    def _clinical_topic(self, sentence: str) -> str:
        for keyword in ("诊断", "治疗", "防治", "预防", "评估", "疾病", "病理", "异常", "临床"):
            position = sentence.find(keyword)
            if position < 0:
                continue
            start = max(0, position - 10)
            end = min(len(sentence), position + 18)
            topic = clean_label(sentence[start:end])
            topic = re.sub(r"^[，,。；;、]+", "", topic)
            return topic[:32]
        return ""

    def _first_nonempty_line(self, markdown: str) -> str:
        for line in markdown.splitlines():
            line = clean_label(line)
            if line:
                return line
        return ""


def deduplicate_triples(triples: Iterable[KnowledgeTriple]) -> list[KnowledgeTriple]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[KnowledgeTriple] = []
    for triple in triples:
        key = (triple.subject, triple.relation, triple.object, triple.source_path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(triple)
    return unique


def validate_triple(triple: KnowledgeTriple) -> str | None:
    if triple.relation not in RELATION_TYPES:
        return f"Unsupported relation: {triple.relation}"
    if not triple.subject or not triple.object:
        return "Triple subject/object cannot be empty"
    if not triple.evidence:
        return "Triple evidence cannot be empty"
    if triple.subject == triple.object:
        return "Self-loop triples are not allowed"
    return None


# ─── LLM 三元组抽取器 ──────────────────────────────────────────────────

class LLMTripleExtractor:
    """使用本地 Ollama 模型从 chunk 文本中提取结构化知识三元组。

    替代 RuleBasedTripleExtractor，实现赛题要求的 "对每个章节调用 LLM，
    提取核心知识点"（F2 进阶分）。
    """

    PROMPT_TEMPLATE = """你是一位医学知识工程师。从以下医学教材段落中提取核心知识点，输出为结构化三元组。

## 关系类型（四选一）
- prerequisite（前置依赖）：A 是学习/理解 B 的前提
- parallel（并列关系）：A 与 B 同级、同类
- containment（包含关系）：A 包含 B
- application（应用关系）：A 的知识应用于 B

## 规则
1. 每个三元组必须包含 subject、relation（四选一）、object、evidence（原文证据句）
2. 每 chunk 提取 3-8 个三元组
3. subject 和 object 必须是具体的医学概念，长度 2-25 字
4. evidence 必须从原文中直接引用
5. 跳过前言、致谢、编委名单等非知识内容——若段落无实质医学知识，返回空数组

## 输出格式
严格输出 JSON 数组，不要输出任何其他内容：
[
  {{"subject": "心脏解剖", "relation": "containment", "object": "心室", "evidence": "心脏由心房和心室组成"}},
  {{"subject": "心脏解剖", "relation": "prerequisite", "object": "心功能评估", "evidence": "了解心脏结构是评估心功能的基础"}}
]

## 教材段落
{chunk_text}

请输出 JSON 数组："""

    def __init__(self, model: str = "qwen2.5:3b", cache_dir: str = "生医黑客松/.triple_cache"):
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._call_count = 0
        self._total_time = 0.0

    def _llm_call(self, prompt: str, timeout: int = 120) -> str:
        t0 = time.time()
        try:
            result = subprocess.run(
                ['ollama', 'run', self.model, prompt],
                capture_output=True, text=True, timeout=timeout,
                encoding='utf-8', errors='replace',
            )
            elapsed = time.time() - t0
            self._call_count += 1
            self._total_time += elapsed
            if result.returncode != 0:
                print(f"  [LLM] ERROR (call #{self._call_count}, {elapsed:.1f}s): {result.stderr[:200]}")
                return ""
            print(f"  [LLM] call #{self._call_count} ok ({elapsed:.1f}s, {len(result.stdout)} chars)")
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            elapsed = time.time() - t0
            print(f"  [LLM] TIMEOUT after {elapsed:.1f}s")
            self._call_count += 1
            return ""
        except FileNotFoundError:
            print("  [LLM] ollama not found in PATH")
            return ""

    def _extract_json(self, response: str) -> list[dict]:
        if not response:
            return []
        response = re.sub(r'```(?:json)?\s*', '', response)
        response = re.sub(r'```\s*$', '', response)
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            return []
        except json.JSONDecodeError:
            objects = re.findall(r'\{[^{}]*\}', response)
            results = []
            for obj_str in objects:
                try:
                    obj = json.loads(obj_str)
                    if isinstance(obj, dict):
                        results.append(obj)
                except json.JSONDecodeError:
                    pass
            return results

    def _validate_triple(self, raw: dict) -> KnowledgeTriple | None:
        subj = raw.get('subject', '').strip()
        rel = raw.get('relation', '').strip().lower()
        obj = raw.get('object', '').strip()
        ev = raw.get('evidence', '').strip()
        if not subj or not obj or not ev or len(subj) < 2 or len(obj) < 2:
            return None
        if rel not in RELATION_TYPES:
            rel_map = {
                'prerequisite': 'prerequisite', 'parallel': 'parallel',
                'containment': 'containment', 'application': 'application',
                '前置依赖': 'prerequisite', '并列关系': 'parallel',
                '包含关系': 'containment', '应用关系': 'application',
                'contains': 'containment', 'includes': 'containment',
                'depends_on': 'prerequisite', 'applies_to': 'application',
            }
            rel = rel_map.get(rel, '')
            if not rel:
                return None
        if is_noise_node(subj) or is_noise_node(obj):
            return None
        return KnowledgeTriple(
            subject=subj, relation=rel, object=obj, evidence=ev,
            source_path='', book_id='', chapter='', section='',
            confidence=0.70, extractor='llm',
        )

    def extract_chunk(self, markdown: str, source_path: str,
                      book_id: str, chapter: str, section: str) -> list[KnowledgeTriple]:
        import hashlib
        cache_key = hashlib.md5((source_path + markdown[:200]).encode()).hexdigest()[:12]
        cache_file = self.cache_dir / f"{book_id}_{cache_key}.json"

        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding='utf-8'))
                triples = []
                for item in cached:
                    t = KnowledgeTriple(
                        subject=item['subject'], relation=item['relation'],
                        object=item['object'], evidence=item.get('evidence', ''),
                        source_path=source_path, book_id=book_id,
                        chapter=chapter, section=section,
                        confidence=item.get('confidence', 0.70), extractor='llm',
                    )
                    triples.append(t)
                if triples:
                    return triples
            except Exception:
                pass

        chunk_text = markdown[:2000]
        prompt = self.PROMPT_TEMPLATE.format(chunk_text=chunk_text)
        response = self._llm_call(prompt)
        if not response:
            return []

        raw_triples = self._extract_json(response)
        triples: list[KnowledgeTriple] = []
        for raw in raw_triples:
            t = self._validate_triple(raw)
            if t:
                t.source_path = source_path
                t.book_id = book_id
                t.chapter = chapter
                t.section = section
                triples.append(t)

        cache_data = [{
            'subject': t.subject, 'relation': t.relation,
            'object': t.object, 'evidence': t.evidence,
            'confidence': t.confidence,
        } for t in triples]
        cache_file.write_text(json.dumps(cache_data, ensure_ascii=False), encoding='utf-8')
        return triples

    def extract_book(self, book_dir: Path, skip_noise: bool = True) -> list[KnowledgeTriple]:
        book_id = book_dir.name
        triples: list[KnowledgeTriple] = []
        chunk_files = sorted(book_dir.glob("*.md"), key=lambda p: p.name)

        for chunk_path in chunk_files:
            markdown = chunk_path.read_text(encoding='utf-8')
            chapter, section = parse_chunk_identity(chunk_path, book_id, markdown)
            source_path = str(chunk_path.resolve())

            if skip_noise and is_noise_chunk(section, markdown):
                print(f"  [SKIP] noise chunk: {chunk_path.name}")
                continue

            print(f"  [LLM] extracting: {chapter} / {section}")
            chunk_triples = self.extract_chunk(
                markdown, source_path, book_id, chapter, section
            )
            triples.extend(chunk_triples)
            print(f"    -> {len(chunk_triples)} triples")

        print(f"  [LLM] Total: {len(triples)} triples from {len(chunk_files)} chunks "
              f"({self._call_count} LLM calls, {self._total_time:.0f}s)")
        return triples


def build_graph(triples: Iterable[KnowledgeTriple]) -> tuple[nx.DiGraph, list[dict[str, str]]]:
    graph = nx.DiGraph()
    invalid: list[dict[str, str]] = []

    for triple in triples:
        reason = validate_triple(triple)
        if reason:
            payload = asdict(triple)
            payload["reason"] = reason
            invalid.append(payload)
            continue

        for node_id in (triple.subject, triple.object):
            graph.add_node(
                node_id,
                label=node_id,
                book_id=triple.book_id,
                chapters=sorted(
                    set(graph.nodes[node_id].get("chapters", [])) | {triple.chapter}
                ) if node_id in graph else [triple.chapter],
            )

        edge_key = (triple.subject, triple.object)
        if graph.has_edge(*edge_key):
            existing = graph.edges[edge_key]
            existing.setdefault("evidence", []).append(triple.evidence)
            existing.setdefault("source_paths", []).append(triple.source_path)
            existing["confidence"] = max(existing.get("confidence", 0), triple.confidence)
            continue

        graph.add_edge(
            triple.subject,
            triple.object,
            relation=triple.relation,
            relation_label=RELATION_TYPES[triple.relation],
            evidence=[triple.evidence],
            source_paths=[triple.source_path],
            book_id=triple.book_id,
            chapter=triple.chapter,
            section=triple.section,
            confidence=triple.confidence,
            extractor=triple.extractor,
            metadata=triple.metadata,
        )

    return graph, invalid


def quality_report(
    graph: nx.DiGraph,
    triples: list[KnowledgeTriple],
    invalid_triples: list[dict[str, str]],
    book_id: str,
) -> GraphQualityReport:
    relation_counts = {relation: 0 for relation in RELATION_TYPES}
    for _, _, data in graph.edges(data=True):
        relation = data.get("relation")
        if relation in relation_counts:
            relation_counts[relation] += 1

    prerequisite_graph = nx.DiGraph(
        (source, target)
        for source, target, data in graph.edges(data=True)
        if data.get("relation") == "prerequisite"
    )
    cycles = [cycle for cycle in nx.simple_cycles(prerequisite_graph)]
    low_degree_nodes = sorted(
        node for node, degree in graph.degree()
        if degree <= 1 and not str(node).startswith(book_id)
    )

    return GraphQualityReport(
        book_id=book_id,
        nodes=graph.number_of_nodes(),
        edges=graph.number_of_edges(),
        triples=len(triples),
        relation_counts=relation_counts,
        prerequisite_cycles=cycles,
        low_degree_nodes=low_degree_nodes[:200],
        invalid_triples=invalid_triples,
    )


def to_cytoscape(graph: nx.DiGraph) -> dict[str, list[dict[str, object]]]:
    nodes = [
        {"data": {"id": str(node), **data}}
        for node, data in graph.nodes(data=True)
    ]
    edges = []
    for index, (source, target, data) in enumerate(graph.edges(data=True)):
        edge_data = {"id": f"e{index}", "source": str(source), "target": str(target), **data}
        edges.append({"data": edge_data})
    return {"nodes": nodes, "edges": edges}


def build_single_book_graph(book_dir: Path, output_dir: Path,
                           extractor_type: str = "rule") -> GraphQualityReport:
    if extractor_type == "llm":
        extractor = LLMTripleExtractor()
    else:
        extractor = RuleBasedTripleExtractor()
    triples = extractor.extract_book(book_dir)
    graph, invalid = build_graph(triples)
    report = quality_report(graph, triples, invalid, book_dir.name)

    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / book_dir.name
    (prefix.with_suffix(".triples.json")).write_text(
        json.dumps([asdict(triple) for triple in triples], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (prefix.with_suffix(".graph.json")).write_text(
        json.dumps(json_graph.node_link_data(graph, edges="edges"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (prefix.with_suffix(".cytoscape.json")).write_text(
        json.dumps(to_cytoscape(graph), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (prefix.with_suffix(".quality.json")).write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def build_all_books(chunks_dir: Path, output_dir: Path,
                    extractor_type: str = "rule") -> list[GraphQualityReport]:
    reports: list[GraphQualityReport] = []
    for book_dir in sorted(path for path in chunks_dir.iterdir() if path.is_dir()):
        reports.append(build_single_book_graph(book_dir, output_dir, extractor_type))
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one independent knowledge graph per textbook.")
    parser.add_argument("--chunks-dir", default="生医黑客松/chunks", help="Directory containing per-book chunk folders.")
    parser.add_argument("--book", help="Optional book folder name, e.g. 03_生理学.")
    parser.add_argument("--output-dir", default="生医黑客松/graphs", help="Directory for graph JSON outputs.")
    args = parser.parse_args()

    chunks_dir = Path(args.chunks_dir)
    output_dir = Path(args.output_dir)

    if args.book:
        reports = [build_single_book_graph(chunks_dir / args.book, output_dir)]
    else:
        reports = build_all_books(chunks_dir, output_dir)

    print("Built single-book knowledge graphs:")
    for report in reports:
        print(
            f"- {report.book_id}: {report.nodes} nodes, {report.edges} edges, "
            f"{report.triples} triples, cycles={len(report.prerequisite_cycles)}"
        )


if __name__ == "__main__":
    main()
