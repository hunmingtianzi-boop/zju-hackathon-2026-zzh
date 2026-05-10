from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from export_frontend_data import build_agent_data


ROOT = Path(__file__).resolve().parent
VAULT_DIR = ROOT / "生医黑客松"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class AgentPaths:
    chunks_dir: Path = VAULT_DIR / "chunks"
    graphs_dir: Path = VAULT_DIR / "graphs"
    merged_dir: Path = VAULT_DIR / "merged"
    essence_dir: Path = VAULT_DIR / "essence"
    frontend_data: Path = ROOT / "frontend" / "src" / "lib" / "agentData.json"


class KIAAgent:
    """统一智能体入口 —— 编排 01-04 流水线 + 检索 + 反馈闭环 + 前端导出。

    用法:
        agent = KIAAgent()
        agent.status()                  # 全管线状态快照
        agent.rebuild()                 # 重建 02→03→04→export
        agent.search("二尖瓣狭窄")       # BM25+FAISS 混合检索
        agent.query("心功能不全")         # 图谱匹配 + 检索合并
        agent.feedback(node_id=..., feedback=...)  # 教师反馈闭环
        agent.export_frontend_data()    # 导出 agentData.json
    """

    def __init__(self, paths: AgentPaths | None = None):
        self.paths = paths or AgentPaths()
        self._search_engine = None

    # ── search engine (lazy-load) ──────────────────────────────

    @property
    def search_engine(self):
        if self._search_engine is None:
            from search_engine import MedicalSearchEngine
            engine = MedicalSearchEngine()
            index_meta = ROOT / "medical_index_meta.pkl"
            if index_meta.exists():
                engine.load(str(ROOT / "medical_index"))
            self._search_engine = engine
        return self._search_engine

    # ── status ─────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        data = build_agent_data()
        artifacts = {
            "chunks": len(list(self.paths.chunks_dir.rglob("*.md"))) if self.paths.chunks_dir.exists() else 0,
            "single_graph_files": len(list(self.paths.graphs_dir.glob("*.json"))) if self.paths.graphs_dir.exists() else 0,
            "merged_outputs": len(list(self.paths.merged_dir.glob("*.json"))) if self.paths.merged_dir.exists() else 0,
            "essence_outputs": len(list(self.paths.essence_dir.glob("*"))) if self.paths.essence_dir.exists() else 0,
            "frontend_data": self.paths.frontend_data.exists(),
            "search_index": (ROOT / "medical_index_meta.pkl").exists(),
            "feedback_log": (ROOT / "teacher_feedback.log").exists(),
        }
        data["artifacts"] = artifacts
        return data

    # ── rebuild ────────────────────────────────────────────────

    def rebuild(self, skip_expensive: bool = False) -> dict[str, Any]:
        self._run([sys.executable, "single_map_builder.py", "--chunks-dir", str(self.paths.chunks_dir), "--output-dir", str(self.paths.graphs_dir)])
        self._run([sys.executable, "cross_textbook_merger.py", "--graphs-dir", str(self.paths.graphs_dir), "--output-dir", str(self.paths.merged_dir)])
        if not skip_expensive:
            self._run([sys.executable, "essence_compressor.py", "--merged-graph", str(self.paths.merged_dir / "merged_graph.json"), "--merge-decisions", str(self.paths.merged_dir / "merge_decisions.json"), "--chunks-dir", str(self.paths.chunks_dir), "--output-dir", str(self.paths.essence_dir)])
        self.write_strict_essence()
        self.export_frontend_data()
        return self.status()

    # ── export ─────────────────────────────────────────────────

    def export_frontend_data(self) -> dict[str, Any]:
        data = build_agent_data()
        self.paths.frontend_data.parent.mkdir(parents=True, exist_ok=True)
        self.paths.frontend_data.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    # ── essence ────────────────────────────────────────────────

    def write_strict_essence(self, target_ratio: float = 0.30) -> dict[str, Any]:
        report_path = self.paths.essence_dir / "essence_report.json"
        essence_path = self.paths.essence_dir / "essence.md"
        if not report_path.exists() or not essence_path.exists():
            return {}

        report = json.loads(report_path.read_text(encoding="utf-8"))
        original_chars = int(report.get("original_chars", 0))
        budget = int(original_chars * target_ratio)
        if original_chars >= 10000:
            budget = max(2000, budget)
        content = essence_path.read_text(encoding="utf-8")
        compact = self._compact_essence_markdown(content, budget)

        strict_path = self.paths.essence_dir / "essence_strict.md"
        strict_path.write_text(compact, encoding="utf-8")
        strict_report = {
            **report,
            "compressed_chars": len(compact),
            "compression_ratio": len(compact) / max(original_chars, 1),
            "strict_budget_chars": budget,
            "summarization_method": f"{report.get('summarization_method', 'rule_based')}+strict_budget",
            "output": str(strict_path),
        }
        (self.paths.essence_dir / "essence_strict_report.json").write_text(
            json.dumps(strict_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return strict_report

    # ── search (BM25 + FAISS) ──────────────────────────────────

    def search(self, question: str, top_k: int = 5, alpha: float = 0.5) -> dict[str, Any]:
        """混合检索：BM25 关键词 + FAISS 语义，返回带引用的结果。"""
        engine = self.search_engine
        if not engine.chunks:
            engine.load_chunks(str(self.paths.chunks_dir))
            engine.build_bm25()
            engine.build_semantic()

        results = engine.search(question, top_k=top_k, alpha=alpha)

        citations = []
        for res in results:
            path = Path(res["path"])
            parts = path.parts
            book = parts[-2] if len(parts) >= 2 else ""
            chunk_name = path.stem
            page = ""
            if "_" in chunk_name:
                for seg in chunk_name.split("_"):
                    if seg.isdigit():
                        page = seg
                        break
            citations.append({
                "source": book,
                "chapter": chunk_name,
                "page": page,
                "snippet": res["content"][:300],
                "score": round(float(res["score"]), 3),
            })

        answer_lines = [f"针对「{question}」，在 {len(engine.chunks)} 个语义块中检索到 {len(citations)} 条结果。"]
        for i, c in enumerate(citations[:3], 1):
            answer_lines.append(f"\n{i}. 《{c['source']}》{c['chapter']} (score={c['score']})")
            answer_lines.append(f"   {c['snippet'][:150]}...")

        return {
            "question": question,
            "answer": "\n".join(answer_lines),
            "citations": citations,
            "total_chunks": len(engine.chunks),
        }

    # ── query (graph + search fusion) ──────────────────────────

    def query(self, question: str, limit: int = 8) -> dict[str, Any]:
        """查询融合：图谱节点匹配 + 语义块检索，两条通路互补。"""
        data = self.status()
        nodes = data["graph"]["nodes"]
        links = data["graph"]["links"]

        # Pathway A: graph node matching
        terms = [term for term in re.split(r"\s+", question.strip()) if term]
        scored = []
        for node in nodes:
            haystack = " ".join([
                node.get("name", ""),
                node.get("essence", ""),
                node.get("reasoning", ""),
                " ".join(node.get("books", [])),
            ])
            score = sum(3 if term in node.get("name", "") else 1 for term in terms if term in haystack)
            if score:
                scored.append((score, node))
        scored.sort(key=lambda item: (item[0], item[1].get("val", 0)), reverse=True)
        matches = [node for _, node in scored[:limit]]
        match_ids = {node["id"] for node in matches}
        related_links = [
            link for link in links
            if self._link_endpoint(link.get("source")) in match_ids or self._link_endpoint(link.get("target")) in match_ids
        ][:limit]

        # Pathway B: semantic chunk search (lazy — only when index exists)
        search_results = None
        try:
            idx_meta = ROOT / "medical_index_meta.pkl"
            if idx_meta.exists():
                search_results = self.search(question, top_k=limit)
        except Exception:
            pass

        return {
            "question": question,
            "graph_answer": self._compose_answer(question, matches, related_links, data),
            "graph_matches": matches,
            "graph_links": related_links,
            "search_results": search_results,
            "pipeline": data["pipeline"],
            "mode": "hybrid" if search_results else "graph_only",
        }

    def _compose_answer(
        self,
        question: str,
        matches: list[dict[str, Any]],
        links: list[dict[str, Any]],
        data: dict[str, Any],
    ) -> str:
        if not matches:
            return "当前可视图谱中没有找到直接命中的节点。可换一个更具体的医学概念，或在检索索引中扩展。"
        head = matches[0]
        relation_hint = ""
        if links:
            relation_hint = " 相关关系：" + "；".join(
                f"{self._link_endpoint(link.get('source'))} -{link.get('label')}→ {self._link_endpoint(link.get('target'))}"
                for link in links[:3]
            )
        compression = data["metrics"].get("compressionRatio", 0) * 100
        return (
            f"围绕「{question}」，图谱定位到「{head['name']}」。"
            f"{head.get('reasoning') or head.get('essence')}"
            f"{relation_hint} 精华压缩比约 {compression:.1f}%。"
        )

    # ── feedback loop ──────────────────────────────────────────

    def feedback(
        self,
        node_id: str,
        node_name: str = "",
        decision_id: str = "",
        feedback_text: str = "",
    ) -> dict[str, Any]:
        """教师反馈闭环：记录反馈 → 更新 merge_decisions.json → 重新导出前端数据。"""
        decisions_path = self.paths.merged_dir / "merge_decisions.json"

        # 1. Write feedback log
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodeId": node_id,
            "nodeName": node_name,
            "decisionId": decision_id,
            "feedback": feedback_text,
        }
        log_path = ROOT / "teacher_feedback.log"
        existing_logs: list[dict[str, Any]] = []
        if log_path.exists():
            try:
                existing_logs = [
                    json.loads(line)
                    for line in log_path.read_text(encoding="utf-8").strip().splitlines()
                    if line.strip()
                ]
            except Exception:
                existing_logs = []
        existing_logs.append(log_entry)
        log_path.write_text(
            "\n".join(json.dumps(entry, ensure_ascii=False) for entry in existing_logs) + "\n",
            encoding="utf-8",
        )

        # 2. Update merge_decisions.json with teacher feedback
        decisions_updated = 0
        if decisions_path.exists() and decision_id:
            try:
                decisions: list[dict[str, Any]] = json.loads(
                    decisions_path.read_text(encoding="utf-8")
                )
                for dec in decisions:
                    if dec.get("decision_id") == decision_id:
                        dec["teacher_feedback"] = feedback_text
                        dec["resolved"] = True
                        dec["resolution"] = f"教师反馈 ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}): {feedback_text[:120]}"
                        dec["status"] = "reviewed"
                        decisions_updated += 1
                if decisions_updated:
                    decisions_path.write_text(
                        json.dumps(decisions, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            except Exception as e:
                return {
                    "success": False,
                    "message": f"更新 merge_decisions 失败: {e}",
                }

        # 3. Re-export frontend data so the UI reflects changes
        try:
            self.export_frontend_data()
        except Exception:
            pass

        return {
            "success": True,
            "message": f"反馈已记录",
            "decisions_updated": decisions_updated,
            "total_feedback_entries": len(existing_logs),
            "node_id": node_id,
            "decision_id": decision_id,
        }

    # ── internal helpers ───────────────────────────────────────

    def _compact_essence_markdown(self, content: str, budget: int) -> str:
        without_details = re.sub(r"<details>.*?</details>", "", content, flags=re.S)
        without_details = re.sub(r"\n{3,}", "\n\n", without_details)
        lines = []
        used = 0
        for raw_line in without_details.splitlines():
            line = raw_line.rstrip()
            if line.startswith("*关联:"):
                continue
            accepted = False
            if line.startswith("### ") or line.startswith("**摘要**") or line.startswith("#") or line.startswith(">") or line.startswith("- ["):
                accepted = True
            elif not line.strip():
                accepted = True
            if not accepted:
                continue
            projected = used + len(line) + 1
            if projected >= budget:
                lines.append("")
                lines.append("> 已达到 30% 预算，后续低优先级条目省略。")
                break
            lines.append(line)
            used = projected
        compact = "\n".join(lines).strip() + "\n"
        if len(compact) > budget:
            note = "\n> 已达到 30% 预算，后续低优先级条目省略。\n"
            compact = compact[: max(0, budget - len(note))].rstrip() + note
        return compact

    def _run(self, command: list[str]) -> None:
        subprocess.run(command, cwd=ROOT, check=True)

    def _link_endpoint(self, value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("id", value.get("name", "")))
        return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="KIA 统一智能体 — 学科知识整合 Agent")
    sub = parser.add_subparsers(dest="command")

    # status
    sub.add_parser("status", help="全管线状态快照")

    # rebuild
    rebuild_p = sub.add_parser("rebuild", help="重建 02→03→04→export 全管线")
    rebuild_p.add_argument("--skip-expensive", action="store_true", help="跳过精华压缩阶段")

    # export
    sub.add_parser("export", help="导出前端数据 agentData.json")

    # strict-essence
    sub.add_parser("strict-essence", help="生成 ≤30% 严格精华版")

    # query
    query_p = sub.add_parser("query", help="图谱 + 检索 混合查询")
    query_p.add_argument("question", nargs="+", help="查询文本")
    query_p.add_argument("--limit", type=int, default=8, help="返回结果数量上限")

    # search
    search_p = sub.add_parser("search", help="BM25+FAISS 混合检索（语义块级别）")
    search_p.add_argument("question", nargs="+", help="检索问题")
    search_p.add_argument("--top-k", type=int, default=5, help="返回结果数")
    search_p.add_argument("--alpha", type=float, default=0.5, help="BM25 权重 (0-1)")

    # feedback
    fb_p = sub.add_parser("feedback", help="教师反馈闭环")
    fb_p.add_argument("--node-id", required=True, help="节点 ID")
    fb_p.add_argument("--node-name", default="", help="节点名称")
    fb_p.add_argument("--decision-id", default="", help="整合决策 ID")
    fb_p.add_argument("--text", required=True, help="反馈文本")

    args = parser.parse_args()
    agent = KIAAgent()

    if args.command == "status":
        print(json.dumps(agent.status(), ensure_ascii=False, indent=2))
    elif args.command == "rebuild":
        print(json.dumps(agent.rebuild(skip_expensive=args.skip_expensive), ensure_ascii=False, indent=2))
    elif args.command == "export":
        data = agent.export_frontend_data()
        print(f"Exported {len(data['graph']['nodes'])} nodes and {len(data['graph']['links'])} links.")
    elif args.command == "strict-essence":
        print(json.dumps(agent.write_strict_essence(), ensure_ascii=False, indent=2))
    elif args.command == "query":
        print(json.dumps(agent.query(" ".join(args.question), limit=args.limit), ensure_ascii=False, indent=2))
    elif args.command == "search":
        print(json.dumps(agent.search(" ".join(args.question), top_k=args.top_k, alpha=args.alpha), ensure_ascii=False, indent=2))
    elif args.command == "feedback":
        print(json.dumps(agent.feedback(
            node_id=args.node_id,
            node_name=args.node_name,
            decision_id=args.decision_id,
            feedback_text=args.text,
        ), ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
