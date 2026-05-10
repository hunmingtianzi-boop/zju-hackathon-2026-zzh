import { NextResponse } from 'next/server';
import agentDataRaw from '@/lib/agentData.json';

interface Citation {
  source: string;
  chapter: string;
  snippet: string;
  score: number;
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
    page: '',
    snippet: r.node.essence || r.node.reasoning || '',
    score: Math.min(r.score / 8, 1),
  }));
}

export async function POST(request: Request) {
  try {
    const { question, top_k = 5 } = await request.json();
    if (!question?.trim()) {
      return NextResponse.json({ error: 'Question is required' }, { status: 400 });
    }

    const citations = kgSearch(question.trim(), top_k);
    const top = citations.slice(0, 3).map((c, i) =>
      `[${i + 1}] ${c.source} · ${c.chapter}\n   ${c.snippet?.slice(0, 150)}`
    ).join('\n\n');

    const answer = citations.length
      ? `围绕「${question}」，图谱定位到 ${citations.length} 个关联知识点：\n\n${top}`
      : `针对「${question}」，当前知识图谱中未找到直接匹配的知识点。`;

    return NextResponse.json({
      question: question.trim(),
      answer,
      citations,
      total_chunks_searched: (agentDataRaw as any).graph?.nodes?.length || 0,
    });
  } catch (error) {
    console.error('RAG Query Error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
