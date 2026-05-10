"""RAG query helper — called by the Next.js /api/rag route via subprocess.

Returns top-K search results with full citations (source, chapter, page, snippet)
so the frontend can display evidence-backed answers even without LLM generation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from search_engine import MedicalSearchEngine


def rag_query(question: str, top_k: int = 5) -> dict:
    engine = MedicalSearchEngine()
    engine.load(str(ROOT / "medical_index"))

    results = engine.search(question, top_k=top_k, alpha=0.5)

    citations = []
    for res in results:
        # Parse path like "生医黑客松/chunks/03_生理学/第一章绪论_第一节_调节.md"
        path = res["path"]
        parts = Path(path).parts
        book = parts[-2] if len(parts) >= 2 else ""
        chunk_name = Path(path).stem

        # Extract page info from chunk filename if present
        page = ""
        if "_" in chunk_name:
            segments = chunk_name.split("_")
            for seg in segments:
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

    # Construct a summary from top results
    summary_parts = []
    for c in citations[:3]:
        summary_parts.append(f"《{c['source']}》{c['chapter']}: {c['snippet'][:120]}...")

    answer = (
        f"针对「{question}」，在 7 本教材的 1,295 个语义块中检索到 {len(citations)} 条相关段落。"
        f"\n\n最相关来源：\n" + "\n".join(f"- {p}" for p in summary_parts)
        + f"\n\n（注：当前为检索结果直出，接入 LLM API 后可生成自然语言回答。）"
    )

    return {
        "question": question,
        "answer": answer,
        "citations": citations,
        "total_chunks_searched": len(engine.chunks),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="+")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    result = rag_query(" ".join(args.question), args.top_k)
    print(json.dumps(result, ensure_ascii=False, indent=2))
