import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { Agent, fetch as undiciFetch, FormData as UndiciFormData } from 'undici';
import { getSession } from '@/lib/auth';
import db, { OUTPUT_DIR } from '@/lib/db';

// This route proxies to the FastAPI engine, which can run for several
// minutes on large files (AI column mapping + address parsing), so it must
// run on the Node.js runtime (not Edge) and must never be statically optimized.
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
// Allow time for the AI-backed cleaning step (seconds). Long because a slow
// rate limit can make large files take many minutes.
export const maxDuration = 1800;

// Base URL of the FastAPI engine (engine/api_server.py), e.g.
//   ENGINE_URL=http://localhost:8000
const ENGINE_URL = (process.env.ENGINE_URL || 'http://localhost:8000').replace(/\/+$/, '');

const ENGINE_DISPATCHER = new Agent({
  headersTimeout: 1_800_000,
  bodyTimeout: 1_800_000,
});

export async function POST(request: Request) {
  // Middleware already blocks unauthenticated requests, but the route must
  // not rely on that alone — and we need the email to log the conversion.
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: 'You must be signed in to use this.' }, { status: 401 });
  }

  try {
    const formData = await request.formData();
    const file = formData.get('file') as File | null;
    const dataType = formData.get('data_type');

    if (!file) {
      return NextResponse.json({ error: 'No file provided' }, { status: 400 });
    }
    if (dataType !== 'customer' && dataType !== 'vendor') {
      return NextResponse.json(
        { error: "data_type must be 'customer' or 'vendor'" },
        { status: 400 }
      );
    }

    // Forward the upload to the engine's /api/clean-data endpoint. Built with
    // undici's own FormData (not the global one) so its type matches what
    // undiciFetch's body expects.
    const engineForm = new UndiciFormData();
    engineForm.append('file', new Blob([await file.arrayBuffer()], { type: file.type }), file.name);
    engineForm.append('data_type', dataType);

    const startedAt = Date.now();
    const cleanResponse = await undiciFetch(`${ENGINE_URL}/api/clean-data`, {
      method: 'POST',
      body: engineForm,
      dispatcher: ENGINE_DISPATCHER,
    });

    const cleanResult = (await cleanResponse.json().catch(() => null)) as {
      detail?: string;
      error?: string;
      status?: string;
      message?: string;
      download_url?: string;
      stats?: { total?: number; clean?: number; errors?: number };
    } | null;

    if (!cleanResponse.ok || !cleanResult) {
      const message =
        (cleanResult && (cleanResult.detail || cleanResult.error)) ||
        `Engine returned ${cleanResponse.status}`;
      return NextResponse.json({ error: message }, { status: cleanResponse.status || 502 });
    }

    if (cleanResult.status === 'error') {
      return NextResponse.json({ error: cleanResult.message }, { status: 500 });
    }

    // Fetch the cleaned file from the engine and buffer it — small enough at
    // this scale, and buffering lets us both return it instantly *and*
    // persist a copy for later re-download (see /history, /admin).
    const downloadResponse = await undiciFetch(`${ENGINE_URL}${cleanResult.download_url}`, {
      dispatcher: ENGINE_DISPATCHER,
    });
    if (!downloadResponse.ok || !downloadResponse.body) {
      return NextResponse.json(
        { error: 'Engine produced a result but the cleaned file could not be downloaded.' },
        { status: 502 }
      );
    }
    const fileBuffer = Buffer.from(await downloadResponse.arrayBuffer());

    // Log the conversion first so we have a row id to name the persisted copy
    // after — gives a natural 1:1 mapping with no extra randomness needed.
    const finishedAt = Date.now();
    const stats = cleanResult.stats || {};
    const { lastInsertRowid } = db.prepare(
      `INSERT INTO conversions
         (user_email, data_type, filename, rows_uploaded, rows_cleaned, rows_errors, conversion_ms, status, created_at, downloaded_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).run(
      session.email,
      dataType,
      file.name,
      Number(stats.total) || 0,
      Number(stats.clean) || 0,
      Number(stats.errors) || 0,
      finishedAt - startedAt,
      String(cleanResult.status),
      finishedAt,
      finishedAt
    );

    // Persist a copy server-side so the uploader (or an admin override) can
    // come back later and re-download it from /history or /admin. This is
    // best-effort: if it fails, the user's instant download must still work —
    // we just leave output_filename NULL (shown as "expired/unavailable").
    try {
      const outputFilename = `${lastInsertRowid}.xlsx`;
      fs.writeFileSync(path.join(OUTPUT_DIR, outputFilename), fileBuffer);
      db.prepare('UPDATE conversions SET output_filename = ? WHERE id = ?').run(outputFilename, lastInsertRowid);
    } catch (error: unknown) {
      console.error(`Failed to persist cleaned file for conversion ${lastInsertRowid}:`, error);
    }

    return new NextResponse(fileBuffer, {
      headers: {
        'Content-Type':
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': `attachment; filename="cleaned_${file.name}"`,
      },
    });
  } catch (error: unknown) {
    console.error('API Error:', error);
    const message =
      error instanceof Error
        ? error.message
        : 'Unknown error occurred while processing the file.';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
