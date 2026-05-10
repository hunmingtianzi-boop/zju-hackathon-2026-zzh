from __future__ import annotations

import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
VAULT_DIR = ROOT / "生医黑客松"

RELATION_LABELS = {
    "prerequisite": "Prerequisite",
    "parallel": "Parallel",
    "containment": "Inclusion",
    "application": "Application",
}

BOOK_LABELS = {
    "01_局部解剖学": "01 局部解剖学",
    "02_组织学与胚胎学": "02 组织学与胚胎学",
    "03_生理学": "03 生理学",
    "04_医学微生物学": "04 医学微生物学",
    "05_病理学": "05 病理学",
    "06_传染病学": "06 传染病学",
    "07_病理生理学": "07 病理生理学",
}

NOISE_PATTERNS = [
    r"^国家卫生健康委员会",
    r"^全 国 高 等 学 校 教 材$",
    r"^供基础",
    r"^编\s*委",
    r"^主\s*编",
    r"^副主编",
    r"^第十轮",
    r"^修订说明",
    r"^中英文名词对照索引$",
    r"^前言$",
    r"^目录$",
    r"^附录$",
    r"^绪论\d*$",
    r"^第[一二三四五六七八九十]+章\s*$",
    r"^第[一二三四五六七八九十]+节\s*$",
    r"^[\d\s._-]+$",
    r"^💡",
]


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def is_noise(label: str) -> bool:
    label = str(label).strip()
    if len(label) < 2 or len(label) > 42:
        return True
    if any(re.search(pattern, label) for pattern in NOISE_PATTERNS):
        return True
    alpha_chars = sum(1 for char in label if char.isalpha() or "\u4e00" <= char <= "\u9fff")
    return alpha_chars / max(len(label), 1) < 0.45


def clean_label(label: str) -> str:
    label = re.sub(r"[\x00-\x1f]", "", str(label))
    label = re.sub(r"\s+", " ", label).strip()
    label = re.sub(r"\.{3,}\s*\d*$", "", label)
    return label[:60]


def edge_items(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return graph.get("links") or graph.get("edges") or []


def node_books(node_id: str, incident_edges: list[dict[str, Any]]) -> list[str]:
    books: set[str] = set()
    for edge in incident_edges:
        if edge.get("source") == node_id or edge.get("target") == node_id:
            for book in edge.get("books", []):
                if book:
                    books.add(book)
    return sorted(books)


def relation_counts(edges: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(edge.get("relation", "unknown") for edge in edges)
    return {RELATION_LABELS.get(key, key): value for key, value in sorted(counts.items())}


def build_decision_index(decisions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for decision in decisions:
        for raw_node in decision.get("nodes", []):
            node = str(raw_node).split("::")[-1]
            index[node].append(decision)
    return index


def first_decision(node_id: str, decision_index: dict[str, list[dict[str, Any]]]) -> dict[str, Any] | None:
    candidates = decision_index.get(node_id, [])
    if candidates:
        return sorted(candidates, key=lambda item: item.get("confidence", 0), reverse=True)[0]
    return None


def compact_essence_report(report: dict[str, Any], strict_report: dict[str, Any]) -> dict[str, Any]:
    active = strict_report or report
    return {
        "originalChars": active.get("original_chars", report.get("original_chars", 0)),
        "compressedChars": active.get("compressed_chars", report.get("compressed_chars", 0)),
        "compressionRatio": active.get("compression_ratio", report.get("compression_ratio", 0)),
        "rawCompressionRatio": report.get("compression_ratio", 0),
        "targetMet": active.get("compression_ratio", 1) <= 0.3,
        "tierDistribution": active.get("tier_distribution", report.get("tier_distribution", {})),
        "method": active.get("summarization_method", report.get("summarization_method", "rule_based")),
        "strict": bool(strict_report),
    }


def select_readable_subgraph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    max_nodes: int = 180,
    max_edges: int = 360,
) -> tuple[list[str], list[dict[str, Any]]]:
    labels = {node.get("id"): clean_label(node.get("label", node.get("id", ""))) for node in nodes}
    degree = Counter()
    cleaned_edges: list[dict[str, Any]] = []

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        if source not in labels or target not in labels:
            continue
        if is_noise(labels[source]) or is_noise(labels[target]):
            continue
        relation = edge.get("relation", "")
        if relation not in RELATION_LABELS:
            continue
        cleaned_edges.append(edge)
        degree[source] += 1
        degree[target] += 1

    seed_nodes = [node for node, _ in degree.most_common(36)]
    selected: set[str] = set(seed_nodes)
    queue = deque(seed_nodes)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in cleaned_edges:
        adjacency[edge["source"]].append(edge["target"])
        adjacency[edge["target"]].append(edge["source"])

    while queue and len(selected) < max_nodes:
        current = queue.popleft()
        neighbors = sorted(adjacency[current], key=lambda item: degree[item], reverse=True)
        for neighbor in neighbors[:10]:
            if neighbor in selected:
                continue
            selected.add(neighbor)
            queue.append(neighbor)
            if len(selected) >= max_nodes:
                break

    selected_edges = [
        edge for edge in cleaned_edges
        if edge["source"] in selected and edge["target"] in selected
    ]
    selected_edges.sort(
        key=lambda edge: (
            0 if edge.get("relation") == "application" else 1,
            -(len(edge.get("books", []))),
            -(degree[edge["source"]] + degree[edge["target"]]),
        )
    )
    return list(selected), selected_edges[:max_edges]


def build_agent_data() -> dict[str, Any]:
    merged_graph = read_json(VAULT_DIR / "merged" / "merged_graph.json", {"nodes": [], "links": []})
    merge_report = read_json(VAULT_DIR / "merged" / "merge_report.json", {})
    decisions = read_json(VAULT_DIR / "merged" / "merge_decisions.json", [])
    essence_report = read_json(VAULT_DIR / "essence" / "essence_report.json", {})
    strict_report = read_json(VAULT_DIR / "essence" / "essence_strict_report.json", {})

    nodes = merged_graph.get("nodes", [])
    edges = edge_items(merged_graph)
    selected_ids, selected_edges = select_readable_subgraph(nodes, edges)
    node_by_id = {node.get("id"): node for node in nodes}
    decision_index = build_decision_index(decisions)
    incident_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in selected_edges:
        incident_by_node[edge["source"]].append(edge)
        incident_by_node[edge["target"]].append(edge)

    graph_nodes = []
    for node_id in selected_ids:
        raw = node_by_id.get(node_id, {"id": node_id, "label": node_id})
        label = clean_label(raw.get("label", node_id))
        books = node_books(node_id, incident_by_node[node_id])
        decision = first_decision(node_id, decision_index)
        graph_nodes.append(
            {
                "id": node_id,
                "name": label,
                "val": min(26, 7 + len(incident_by_node[node_id])),
                "type": "merged" if len(books) > 1 or decision else "single",
                "source": ", ".join(book.split("_")[0] for book in books) if books else "global",
                "books": [BOOK_LABELS.get(book, book) for book in books],
                "essence": decision.get("rationale", "") if decision else f"{label} 是整合图谱中的知识节点，可继续查看其邻接关系与来源教材。",
                "reasoning": decision.get("rationale", "由 01-04 管线自动抽取、合并并纳入可视化图谱。") if decision else "由单本图谱与跨教材合并结果生成。",
                "decisionId": decision.get("decision_id") if decision else None,
                "confidence": decision.get("confidence") if decision else None,
            }
        )

    graph_links = [
        {
            "source": edge["source"],
            "target": edge["target"],
            "label": RELATION_LABELS.get(edge.get("relation", ""), edge.get("relation", "")),
            "type": RELATION_LABELS.get(edge.get("relation", ""), edge.get("relation", "")),
            "books": [BOOK_LABELS.get(book, book) for book in edge.get("books", [])],
        }
        for edge in selected_edges
    ]

    graph_nodes.sort(key=lambda node: node["val"], reverse=True)

    quality_files = sorted((VAULT_DIR / "graphs").glob("*.quality.json"))
    single_book_quality = [read_json(path, {}) for path in quality_files]
    graph_summary = {
        "nodes": len(nodes),
        "edges": len(edges),
        "visibleNodes": len(graph_nodes),
        "visibleEdges": len(graph_links),
        "relationCounts": relation_counts(edges),
        "singleBookGraphs": len(single_book_quality),
        "singleBookCycles": sum(len(item.get("prerequisite_cycles", [])) for item in single_book_quality),
    }

    essence = compact_essence_report(essence_report, strict_report)

    return {
        "generatedAt": "2026-05-10",
        "pipeline": [
            {"id": "01", "name": "多源教材加载", "status": "done", "detail": "PDF/MD/Word/Excel 统一加载为 Section + Markdown。"},
            {"id": "02", "name": "单本知识图谱", "status": "done", "detail": f"{graph_summary['singleBookGraphs']} 本教材图谱已生成，前置依赖环路 {graph_summary['singleBookCycles']}。"},
            {"id": "03", "name": "跨教材整合", "status": "done", "detail": f"{merge_report.get('merge_count', 0)} 条合并决策，{merge_report.get('conflict_count', 0)} 条冲突。"},
            {"id": "04", "name": "30% 精华提纯", "status": "done" if essence["targetMet"] else "warning", "detail": f"当前交付压缩比 {essence['compressionRatio'] * 100:.1f}%。"},
        ],
        "metrics": {
            "totalBooks": merge_report.get("total_books", 7),
            "nodesBefore": merge_report.get("total_nodes_before", 0),
            "nodesAfter": merge_report.get("total_nodes_after", graph_summary["nodes"]),
            "edgesAfter": merge_report.get("total_edges_after", graph_summary["edges"]),
            "mergeCount": merge_report.get("merge_count", 0),
            "conflictCount": merge_report.get("conflict_count", 0),
            "complementCount": merge_report.get("complement_count", 0),
            "dedupRatio": merge_report.get("dedup_ratio", 0),
            "compressionRatio": essence["compressionRatio"],
            "rawCompressionRatio": essence["rawCompressionRatio"],
            "compressionTargetMet": essence["targetMet"],
        },
        "graph": {"nodes": graph_nodes, "links": graph_links},
        "graphSummary": graph_summary,
        "essence": essence,
        "decisions": decisions[:80],
    }


def main() -> None:
    output_path = ROOT / "frontend" / "src" / "lib" / "agentData.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_agent_data()
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Exported frontend data: {len(data['graph']['nodes'])} nodes, "
        f"{len(data['graph']['links'])} links -> {output_path}"
    )


if __name__ == "__main__":
    main()
