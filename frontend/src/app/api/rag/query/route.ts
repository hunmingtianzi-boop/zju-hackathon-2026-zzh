import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';

interface Citation {
  source: string;
  chapter: string;
  page: string;
  snippet: string;
  score: number;
}

interface RagResult {
  question: string;
  answer: string;
  citations: Citation[];
  total_chunks_searched: number;
}

function callPythonRag(question: string, topK: number): Promise<RagResult> {
  return new Promise((resolve, reject) => {
    const projectRoot = path.resolve(process.cwd(), '..');
    const scriptPath = path.join(projectRoot, 'rag_query.py');
    const args = [scriptPath, question, '--top-k', String(topK)];

    const proc = spawn('python', args, {
      cwd: projectRoot,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data: Buffer) => {
      stdout += data.toString('utf-8');
    });

    proc.stderr.on('data', (data: Buffer) => {
      stderr += data.toString('utf-8');
    });

    // Timeout after 60s
    const timer = setTimeout(() => {
      proc.kill();
      reject(new Error('RAG subprocess timed out after 60s'));
    }, 60000);

    proc.on('close', (code: number) => {
      clearTimeout(timer);
      if (code === 0) {
        try {
          resolve(JSON.parse(stdout) as RagResult);
        } catch {
          reject(new Error(`Failed to parse RAG output: ${stdout.slice(0, 200)}`));
        }
      } else {
        reject(new Error(`Python exited ${code}: ${stderr.slice(0, 300)}`));
      }
    });

    proc.on('error', (err: Error) => {
      clearTimeout(timer);
      reject(new Error(`Failed to spawn Python: ${err.message}`));
    });
  });
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { question, top_k = 5 } = body;

    if (!question || question.trim().length === 0) {
      return NextResponse.json(
        { error: 'Question is required' },
        { status: 400 }
      );
    }

    // Attempt to proxy to Python backend
    try {
      const res = await fetch(`${BACKEND_URL}/api/rag/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, top_k }),
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        return NextResponse.json(await res.json());
      }
    } catch {
      console.warn('Backend /api/rag/query not reachable, trying local Python.');
    }

    // Local Python subprocess
    try {
      const result = await callPythonRag(question.trim(), top_k);
      return NextResponse.json(result);
    } catch (pythonError) {
      console.error('Python RAG failed:', pythonError);
      return NextResponse.json({
        answer: `[RAG 离线] 针对「${question}」，当前检索引擎暂时不可用。请运行 python search_engine.py 构建索引后重试。`,
        citations: [],
      });
    }
  } catch (error) {
    console.error('RAG API Error:', error);
    return NextResponse.json(
      { error: 'Internal Server Error' },
      { status: 500 }
    );
  }
}
