import { DatabaseSync } from "node:sqlite";
import path from "path";
import fs from "fs";

// Single-file embedded DB for OTP codes + the conversion log. Uses Node's
// built-in `node:sqlite` (no native module / build toolchain required).
const DATA_DIR = path.join(process.cwd(), "data");
fs.mkdirSync(DATA_DIR, { recursive: true });

// Persisted copies of cleaned files, named "{conversion_id}.xlsx" — see
// api/clean/route.ts (write) and api/conversions/[id]/download (read).
export const OUTPUT_DIR = path.join(DATA_DIR, "outputs");
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const db = new DatabaseSync(path.join(DATA_DIR, "app.db"));

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
    conversion_ms INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    downloaded_at INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS idx_conversions_created_at ON conversions(created_at);
`);

// Runtime migration: CREATE TABLE IF NOT EXISTS doesn't alter an existing
// table, so add the persisted-file column for dev DBs created before this
// feature existed. New rows from fresh installs already match this shape.
const conversionColumns = db.prepare("PRAGMA table_info(conversions)").all() as { name: string }[];
if (!conversionColumns.some((c) => c.name === "output_filename")) {
  db.exec("ALTER TABLE conversions ADD COLUMN output_filename TEXT");
}

export default db;
