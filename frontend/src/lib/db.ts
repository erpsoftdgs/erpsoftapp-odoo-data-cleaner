import { DatabaseSync } from "node:sqlite";
import path from "path";
import fs from "fs";

// Single-file embedded DB for OTP codes + the conversion log. Uses Node's
// built-in `node:sqlite` (no native module / build toolchain required).
const DATA_DIR = path.join(process.cwd(), "data");

// Persisted copies of cleaned files, named "{conversion_id}.xlsx" — see
// api/clean/route.ts (write) and api/conversions/[id]/download (read).
export const OUTPUT_DIR = path.join(DATA_DIR, "outputs");

function openDatabase(): DatabaseSync {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    return new DatabaseSync(path.join(DATA_DIR, "app.db"));
  } catch (error: unknown) {
    // Next.js's build step ("Collecting page data") statically imports
    // every route module — including this one, via verify-code/route.ts ->
    // otp.ts -> db.ts — even though it never actually serves a request. If
    // the persistent DB file is owned by a different user than whoever is
    // running `next build` (the systemd service runs as www-data, but a
    // human runs the build over SSH as themselves), that import-time touch
    // fails with a permission error and takes the whole build down with
    // it. Fall back to an in-memory DB so the module always loads cleanly —
    // the real service process (which does have the right permissions)
    // opens the real file normally, so this fallback never triggers when
    // actually serving traffic.
    console.warn("Could not open persistent database, falling back to in-memory:", error);
    return new DatabaseSync(":memory:");
  }
}

const db = openDatabase();

try {
  db.exec(`
    CREATE TABLE IF NOT EXISTS otp_codes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL,
      code_hash TEXT NOT NULL,
      expires_at INTEGER NOT NULL,
      consumed INTEGER NOT NULL DEFAULT 0,
      created_at INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_otp_codes_email ON otp_codes(email);

    CREATE TABLE IF NOT EXISTS conversions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_email TEXT NOT NULL,
      data_type TEXT NOT NULL,
      filename TEXT NOT NULL,
      rows_uploaded INTEGER NOT NULL,
      rows_cleaned INTEGER NOT NULL,
      rows_errors INTEGER NOT NULL,
      rows_missing_fields INTEGER NOT NULL DEFAULT 0,
      rows_duplicates INTEGER NOT NULL DEFAULT 0,
      rows_internal INTEGER NOT NULL DEFAULT 0,
      rows_is_company_flag INTEGER NOT NULL DEFAULT 0,
      conversion_ms INTEGER NOT NULL,
      status TEXT NOT NULL,
      created_at INTEGER NOT NULL,
      downloaded_at INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_conversions_created_at ON conversions(created_at);
  `);

  // Runtime migration: CREATE TABLE IF NOT EXISTS doesn't alter an existing
  // table, so add columns for dev DBs created before a given feature existed.
  // New rows from fresh installs already match this shape.
  const conversionColumns = db.prepare("PRAGMA table_info(conversions)").all() as { name: string }[];
  const hasConversionColumn = (name: string) => conversionColumns.some((c) => c.name === name);

  if (!hasConversionColumn("output_filename")) {
    db.exec("ALTER TABLE conversions ADD COLUMN output_filename TEXT");
  }

  // rows_errors is the total flagged count; these four subdivide it by reason
  // (engine/odoo_data_engine.py's validate_and_split breakdown). Rows created
  // before this existed have no breakdown — default to 0 rather than NULL so
  // the UI can sum/compare them without null-checks everywhere.
  for (const col of ["rows_missing_fields", "rows_duplicates", "rows_internal", "rows_is_company_flag"]) {
    if (!hasConversionColumn(col)) {
      db.exec(`ALTER TABLE conversions ADD COLUMN ${col} INTEGER NOT NULL DEFAULT 0`);
    }
  }
} catch (error: unknown) {
  // Same build-time-static-import concern as openDatabase() above — schema
  // setup against a real file we can't write to (wrong user) must not crash
  // `next build`. The service process that actually serves traffic runs as
  // the user that owns the file, so this only ever fires during a build.
  console.warn("Database schema setup failed (likely a build-time permission issue):", error);
}

export default db;
