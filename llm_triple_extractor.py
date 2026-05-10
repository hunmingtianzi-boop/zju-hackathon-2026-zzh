"""LLM Triple Extractor — few-shot demonstration.

Runs a single-chunk LLM extraction with a few-shot medical knowledge prompt
and saves the output to 生医黑客松/graphs/llm_sample.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from llm_client import chat

FEWSHOT_PROMPT = """你是一位医学知识工程师。从以下医学教材段落中提取核心知识点，输出为结构化三元组 JSON 数组。

## 关系类型（四选一）
- prerequisite（前置依赖）：A 是学习/理解 B 的前提
- parallel（并列关系）：A 与 B 同级、同类
- containment（包含关系）：A 包含 B
- application（应用关系）：A 的知识应用于 B

## Few-Shot 示例

段落：细胞受到刺激后，膜电位发生一次快速而可逆的倒转，称为动作电位。在此之前，细胞处于静息电位状态。

输出：
[
  {"subject": "动作电位", "relation": "prerequisite", "object": "静息电位", "evidence": "在此之前，细胞处于静息电位状态"},
  {"subject": "细胞", "relation": "containment", "object": "动作电位", "evidence": "细胞受到刺激后，膜电位发生一次快速而可逆的倒转，称为动作电位"}
]

段落：免疫系统由T细胞和B细胞组成。抗体在体液免疫中发挥关键作用。

输出：
[
  {"subject": "免疫系统", "relation": "containment", "object": "T细胞", "evidence": "免疫系统由T细胞和B细胞组成"},
  {"subject": "免疫系统", "relation": "containment", "object": "B细胞", "evidence": "免疫系统由T细胞和B细胞组成"},
  {"subject": "T细胞", "relation": "parallel", "object": "B细胞", "evidence": "免疫系统由T细胞和B细胞组成"},
  {"subject": "抗体", "relation": "application", "object": "体液免疫", "evidence": "抗体在体液免疫中发挥关键作用"}
]

## 规则
1. 每个三元组必须包含 subject、relation（四选一）、object、evidence（原文证据句）
2. 每 chunk 提取 3-8 个三元组
3. subject 和 object 必须是具体的医学概念，长度 2-25 字
4. evidence 必须从原文中直接引用
5. 跳过前言、致谢、编委名单等非知识内容——若段落无实质医学知识，返回空数组
6. 严格输出 JSON 数组，不要输出任何其他内容

## 教材段落
{chunk_text}

请输出 JSON 数组："""


def run_sample(chunks_dir: str = "生医黑客松/chunks", book: str = "03_生理学"):
    book_dir = Path(chunks_dir) / book
    chunks = sorted(book_dir.glob("*.md"))
    
    results = []
    sample_count = 0
    
    for chunk_path in chunks:
        if sample_count >= 5:
            break
        
        markdown = chunk_path.read_text(encoding="utf-8")
        if len(markdown) < 200:
            continue  # Skip too-short chunks (preface/TOC)
        
        chunk_text = markdown[:2000]
        prompt = FEWSHOT_PROMPT.format(chunk_text=chunk_text)
        
        print(f"[LLM] Extracting: {chunk_path.name} ({len(chunk_text)} chars)...")
        response = chat(prompt, system="你是专业医学知识工程师。请严格输出JSON。", temperature=0.1)
        
        if not response:
            continue
        
        try:
            # Try to parse JSON array from response
            import re
            json_match = re.search(r"\[[\s\S]*\]", response)
            if json_match:
                triples = json.loads(json_match.group(0))
                for t in triples:
                    t["source_chunk"] = chunk_path.name
                    t["book"] = book
                results.extend(triples)
                sample_count += 1
                print(f"  → {len(triples)} triples extracted")
            else:
                print(f"  → No JSON array found in response")
        except json.JSONDecodeError as e:
            print(f"  → JSON parse error: {e}")
    
    # Save sample
    sample_path = Path("生医黑客松/graphs/llm_sample.json")
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    sample_path.write_text(
        json.dumps({
            "description": f"LLM triple extraction sample ({len(results)} triples from {sample_count} chunks)",
            "prompt_type": "few-shot",
            "model": "deepseek-chat",
            "triples": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    print(f"\nSaved {len(results)} triples to {sample_path}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", default="03_生理学")
    parser.add_argument("--chunks-dir", default="生医黑客松/chunks")
    args = parser.parse_args()
    run_sample(args.chunks_dir, args.book)
