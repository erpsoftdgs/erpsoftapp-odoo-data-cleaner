import { randomInt, createHash } from "crypto";
import db from "./db";

const CODE_TTL_MS = 10 * 60 * 1000; // 10 minutes
const RESEND_COOLDOWN_MS = 60 * 1000; // 1 minute between requests for the same email

function hashCode(code: string): string {
  return createHash("sha256").update(code).digest("hex");
}

function generateCode(): string {
  return randomInt(0, 1_000_000).toString().padStart(6, "0");
}

export type IssueResult =
  | { ok: true; code: string }
  | { ok: false; reason: "cooldown"; retryAfterMs: number };

/**
 * Generates a fresh code, stores its hash, and returns the raw code to send
 * by email. Refuses to issue a new one if the last request for this address
 * is still within the cooldown window (basic anti-spam).
 */
export function issueCode(email: string): IssueResult {
  const normalised = email.toLowerCase();
  const now = Date.now();

  const last = db
    .prepare(
      "SELECT created_at FROM otp_codes WHERE email = ? ORDER BY created_at DESC LIMIT 1"
    )
    .get(normalised) as { created_at: number } | undefined;

  if (last && now - last.created_at < RESEND_COOLDOWN_MS) {
    return {
      ok: false,
      reason: "cooldown",
      retryAfterMs: RESEND_COOLDOWN_MS - (now - last.created_at),
    };
  }

  const code = generateCode();
  db.prepare(
    `INSERT INTO otp_codes (email, code_hash, expires_at, consumed, created_at)
     VALUES (?, ?, ?, 0, ?)`
  ).run(normalised, hashCode(code), now + CODE_TTL_MS, now);

  return { ok: true, code };
}

/**
 * Verifies a submitted code against the most recent unconsumed, unexpired
 * code on file for the address, and marks it consumed on success (single use).
 */
export function consumeCode(email: string, submitted: string): boolean {
  const normalised = email.toLowerCase();
  const now = Date.now();

  const row = db
    .prepare(
      `SELECT id, code_hash FROM otp_codes
       WHERE email = ? AND consumed = 0 AND expires_at > ?
       ORDER BY created_at DESC LIMIT 1`
    )
    .get(normalised, now) as { id: number; code_hash: string } | undefined;

  if (!row || row.code_hash !== hashCode(submitted.trim())) {
    return false;
  }

  db.prepare("UPDATE otp_codes SET consumed = 1 WHERE id = ?").run(row.id);
  return true;
}
