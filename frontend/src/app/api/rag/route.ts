import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';

interface RagRequest {
  question: string;
  top_k?: number;
}

interface Citation {
  source: string;
  chapter: string;
  page: string;
  snippet: string;
  score: number;
}

interface RagResponse {
  question: string;
  answer: string;
  citations: Citation[];
  total_chunks_searched: number;
}

async function callPythonRag(question: string, topK: number): Promise<RagResponse> {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(process.cwd(), '..', 'rag_query.py');
    const args = [scriptPath, question, '--top-k', String(topK)];

    const proc = spawn('python', args, {
      cwd: path.join(process.cwd(), '..'),
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

    proc.on('close', (code: number) => {
      if (code === 0) {
        try {
          const result = JSON.parse(stdout) as RagResponse;
          resolve(result);
        } catch {
          reject(new Error(`Failed to parse RAG output: ${stdout.slice(0, 200)}`));
        }
      } else {
        reject(new Error(`RAG subprocess exited ${code}: ${stderr.slice(0, 300)}`));
      }
    });

    proc.on('error', (err: Error) => {
      reject(new Error(`Failed to spawn RAG subprocess: ${err.message}`));
    });

    // Timeout after 60s
    const timer = setTimeout(() => {
      proc.kill();
      reject(new Error('RAG subprocess timed out after 60s'));
    }, 60000);

    proc.on('close', () => clearTimeout(timer));
  });
}

function fallbackResponse(question: string): RagResponse {
  return {
    question,
    answer: `针对「${question}」，当前 RAG 检索引擎离线或索引文件未就绪。请先运行 python search_engine.py 构建索引，或检查 medical_index_faiss.index 是否存在。`,
    citations: [],
    total_chunks_searched: 0,
  };
}

export async function POST(request: Request) {
  try {
    const body: RagRequest = await request.json();
    const { question, top_k = 5 } = body;

    if (!question || question.trim().length === 0) {
      return NextResponse.json(
        { success: false, message: 'Question is required' },
        { status: 400 }
      );
    }

    // Try remote backend first
    try {
      const res = await fetch(`${BACKEND_URL}/api/rag`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, top_k }),
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        return NextResponse.json(await res.json());
      }
    } catch {
      console.warn('Backend /api/rag not reachable, using local Python subprocess.');
    }

    // Fallback: spawn local Python rag_query.py
    try {
      const result = await callPythonRag(question.trim(), top_k);
      return NextResponse.json(result);
    } catch (pythonError) {
      console.error('Python RAG subprocess failed:', pythonError);
      return NextResponse.json(fallbackResponse(question.trim()));
    }
  } catch (error) {
    console.error('RAG API Error:', error);
    return NextResponse.json(
      { success: false, message: 'Internal server error' },
      { status: 500 }
    );
  }
}
