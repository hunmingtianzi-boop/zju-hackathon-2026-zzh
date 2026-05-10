import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const files = formData.getAll('files') as File[];

    if (!files || files.length === 0) {
      return NextResponse.json({ success: false, message: 'No files uploaded' }, { status: 400 });
    }

    const uploaded = files.map(f => ({
      name: f.name,
      size: f.size,
      type: f.type || 'unknown',
    }));

    // On Vercel, filesystem is read-only. Real parsing requires Python backend.
    // Return file metadata so the frontend can display parsing status.
    return NextResponse.json({
      success: true,
      message: `${files.length} file(s) received. Real parsing requires Python backend (multi_source_loader.py) running locally.`,
      files: uploaded,
      note: 'Vercel serverless cannot run PyMuPDF/python-docx. For full parsing, run python kia_agent.py rebuild locally.',
    });
  } catch (error) {
    console.error('Upload Error:', error);
    return NextResponse.json({ success: false, message: 'Failed to process upload' }, { status: 500 });
  }
}
