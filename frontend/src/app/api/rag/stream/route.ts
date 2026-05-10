import agentDataRaw from '@/lib/agentData.json';

function kgSearch(question: string, topK: number) {
  const nodes = (agentDataRaw as any).graph?.nodes || [];
  const results: { node: any; score: number }[] = [];
  const terms = question.split(/[\s，,、]+/).filter((t: string) => t.length >= 1);
  const q = question.toLowerCase();

  for (const node of nodes) {
    const name = (node.name || '').toLowerCase();
    const essence = (node.essence || '').toLowerCase();
    const haystack = `${name} ${essence}`;
    let score = 0;
    for (const term of terms) {
      if (term.length < 1) continue;
      if (name.includes(term)) score += term.length >= 2 ? 8 : 4;
      else if (essence.includes(term)) score += 3;
    }
    if (name.includes(q)) score += 10;
    const qChars = [...q].filter((c: string) => /[\u4e00-\u9fff]/.test(c));
    if (qChars.length >= 2) {
      const overlap = qChars.filter((c: string) => haystack.includes(c)).length / qChars.length;
      score += overlap * 4;
    }
    if (node.type === 'merged') score *= 1.4;
    if ((node.val || 0) > 10) score *= 1.3;
    if (score > 1) results.push({ node, score });
  }
  results.sort((a, b) => b.score - a.score);
  return results.slice(0, topK).map(r => ({
    source: (r.node.books || ['整合图谱']).join(' / '),
    chapter: r.node.name || '',
    snippet: (r.node.essence && !r.node.essence.includes('是整合图谱中的知识节点') && !r.node.essence.includes('语义相似度'))
      ? r.node.essence
      : `来自「${(r.node.books || ['整合图谱']).join('、')}」的知识节点`,
    score: Math.min(r.score / 15, 1),
  }));
}

export async function POST(request: Request) {
  try {
    const { question, top_k = 5 } = await request.json();
    if (!question?.trim()) {
      return new Response('{"error":"Question is required"}', { status: 400 });
    }

    const citations = kgSearch(question.trim(), top_k);
    const apiKey = process.env.DEEPSEEK_API_KEY;

    // Build context for LLM
    const context = citations.slice(0, 5).map((c, i) =>
      `[${i + 1}] 《${c.source}》${c.chapter}: ${c.snippet?.slice(0, 200)}`
    ).join('\n');

    const prompt = `根据以下教材知识点回答用户问题。引用时标注 [1][2]。只基于知识点回答，不要编造。\n\n知识点:\n${context}\n\n问题: ${question}\n回答:`;

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        try {
          // First chunk: citations metadata
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'citations', citations })}\n\n`));

          if (!apiKey) {
            // No API key, send local answer
            const answer = citations.length
              ? `围绕「${question}」，图谱定位到 ${citations.length} 个关联知识点。详见上方引用来源。`
              : '未找到直接匹配。';
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'token', token: answer })}\n\n`));
            controller.enqueue(encoder.encode('data: [DONE]\n\n'));
            controller.close();
            return;
          }

          // Stream from DeepSeek
          const res = await fetch('https://api.deepseek.com/v1/chat/completions', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${apiKey}`,
            },
            body: JSON.stringify({
              model: 'deepseek-chat',
              messages: [{ role: 'user', content: prompt }],
              temperature: 0.3,
              max_tokens: 1024,
              stream: true,
            }),
            signal: AbortSignal.timeout(30000),
          });

          if (!res.ok) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'token', token: '[LLM 暂不可用]' })}\n\n`));
            controller.enqueue(encoder.encode('data: [DONE]\n\n'));
            controller.close();
            return;
          }

          const reader = res.body?.getReader();
          if (!reader) {
            controller.close();
            return;
          }

          const decoder = new TextDecoder();
          let buffer = '';
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed.startsWith('data: ')) continue;
              const data = trimmed.slice(6);
              if (data === '[DONE]') continue;
              try {
                const parsed = JSON.parse(data);
                const token = parsed.choices?.[0]?.delta?.content;
                if (token) {
                  controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'token', token })}\n\n`));
                }
              } catch {}
            }
          }
        } catch (e) {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'error', message: 'Stream failed' })}\n\n`));
        }
        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        controller.close();
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  } catch (error) {
    return new Response('{"error":"Internal Server Error"}', { status: 500 });
  }
}
