import { NextResponse } from 'next/server';
import { getSession } from '@/lib/auth';
import db from '@/lib/db';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: 'You must be signed in to submit a rating.' }, { status: 401 });
  }

  try {
    const body = await request.json();
    const rating = Number(body.rating);
    const feedback = typeof body.feedback === 'string' ? body.feedback.trim() : null;
    const conversionId = body.conversionId ? Number(body.conversionId) : null;

    if (!rating || rating < 1 || rating > 5) {
      return NextResponse.json({ error: 'Rating must be between 1 and 5.' }, { status: 400 });
    }

    db.prepare(
      `INSERT INTO ratings (conversion_id, user_email, rating, feedback, created_at)
       VALUES (?, ?, ?, ?, ?)`
    ).run(conversionId, session.email, rating, feedback || null, Date.now());

    return NextResponse.json({ success: true });
  } catch (error: unknown) {
    console.error('Failed to save rating:', error);
    return NextResponse.json(
      { error: 'An error occurred while saving your rating.' },
      { status: 500 }
    );
  }
}
