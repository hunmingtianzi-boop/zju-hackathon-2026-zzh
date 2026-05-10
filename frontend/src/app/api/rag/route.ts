import { NextResponse } from 'next/server';

// Pre-load agent data for in-memory search
import agentDataRaw from '@/lib/agentData.json';

interface Citation {
  source: string;
  chapter: string;
  snippet: string;
  score: number;
}

interface RagResponse {
  question: string;
  answer: string;
  citations: Citation[];
  total_chunks_searched: number;
  method: 'llm' | 'local';
}

function kgSearch(question: string, topK: number): Citation[] {
  const nodes = (agentDataRaw as any).graph?.nodes || [];
  const results: { node: any; score: number }[] = [];

  for (const node of nodes) {
    const haystack = `${node.name || ''} ${node.essence || ''} ${node.reasoning || ''} ${(node.books || []).join(' ')}`.toLowerCase();
    const q = question.toLowerCase();
    let score = 0;
    if (node.name?.includes(q)) score += 4;
    if (haystack.includes(q)) score += 1;
    const charOverlap = [...q].filter(c => haystack.includes(c)).length / Math.max(q.length, 1);
    score += charOverlap * 2;
    if (score > 0) results.push({ node, score });
  }

  results.sort((a, b) => b.score - a.score);

  return results.slice(0, topK).map(r => ({
    source: (r.node.books || ['整合图谱']).join(' / '),
    chapter: r.node.name || '',
    snippet: r.node.essence || r.node.reasoning || '',
    score: Math.min(r.score / 8, 1),
  }));
}

function localAnswer(question: string, citations: Citation[]): string {
  if (!citations.length) {
    return `针对「${question}」，当前知识图谱中未找到直接匹配的知识点。建议尝试更具体的医学概念，或在本地运行 python search_engine.py 做全库检索。`;
  }
  const top = citations.slice(0, 3).map((c, i) =>
    `[${i + 1}] ${c.source} · ${c.chapter}\n   ${c.snippet?.slice(0, 150)}`
  ).join('\n\n');
  return `围绕「${question}」，图谱定位到 ${citations.length} 个关联知识点：\n\n${top}\n\n（注：当前为图谱检索结果。接入 LLM API 后可生成自然语言回答。）`;
}

async function llmAnswer(question: string, citations: Citation[]): Promise<string | null> {
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey || !citations.length) return null;

  const context = citations.slice(0, 5).map((c, i) =>
    `[${i + 1}] 来源：${c.source}，${c.chapter}\n内容：${c.snippet?.slice(0, 300)}`
  ).join('\n\n');

  const prompt = `你是一位医学教学助手。根据以下教材知识点回答用户问题。\n规则：1) 只基于提供的知识点回答，不要编造；2) 引用时标注来源编号如 [1][2]；3) 如果不足以回答，明确说明。\n\n## 知识点\n${context}\n\n## 用户问题\n${question}\n\n请回答：`;

  try {
    const res = await fetch('https://api.deepseek.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: 'deepseek-chat',
        messages: [
          { role: 'system', content: '你是专业医学教学助手。请用中文回答。' },
          { role: 'user', content: prompt },
        ],
        temperature: 0.3,
        max_tokens: 1024,
        stream: false,
      }),
      signal: AbortSignal.timeout(15000),
    });

    if (!res.ok) return null;
    const data = await res.json();
    return data.choices?.[0]?.message?.content || null;
  } catch {
    return null;
  }
}

export async function POST(request: Request) {
  try {
    const { question, top_k = 5 } = await request.json();

    if (!question || question.trim().length === 0) {
      return NextResponse.json({ success: false, message: 'Question is required' }, { status: 400 });
    }

    const citations = kgSearch(question.trim(), top_k);

    // Try LLM generation, fallback to local
    const llmResult = await llmAnswer(question.trim(), citations);
    const answer = llmResult || localAnswer(question.trim(), citations);

    return NextResponse.json({
      question: question.trim(),
      answer,
      citations,
      total_chunks_searched: (agentDataRaw as any).graph?.nodes?.length || 0,
      method: llmResult ? 'llm' : 'local',
    } as RagResponse);
  } catch (error) {
    console.error('RAG API Error:', error);
    return NextResponse.json({ success: false, message: 'Internal server error' }, { status: 500 });
  }
}
