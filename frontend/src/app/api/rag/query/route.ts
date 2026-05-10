import { NextResponse } from 'next/server';
import agentDataRaw from '@/lib/agentData.json';

interface Citation {
  source: string;
  chapter: string;
  page: string;
  snippet: string;
  score: number;
}

function kgSearch(question: string, topK: number): Citation[] {
  const nodes = (agentDataRaw as any).graph?.nodes || [];
  const results: { node: any; score: number }[] = [];
  const terms = question.split(/[\s，,、]+/).filter((t: string) => t.length >= 1);
  const q = question.toLowerCase();

  for (const node of nodes) {
    const name = (node.name || '').toLowerCase();
    const essence = (node.essence || '').toLowerCase();
    const books = (node.books || []).join(' ').toLowerCase();
    const haystack = `${name} ${essence} ${books}`;

    let score = 0;

    // Keyword match (highest weight for name match)
    for (const term of terms) {
      if (term.length < 1) continue;
      if (name.includes(term)) score += term.length >= 2 ? 8 : 4;
      else if (essence.includes(term)) score += 3;
    }

    // Full question match in name
    if (name.includes(q)) score += 10;

    // CJK character overlap
    const qChars = [...q].filter((c: string) => /[\u4e00-\u9fff]/.test(c));
    if (qChars.length >= 2) {
      const overlap = qChars.filter((c: string) => haystack.includes(c)).length / qChars.length;
      score += overlap * 4;
    }

    // Boost merged + high-value nodes
    if (node.type === 'merged') score *= 1.4;
    if ((node.val || 0) > 10) score *= 1.3;

    if (score > 1) results.push({ node, score });
  }

  results.sort((a, b) => b.score - a.score);

  return results.slice(0, topK).map(r => {
    // Use best available snippet text
    const ess = r.node.essence || '';
    const rea = r.node.reasoning || '';
    const isNoiseSnippet = ess.includes('是整合图谱中的知识节点') || ess.includes('语义相似度');
    const isNoiseReasoning = rea.includes('由单本图谱与跨教材合并结果生成');
    
    let snippet = '';
    if (ess && !isNoiseSnippet) snippet = ess;
    else if (rea && !isNoiseReasoning) snippet = rea;
    else snippet = `来自「${(r.node.books || ['整合图谱']).join('、')}」，在图谱中可查看其邻接关系与原文出处。`;

    return {
      source: (r.node.books || ['整合图谱']).join(' / '),
      chapter: r.node.name || '',
      page: '',
      snippet,
      score: Math.min(r.score / 15, 1),
    };
  });
}

export async function POST(request: Request) {
  try {
    const { question, top_k = 5 } = await request.json();
    if (!question?.trim()) {
      return NextResponse.json({ error: 'Question is required' }, { status: 400 });
    }

    const citations = kgSearch(question.trim(), top_k);

    const answer = citations.length
      ? `围绕「${question}」，检索到 ${citations.length} 条关联知识点（详见引用来源）。`
      : `针对「${question}」，图谱中暂无直接匹配。建议尝试：发热机制、炎症反应、心功能、病毒感染等术语。`;

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
