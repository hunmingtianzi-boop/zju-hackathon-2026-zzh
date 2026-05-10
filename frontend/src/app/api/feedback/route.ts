import { NextResponse } from 'next/server';

const feedbackLog: Array<{
  timestamp: string;
  nodeId: string;
  nodeName: string;
  decisionId: string;
  feedback: string;
}> = [];

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { nodeId, nodeName = '', decisionId = '', feedback } = body;

    if (!feedback || feedback.trim().length === 0) {
      return NextResponse.json({ success: false, message: 'Feedback text is required' }, { status: 400 });
    }

    const entry = {
      timestamp: new Date().toISOString(),
      nodeId,
      nodeName,
      decisionId,
      feedback: feedback.trim(),
    };

    feedbackLog.push(entry);

    // In production, this would write to a database or merge_decisions.json.
    // Vercel serverless is ephemeral — feedback persists only during function lifetime.
    return NextResponse.json({
      success: true,
      message: `反馈已记录。节点「${nodeName || nodeId}」的整合建议已标记为已审核。`,
      entry,
      note: 'Feedback logged in-memory. For persistent storage, connect a database or run Python backend locally.',
    });
  } catch (error) {
    console.error('Feedback API Error:', error);
    return NextResponse.json({ success: false, message: 'Failed to record feedback' }, { status: 500 });
  }
}
