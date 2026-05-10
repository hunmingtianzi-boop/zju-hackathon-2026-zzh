import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';

interface FeedbackBody {
  nodeId: string;
  nodeName?: string;
  decisionId?: string;
  feedback: string;
}

export async function POST(request: Request) {
  try {
    const body: FeedbackBody = await request.json();
    const { nodeId, nodeName = '', decisionId = '', feedback } = body;

    if (!feedback || feedback.trim().length === 0) {
      return NextResponse.json({ success: false, message: 'Feedback text is required' }, { status: 400 });
    }

    // Try remote backend first
    try {
      const res = await fetch(`${BACKEND_URL}/api/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        return NextResponse.json(await res.json());
      }
    } catch {
      console.warn("Backend /api/feedback not reachable, using local fallback.");
    }

    // ── Local fallback: write log + update merge_decisions ────

    const projectRoot = path.resolve(process.cwd(), '..');

    // 1. Write feedback log
    const feedbackEntry = {
      timestamp: new Date().toISOString(),
      nodeId,
      nodeName,
      decisionId,
      feedback,
    };

    const logPath = path.join(projectRoot, 'teacher_feedback.log');
    let existingLogs: object[] = [];
    if (fs.existsSync(logPath)) {
      try {
        const raw = fs.readFileSync(logPath, 'utf-8');
        existingLogs = raw.trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
      } catch {}
    }
    existingLogs.push(feedbackEntry);
    fs.writeFileSync(logPath, existingLogs.map(e => JSON.stringify(e)).join('\n') + '\n');

    // 2. Update merge_decisions.json with teacher feedback
    let decisionsUpdated = 0;
    const decisionsPath = path.join(projectRoot, '生医黑客松', 'merged', 'merge_decisions.json');
    if (decisionId && fs.existsSync(decisionsPath)) {
      try {
        const raw = fs.readFileSync(decisionsPath, 'utf-8');
        const decisions = JSON.parse(raw);
        if (Array.isArray(decisions)) {
          for (const dec of decisions) {
            if (dec.decision_id === decisionId) {
              dec.teacher_feedback = feedback;
              dec.resolved = true;
              dec.resolution = `教师反馈 (${new Date().toISOString().slice(0, 16).replace('T', ' ')}): ${feedback.slice(0, 120)}`;
              dec.status = 'reviewed';
              decisionsUpdated++;
            }
          }
          if (decisionsUpdated) {
            fs.writeFileSync(decisionsPath, JSON.stringify(decisions, null, 2), 'utf-8');
          }
        }
      } catch (e) {
        console.error('Failed to update merge_decisions:', e);
      }
    }

    return NextResponse.json({
      success: true,
      message: decisionsUpdated > 0
        ? `Feedback recorded and applied to ${decisionsUpdated} merge decision(s)`
        : 'Feedback recorded (no matching decision ID found)',
      decisionsUpdated,
      totalFeedbackEntries: existingLogs.length,
    });
  } catch (error) {
    console.error('Feedback API Error:', error);
    return NextResponse.json({ success: false, message: 'Failed to record feedback' }, { status: 500 });
  }
}
