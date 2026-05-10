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


def _generate_llm_answer(question: str, citations: list[dict]) -> str:
    """Generate an evidence-backed answer using DeepSeek API."""
    from llm_client import chat

    context_parts = []
    for i, c in enumerate(citations[:5], 1):
        context_parts.append(
            f"[{i}] 来源：《{c['source']}》，{c['chapter']}（第{c['page']}页）\n"
            f"内容：{c['snippet']}"
        )
    context = "\n\n".join(context_parts)

    prompt = (
        f"你是一位医学教学助手。根据以下教材原文回答用户问题。\n"
        f"规则：1) 只基于提供的原文回答，不要编造；2) 引用时标注来源编号如 [1][2]；"
        f"3) 如果原文不足以回答，明确说明。\n\n"
        f"## 教材原文\n{context}\n\n"
        f"## 用户问题\n{question}\n\n"
        f"请回答："
    )

    llm_answer = chat(prompt, temperature=0.3)
    if not llm_answer:
        summary_parts = []
        for c in citations[:3]:
            summary_parts.append(f"《{c['source']}》{c['chapter']}: {c['snippet'][:120]}...")
        return (
            f"针对「{question}」，在 7 本教材中检索到 {len(citations)} 条相关段落。"
            f"\n\n（LLM 暂不可用，检索结果直出）：\n" + "\n".join(f"- {p}" for p in summary_parts)
        )
    return llm_answer


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

    # Generate LLM answer with citations
    answer = _generate_llm_answer(question, citations) if citations else (
        f"针对「{question}」，在 7 本教材的 1,295 个语义块中未找到足够相关的内容。"
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
