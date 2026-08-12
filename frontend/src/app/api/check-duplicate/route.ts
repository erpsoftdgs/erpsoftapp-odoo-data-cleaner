import { NextResponse } from 'next/server';
import { getSession } from '@/lib/auth';
import db from '@/lib/db';

// Use Node.js runtime to access SQLite (db.ts)
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const hash = searchParams.get('hash');

  if (!hash) {
    return NextResponse.json({ error: 'Missing hash parameter' }, { status: 400 });
  }

  try {
    const existing = db
      .prepare('SELECT user_email FROM conversions WHERE file_hash = ? LIMIT 1')
      .get(hash) as { user_email: string } | undefined;

    if (existing) {
      return NextResponse.json({ 
        duplicate: true, 
        cleaned_by: existing.user_email 
      });
    }

    return NextResponse.json({ duplicate: false });
  } catch (error) {
    console.error('Error checking for duplicate file:', error);
    return NextResponse.json({ error: 'Database error' }, { status: 500 });
  }
}
