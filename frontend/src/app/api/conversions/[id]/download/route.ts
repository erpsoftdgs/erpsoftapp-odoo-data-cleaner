import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { getSession, isAdminEmail } from '@/lib/auth';
import db, { OUTPUT_DIR } from '@/lib/db';

// Reads persisted files from disk, so this must run on the Node.js runtime.
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type ConversionRow = {
  id: number;
  user_email: string;
  filename: string;
  output_filename: string | null;
};

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  // Middleware already requires a session for non-public routes, but the
  // route must not rely on that alone — same pattern as /api/clean.
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: 'You must be signed in to use this.' }, { status: 401 });
  }

  const { id } = await params;
  const row = db.prepare('SELECT * FROM conversions WHERE id = ?').get(Number(id)) as unknown as
    | ConversionRow
    | undefined;
  if (!row) {
    return NextResponse.json({ error: 'Conversion not found.' }, { status: 404 });
  }

  // Only the uploader can re-download their file — admins (per ADMIN_EMAILS)
  // can override this and fetch anyone's, mirroring the /admin report access.
  if (row.user_email !== session.email && !isAdminEmail(session.email)) {
    return NextResponse.json({ error: 'You do not have access to this file.' }, { status: 403 });
  }

  if (!row.output_filename) {
    return NextResponse.json(
      { error: 'This file is no longer available for download.' },
      { status: 404 }
    );
  }

  let fileBuffer: Buffer;
  try {
    fileBuffer = fs.readFileSync(path.join(OUTPUT_DIR, row.output_filename));
  } catch {
    // DB says it should exist but it's missing on disk — clear the pointer
    // so the UI shows it as expired instead of repeatedly failing.
    db.prepare('UPDATE conversions SET output_filename = NULL WHERE id = ?').run(row.id);
    return NextResponse.json(
      { error: 'This file is no longer available for download.' },
      { status: 404 }
    );
  }

  db.prepare('UPDATE conversions SET downloaded_at = ? WHERE id = ?').run(Date.now(), row.id);

  return new NextResponse(new Uint8Array(fileBuffer), {
    headers: {
      'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'Content-Disposition': `attachment; filename="cleaned_${row.filename}"`,
    },
  });
}
