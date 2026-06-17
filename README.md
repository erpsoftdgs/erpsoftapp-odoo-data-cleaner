# erpSOFTapp Data Cleaner

A two-part app for cleaning vendor/customer spreadsheets into Odoo-import-ready
files using Claude (with OpenRouter as a fallback for rate limits):

- **`engine/`** — a Python FastAPI service that does the actual cleaning
  (column mapping, address parsing, validation) via the Anthropic API.
- **`frontend/`** — a Next.js app that provides the upload UI, a passwordless
  email-code login restricted to `@erpsoftapp.com`, and an admin report of
  every conversion that's been run.

## Architecture

```text
Browser ──▶ Next.js (frontend, :3000)
              ├─ /login, session cookies, middleware route-guards
              ├─ /api/clean      ──HTTP proxy──▶ FastAPI engine (:8000)
              ├─ /api/conversions/[id]/download ──reads── frontend/data/outputs/
              ├─ /history        ──reads── SQLite (frontend/data/app.db), own rows only
              └─ /admin          ──reads── SQLite (frontend/data/app.db), all rows
```

The frontend never talks to Anthropic directly — it forwards uploads to the
engine's `/api/clean-data` endpoint, buffers the cleaned `.xlsx`, returns it
straight to the same authenticated request (so the uploader gets an instant
download), **and** persists a copy to `frontend/data/outputs/{conversion_id}.xlsx`
so it can be re-downloaded later. Every run is logged (who/when/row
counts/timing/stored filename) to a local SQLite database.

## Prerequisites

- Node.js v26+ (uses the built-in `node:sqlite` module — no native build step)
- Python 3.12
- An Anthropic API key (and optionally an OpenRouter key as a 429 fallback)

## Setup

### 1. Create the root `.env`

Both the engine and the frontend read from a **single `.env` at the project root**:

```env
# Engine — AI providers (fallback chain on Anthropic 429s: Claude → Gemini → OpenRouter)
ANTHROPIC_API_KEY=
GEMINI_API_KEY=         # optional 2nd-tier fallback; defaults to gemini-3.1-flash-lite (set GEMINI_MODEL to override)
OPENROUTER_API_KEY=     # optional 3rd-tier fallback; defaults to a free Llama model (set OPENROUTER_MODEL to override)
RATE_LIMIT_RPM=         # Claude requests/minute pace, default 5 (free tier is ~5 RPM)
GEMINI_RATE_LIMIT_RPM=  # Gemini fallback requests/minute pace, default 15 — set independently since
                        # Gemini's free-tier limit is higher than Claude's; falling back shouldn't be
                        # throttled down to Claude's slower pace
ANTHROPIC_MAX_RETRIES=  # optional, default 3 — SDK retries on a 429 before falling back to Gemini/OpenRouter

# Frontend — auth & sessions
ADMIN_EMAILS=         # comma-separated allowlist for /admin
SESSION_SECRET=       # generate with: node -e "console.log(require('crypto').randomBytes(48).toString('base64'))"

# Frontend — SMTP (leave blank locally; login codes log to console instead)
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASS=
SMTP_FROM=

# Frontend — engine proxy
ENGINE_URL=
```

The engine loads it via `python-dotenv` (`load_dotenv()` in `api_server.py`). The
frontend loads it via a `dotenv` hook at the top of `next.config.ts` — no separate
`frontend/.env.local` is needed.

### 2. Install the engine's Python dependencies

```bash
cd engine
pip3 install -r requirements.txt --break-system-packages   # Odoo.sh / externally-managed envs
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

### 4. Run everything

```bash
cd frontend
npm run dev
```

This single command starts **both** servers together (via `concurrently`),
with color-coded, prefixed log output — `[frontend]` (blue) and `[engine]`
(green):

- Next.js on [http://localhost:3000](http://localhost:3000) (falls back to
  3001+ if the port is taken). Dev mode uses `next dev --webpack` rather than
  Turbopack — on lower-resource machines Turbopack spawns enough parallel
  compile workers to exhaust memory/CPU.
- The FastAPI engine on `http://localhost:8000` (`uvicorn --reload`, picked up
  by `ENGINE_URL` in `frontend/.env.local`).

To run them separately (e.g. for isolated debugging), use `npm run
dev:frontend` or `npm run dev:engine` from `frontend/`.

## How login works

1. User enters an `@erpsoftapp.com` email at `/login`.
2. The server generates a 6-digit code, hashes and stores it (10-minute TTL,
   60-second resend cooldown), and emails it via SMTP — or, if SMTP isn't
   configured, logs it to the server console as `🔑 [DEV] Login code for ...`.
3. User enters the code; on success the server sets an `httpOnly` JWT session
   cookie (signed with `jose`, 7-day expiry).
4. `frontend/src/middleware.ts` guards every route: no/invalid session →
   redirects to `/login`; valid session but not in `ADMIN_EMAILS` → blocked
   from `/admin`.

## Conversion reporting & re-download

Every run through `/api/clean` is logged to `frontend/data/app.db` (SQLite,
created automatically) with the uploader's email, filename, data type, row
counts, conversion time, and timestamps. Admin users (per `ADMIN_EMAILS`) can
review the full history of every user's conversions at `/admin`; regular
users can review their own at `/history`.

Cleaned files are also **persisted server-side** at
`frontend/data/outputs/{conversion_id}.xlsx` (alongside the SQLite DB, in the
gitignored `frontend/data/` directory) so they can be re-downloaded later —
not just streamed once at conversion time:

- **Re-download**: `GET /api/conversions/{id}/download` streams the stored
  file back. Access is restricted to the original uploader, with an override
  for admins (per `ADMIN_EMAILS`) — the same "only the uploader receives
  their file, admins can see everything" rule that governs `/admin`.
- **Retention**: stored copies are automatically deleted **30 days** after
  creation (`frontend/src/lib/retention.ts`, scheduled from `db.ts` at boot
  and every 6 hours). The `conversions` row and its reporting data are kept
  permanently — only the file itself and its re-download capability are
  removed; the UI then shows that conversion as "Expired".

## Common commands

```bash
# Engine: update/clean a single column-mapping cache, run with auto-reload
uvicorn api_server:app --reload --port 8000

# Frontend: type-check
npx tsc --noEmit

# Inspect the conversion log directly
node -e "
  const { DatabaseSync } = require('node:sqlite');
  const db = new DatabaseSync('./data/app.db');
  console.log(db.prepare('SELECT * FROM conversions ORDER BY created_at DESC').all());
"
```

## Notes

- Only `vendor`/`customer` data types are supported (product cleaning was
  dropped from the UI for now).
- `frontend/data/` (the SQLite DB and the persisted `outputs/` files) and
  `.env*` files are gitignored — never commit secrets, the local database, or
  stored user files.
