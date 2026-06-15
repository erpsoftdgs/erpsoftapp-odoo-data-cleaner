import fs from "fs";
import path from "path";
import db, { OUTPUT_DIR } from "./db";

const RETENTION_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

type ExpiredRow = { id: number; output_filename: string };

/**
 * Deletes stored copies of cleaned files older than the retention window and
 * clears their `output_filename` so the UI shows them as expired. The
 * `conversions` row itself (and all its reporting data) is left untouched —
 * only the re-download capability is removed.
 */
export function pruneExpiredOutputs(): void {
  const cutoff = Date.now() - RETENTION_MS;
  const rows = db
    .prepare("SELECT id, output_filename FROM conversions WHERE output_filename IS NOT NULL AND created_at < ?")
    .all(cutoff) as unknown as ExpiredRow[];

  if (rows.length === 0) return;

  const clearOutput = db.prepare("UPDATE conversions SET output_filename = NULL WHERE id = ?");
  for (const row of rows) {
    try {
      fs.unlinkSync(path.join(OUTPUT_DIR, row.output_filename));
    } catch (error: unknown) {
      const code = (error as NodeJS.ErrnoException)?.code;
      if (code !== "ENOENT") {
        console.error(`Failed to delete expired output for conversion ${row.id}:`, error);
      }
    }
    clearOutput.run(row.id);
  }

  console.log(`Retention: pruned ${rows.length} expired conversion file(s) older than 30 days.`);
}
