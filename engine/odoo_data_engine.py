"""
Odoo ERP Data Migration Engine
================================
Universal AI-powered cleaning and column-mapping pipeline.
Converts arbitrary client spreadsheets into Odoo-ready import files.

Author  : Senior Python / AI Data Engineer
Version : 1.1.0 (Added Version Routing)
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import anthropic
import pandas as pd
import urllib.error
import urllib.request
from openpyxl.styles import PatternFill, Font
from openpyxl.utils import get_column_letter

if __package__:
    from .config import (
        ANTHROPIC_MAX_RETRIES,
        ANTHROPIC_RATE_LIMIT_RPM,
        GEMINI_API_KEY,
        GEMINI_MODEL,
        GEMINI_RATE_LIMIT_RPM,
        OPENROUTER_API_KEY,
        OPENROUTER_MODEL,
    )
    from .schemas import SCHEMA_MAP, MANDATORY_FIELD, get_schema
else:
    from config import (
        ANTHROPIC_MAX_RETRIES,
        ANTHROPIC_RATE_LIMIT_RPM,
        GEMINI_API_KEY,
        GEMINI_MODEL,
        GEMINI_RATE_LIMIT_RPM,
        OPENROUTER_API_KEY,
        OPENROUTER_MODEL,
    )
    from schemas import SCHEMA_MAP, MANDATORY_FIELD, get_schema

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("odoo_engine")


# ===========================================================================
# 1c. UNIVERSAL FILE STRUCTURE NORMALISER
#     Detects non-flat layouts and reshapes them into a standard flat table.
# ===========================================================================


def ai_normalise_structure(
    df: pd.DataFrame,
    source_path: Path,
    client: anthropic.Anthropic,
) -> pd.DataFrame:
    """
    Detects whether a loaded DataFrame has a non-standard structure
    (block records, vertical layout, multi-row headers, mixed metadata rows, etc.)
    and uses the AI to produce a reshape plan, then executes it in pure Pandas.

    For standard flat tables (one header row, one row per record) this returns
    the DataFrame unchanged — zero API cost.

    Handles:
    - Block structures  : multiple raw rows per record (e.g. CSS vendor file)
    - Vertical layouts  : fields as rows, records as columns
    - Multi-row headers : 2-3 header rows that need collapsing
    - Junk preamble     : title/logo rows before the real data starts
    - Mixed rows        : metadata/summary rows interspersed with data rows
    """
    if _is_flat_table(df):
        return df

    logger.info(
        "Non-flat structure detected in '%s' — running AI structure analyser",
        source_path.name,
    )

    snapshot_rows = min(12, len(df))
    snapshot = df.head(snapshot_rows).fillna("").astype(str).values.tolist()

    system_prompt = (
        "You are an expert data engineer specialising in spreadsheet normalisation. "
        "Return ONLY valid JSON — no prose, no markdown, no code fences."
    )

    user_prompt = f"""A spreadsheet has been loaded into a 2D array. The structure is NOT a standard
flat table (one header row followed by one row per record). You must analyse the pattern
and return a JSON reshape plan.

RAW DATA SNAPSHOT (first {snapshot_rows} rows, all columns):
{json.dumps(snapshot, indent=2)}

Analyse the repeating pattern carefully. Common non-flat structures:
1. BLOCK  — multiple raw rows form one logical record.
   e.g. Row A = "A/C Ref: | REF001 | Name: | Vendor Name"
        Row B = "0803... | Street | Sor | email@... | ..."
   Each pair of rows = one vendor record.

2. VERTICAL — fields are rows, records are columns.
   e.g. Row 0 = "Name | Alice | Bob | Carol"
        Row 1 = "Phone | 080... | 070... | 090..."

3. MULTI_HEADER — 2-3 rows together form the column header.
   e.g. Row 0 = "Contact | | Address | |"
        Row 1 = "Name | Phone | Street | City | State"

4. PREAMBLE — junk rows (title, logo text, blank) before the real data.
   e.g. Row 0 = "Agary Publishing — Customer List 2024"
        Row 1 = "" (blank)
        Row 2 = "Name | Phone | Address | ..."  ← real header

Return a JSON object with this structure:
{{
  "structure_type": "FLAT" | "BLOCK" | "VERTICAL" | "MULTI_HEADER" | "PREAMBLE" | "MIXED",
  "description": "one sentence describing what you see",
  "reshape_plan": {{

    For FLAT (already standard — return as-is):
      {{"action": "none"}}

    For BLOCK:
      {{
        "action": "block_to_rows",
        "rows_per_record": <int>,        // how many raw rows form one record
        "header_row_index": <int|null>,  // index of a header row if present, else null
        "skip_rows": [<int>, ...],       // raw row indices to skip (e.g. file header)
        "record_start_signal": {{        // how to identify the FIRST row of each block
          "col": <int>,                  // column index
          "value": "<string>"            // value that marks the start of a new record
        }},
        "field_map": [                   // how to read each field from the block rows
          {{
            "field": "<human name>",     // what this field represents
            "row_offset": <int>,         // 0 = first row of block, 1 = second row, etc.
            "col": <int>                 // column index within that row
          }},
          ...
        ]
      }}

    For VERTICAL:
      {{
        "action": "transpose",
        "field_name_col": <int>,   // column that contains field names
        "data_start_col": <int>    // first column that contains record data
      }}

    For MULTI_HEADER:
      {{
        "action": "collapse_headers",
        "header_rows": [<int>, ...],   // row indices that together form the header
        "data_start_row": <int>        // first row of actual data
      }}

    For PREAMBLE:
      {{
        "action": "skip_preamble",
        "header_row": <int>,    // row index of the real header
        "data_start_row": <int> // first row of actual data
      }}

    For MIXED:
      {{
        "action": "filter_rows",
        "header_row": <int>,
        "data_row_signal": {{   // how to identify a real data row vs junk
          "col": <int>,
          "pattern": "<regex or keyword that data rows match>"
        }}
      }}
  }}
}}

Return ONLY the JSON object.
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            raw_text = _complete_with_fallback(
                client, system_prompt, user_prompt, max_tokens=1500
            )
            raw_text = re.sub(
                r"^```[a-z]*\n?|```$", "", raw_text, flags=re.MULTILINE
            ).strip()
            plan = json.loads(raw_text)
            logger.info(
                "Structure analysis: type=%s | %s",
                plan.get("structure_type"),
                plan.get("description"),
            )
            return _execute_reshape_plan(df, plan, source_path)
        except (json.JSONDecodeError, _LLMUnavailable) as exc:
            logger.warning("Structure analysis attempt %d failed: %s", attempt + 1, exc)
            time.sleep(2**attempt)

    logger.warning("Structure analysis failed — returning raw DataFrame as-is")
    return df


def _is_flat_table(df: pd.DataFrame) -> bool:
    if df.empty or len(df) < 3:
        return True

    col0 = df.iloc[:, 0].fillna("").astype(str).str.strip()

    label_pattern = re.compile(
        r"^(a/c ref:?|name:|tel:?|code:?|ref:?|id:?|telephone|a/c ref)$", re.IGNORECASE
    )
    label_count = sum(1 for v in col0 if label_pattern.match(v))
    if label_count >= 3:
        return False

    blank_count = sum(1 for v in col0 if not v)
    if blank_count / len(col0) > 0.30:
        return False

    row0 = df.iloc[0].fillna("").astype(str).str.strip()
    if row0.iloc[0] == "" and df.shape[1] > 3:
        return False

    return True


def _execute_reshape_plan(
    df: pd.DataFrame,
    plan: dict,
    source_path: Path,
) -> pd.DataFrame:
    action = plan.get("reshape_plan", {}).get("action", "none")

    if action == "none":
        return df

    rp = plan["reshape_plan"]

    if action == "block_to_rows":
        return _reshape_block(df, rp)

    if action == "transpose":
        field_col = rp.get("field_name_col", 0)
        data_start = rp.get("data_start_col", 1)
        transposed = df.iloc[:, data_start:].T.copy()
        transposed.columns = df.iloc[:, field_col].fillna("").astype(str).tolist()
        transposed.reset_index(drop=True, inplace=True)
        transposed.dropna(how="all", inplace=True)
        logger.info(
            "Transposed vertical layout → %d rows × %d cols",
            len(transposed),
            len(transposed.columns),
        )
        return transposed

    if action == "collapse_headers":
        header_rows = rp.get("header_rows", [0])
        data_start = rp.get("data_start_row", len(header_rows))
        combined_header = []
        for col_idx in range(df.shape[1]):
            parts = [
                str(df.iloc[r, col_idx]).strip()
                for r in header_rows
                if str(df.iloc[r, col_idx]).strip() not in ("", "nan")
            ]
            combined_header.append(" / ".join(parts) if parts else f"col_{col_idx}")
        result = df.iloc[data_start:].copy()
        result.columns = combined_header[: len(result.columns)]
        result.reset_index(drop=True, inplace=True)
        logger.info(
            "Collapsed %d header rows → %d data rows", len(header_rows), len(result)
        )
        return result

    if action == "skip_preamble":
        header_row = rp.get("header_row", 0)
        data_start = rp.get("data_start_row", header_row + 1)
        result = df.iloc[data_start:].copy()
        result.columns = df.iloc[header_row].fillna("").astype(str).str.strip().tolist()
        result.reset_index(drop=True, inplace=True)
        result.dropna(how="all", inplace=True)
        logger.info("Skipped preamble — %d data rows", len(result))
        return result

    if action == "filter_rows":
        header_row = rp.get("header_row", 0)
        signal = rp.get("data_row_signal", {})
        sig_col = signal.get("col", 0)
        sig_pattern = signal.get("pattern", "")
        result = df.iloc[header_row + 1 :].copy()
        result.columns = df.iloc[header_row].fillna("").astype(str).str.strip().tolist()
        if sig_pattern:
            mask = (
                result.iloc[:, sig_col]
                .astype(str)
                .str.contains(sig_pattern, na=False, regex=True)
            )
            result = result[mask]
        result.reset_index(drop=True, inplace=True)
        logger.info("Filtered mixed rows → %d data rows", len(result))
        return result

    logger.warning("Unknown reshape action '%s' — returning raw DataFrame", action)
    return df


def _reshape_block(df: pd.DataFrame, rp: dict) -> pd.DataFrame:
    signal_col = rp.get("record_start_signal", {}).get("col", 0)
    signal_val = rp.get("record_start_signal", {}).get("value", "")
    skip_rows = set(rp.get("skip_rows", []))
    field_map = rp.get("field_map", [])

    if not field_map:
        logger.warning("Block reshape: no field_map provided — returning raw")
        return df

    block_starts = []
    for i in range(len(df)):
        if i in skip_rows:
            continue
        cell = str(df.iloc[i, signal_col]).strip()
        if cell == signal_val:
            block_starts.append(i)

    if not block_starts:
        logger.warning(
            "Block reshape: no block start rows found for signal %r=%r",
            signal_col,
            signal_val,
        )
        return df

    records = []
    col_names = [f["field"] for f in field_map]

    for start in block_starts:
        record = {}
        for fm in field_map:
            row_offset = fm.get("row_offset", 0)
            col_idx = fm.get("col", 0)
            raw_row = start + row_offset
            if raw_row < len(df) and col_idx < df.shape[1]:
                val = str(df.iloc[raw_row, col_idx]).strip()
                record[fm["field"]] = val if val not in ("", "nan") else None
            else:
                record[fm["field"]] = None
        records.append(record)

    result = pd.DataFrame(records, columns=col_names)
    result.dropna(how="all", inplace=True)
    result.reset_index(drop=True, inplace=True)
    logger.info(
        "Block reshape: %d blocks → %d records × %d fields",
        len(block_starts),
        len(result),
        len(col_names),
    )
    return result


# ===========================================================================
# 2b. LLM PROVIDER LAYER  –  Claude first, free OpenRouter model as fallback
# ===========================================================================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

_last_call_at: dict[str, float] = {}


def _pace_call(provider: str, rpm: float) -> None:
    if rpm <= 0:
        return
    min_interval = 60.0 / rpm
    elapsed = time.monotonic() - _last_call_at.get(provider, 0.0)
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _last_call_at[provider] = time.monotonic()


class _LLMUnavailable(Exception):
    pass


def _is_rate_limited(exc: anthropic.APIError) -> bool:
    if isinstance(exc, anthropic.RateLimitError):
        return True
    return getattr(exc, "status_code", None) == 429


def _is_credits_exhausted(exc: anthropic.APIError) -> bool:
    return "credit balance" in str(exc).lower()


def _is_provider_unavailable_error(exc: anthropic.APIError) -> bool:
    return _is_rate_limited(exc) or _is_credits_exhausted(exc)


_anthropic_credits_exhausted = False


def _retry_after_seconds(exc: anthropic.APIError) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    value = headers.get("retry-after") if headers else None
    if value:
        try:
            return float(value)
        except ValueError:
            pass
    return None


def _call_gemini(system_prompt: str, user_prompt: str, max_tokens: int) -> str | None:
    if not GEMINI_API_KEY:
        return None

    payload = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
    ).encode("utf-8")

    url = GEMINI_URL.format(model=GEMINI_MODEL, key=GEMINI_API_KEY)
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("Gemini fallback request failed: %s", exc)
        return None


def _call_openrouter(
    system_prompt: str, user_prompt: str, max_tokens: int
) -> str | None:
    if not OPENROUTER_API_KEY:
        return None

    payload = json.dumps(
        {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("OpenRouter fallback request failed: %s", exc)
        return None


def _complete_with_fallback(
    client: anthropic.Anthropic,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> str:
    global _anthropic_credits_exhausted
    exc: anthropic.APIError | None = None

    if not _anthropic_credits_exhausted:
        _pace_call("anthropic", ANTHROPIC_RATE_LIMIT_RPM)
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text.strip()
        except anthropic.APIError as caught:
            if _is_credits_exhausted(caught):
                logger.error(
                    "Anthropic account is out of credits – skipping Claude for "
                    "the rest of this run, falling back to Gemini/OpenRouter only"
                )
                _anthropic_credits_exhausted = True
            elif not _is_rate_limited(caught):
                raise _LLMUnavailable(str(caught)) from caught
            exc = caught

    if exc is not None:
        logger.warning(
            "Anthropic unavailable (%s) – trying Gemini fallback (%s) …",
            exc,
            GEMINI_MODEL,
        )
    _pace_call("gemini", GEMINI_RATE_LIMIT_RPM)
    fallback_text = _call_gemini(system_prompt, user_prompt, max_tokens)
    if fallback_text is not None:
        logger.info("Gemini fallback succeeded – continuing pipeline")
        return fallback_text

    logger.warning(
        "Gemini fallback unavailable – trying OpenRouter fallback (%s) …",
        OPENROUTER_MODEL,
    )
    fallback_text = _call_openrouter(system_prompt, user_prompt, max_tokens)
    if fallback_text is not None:
        logger.info("OpenRouter fallback succeeded – continuing pipeline")
        return fallback_text

    if exc is not None:
        wait = _retry_after_seconds(exc)
        if wait:
            logger.warning(
                "Anthropic unavailable, no fallback available – sleeping %.0fs …", wait
            )
            time.sleep(wait)
        raise _LLMUnavailable(
            "Anthropic unavailable and no fallback (Gemini/OpenRouter) available"
        ) from exc
    raise _LLMUnavailable(
        "Anthropic credits exhausted and no fallback (Gemini/OpenRouter) available"
    )


# ===========================================================================
# 2. FILE LOADER
# ===========================================================================


def load_raw_file(filepath: str | Path) -> pd.DataFrame:
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix in (".xlsx", ".xls", ".xlsm"):
        probe = pd.read_excel(path, header=None, nrows=10)
        header_row = _detect_header_row(probe)
        df = pd.read_excel(path, header=header_row, dtype=str)
    elif suffix == ".csv":
        probe = pd.read_csv(path, header=None, nrows=10)
        header_row = _detect_header_row(probe)
        df = pd.read_csv(path, header=header_row, dtype=str)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    df = df.replace(r"^\s*$", pd.NA, regex=True)
    rows_before_empty_drop = len(df)
    df.dropna(how="all", inplace=True)
    empty_rows_dropped = rows_before_empty_drop - len(df)
    if empty_rows_dropped:
        logger.info(
            "Dropped %d fully empty rows from '%s'", empty_rows_dropped, path.name
        )
    df.dropna(axis=1, how="all", inplace=True)

    df.columns = [str(c).strip() for c in df.columns]
    df = df.apply(lambda col: col.map(lambda x: x.strip() if isinstance(x, str) else x))

    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

    logger.info(
        "Loaded %d rows × %d cols from '%s' (header row %d)",
        len(df),
        len(df.columns),
        path.name,
        header_row,
    )
    return df


def _detect_header_row(probe: pd.DataFrame) -> int:
    best_row, best_score = 0, 0
    for i, row in probe.iterrows():
        score = sum(
            1
            for v in row
            if isinstance(v, str)
            and v.strip()
            and not re.fullmatch(r"[\d\s.,-/]+", v.strip())
        )
        if score > best_score:
            best_score, best_row = score, int(i)
    return best_row


# ===========================================================================
# 3. AI COLUMN MAPPER
# ===========================================================================


def ai_map_columns(
    raw_columns: list[str],
    target_schema: dict[str, dict],
    data_type: str,
    version: str,  # <-- Added version parameter
    client: anthropic.Anthropic,
    sample_rows: list[dict] | None = None,
) -> tuple[dict[str, str | None], dict[str, list[str]]]:
    target_fields = list(target_schema.keys())
    sample_str = ""
    if sample_rows:
        sample_str = "\n\nSample data rows (first 3):\n" + json.dumps(
            sample_rows[:3], indent=2, default=str
        )

    system_prompt = (
        "You are an expert Odoo ERP data migration specialist. "
        "You MUST return ONLY valid JSON – no prose, no code fences, no explanations. "
        "Your response must be a single JSON object."
    )

    user_prompt = f"""Map the raw spreadsheet columns below to Odoo {version} {data_type} import fields,
and flag any columns that need additional AI processing.

RAW COLUMNS (from client spreadsheet):
{json.dumps(raw_columns, indent=2)}
{sample_str}

TARGET ODOO FIELDS (exact spelling required):
{json.dumps(target_fields, indent=2)}

MAPPING RULES:
1. Each KEY is a raw column name; VALUE is the best-matching Odoo field name (exact spelling
   from the target list), or null if no match.
2. Never invent field names – only use values from the target list or null.
3. One raw column → at most one Odoo field. Multiple raws must NOT share the same Odoo target.
4. Semantic matching required: "Client Name"→"Name", "Organisation"→"Vendor Name",
   "Tel"→"Phone", "Ref"→"Reference", "Area"→"City", "Supplier Rank"→"Supplier Rank".
5. For child/contact columns match appropriately (e.g. "child_ids/name"→"contacts / name").
6. If a raw column contains combined address data (street + city + state in one cell),
   map it to "Street" AND add its raw column name to "needs_address_split".
7. If a raw column clearly represents a DIFFERENT individual contact person than the main
   record itself (e.g. "Contact Person", "Attn", "Attention", "C/O", "Care Of", "Contact",
   "Representative") — i.e. it names someone other than the company/individual identified
   in the main name column — map it to "contacts / name", NEVER to "Name". The main "Name"
   field must always hold the record's own identity (the company name when "Is a Company"
   is true, or the individual's own name when false), not a secondary contact person.

FLAG RULES:
- "needs_address_split": list raw column names where sample values combine multiple address
  parts in one cell (e.g. "12 Broad St, Lagos, Lagos State"). Only flag when clearly combined.
- "needs_field_clean": list the ODOO FIELD NAMES (post-mapping) where sample values look
  cross-contaminated. Examples: Phone column with "John Smith 0803..." (name before number);
  State column with city names instead of state names; Country with full addresses.
  Only flag fields where contamination is evident — do not flag clean columns.

Return a JSON object with EXACTLY this structure (no other keys):
{{
  "mapping": {{
    "RawColumnName": "OdooFieldName",
    "AnotherRawCol": null
  }},
  "flags": {{
    "needs_address_split": ["RawColWithCombinedAddress"],
    "needs_field_clean": ["Phone", "State"]
  }}
}}
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            raw_text = _complete_with_fallback(
                client, system_prompt, user_prompt, max_tokens=1000
            )
            raw_text = re.sub(
                r"^```[a-z]*\n?|```$", "", raw_text, flags=re.MULTILINE
            ).strip()
            result = json.loads(raw_text)
            mapping = result.get("mapping", {})
            flags = result.get(
                "flags",
                {
                    "needs_address_split": [],
                    "needs_field_clean": [],
                },
            )
            logger.info(
                "AI column mapping: %d mappings | address_split=%s | field_clean=%s",
                len(mapping),
                flags.get("needs_address_split", []),
                flags.get("needs_field_clean", []),
            )
            return mapping, flags
        except (json.JSONDecodeError, _LLMUnavailable) as exc:
            logger.warning("AI mapping attempt %d failed: %s", attempt + 1, exc)
            time.sleep(2**attempt)

    logger.error(
        "AI column mapping failed after %d attempts – returning empty map", max_retries
    )
    return {}, {"needs_address_split": [], "needs_field_clean": []}


# ===========================================================================
# 4. RULE-BASED PANDAS CLEANER
# ===========================================================================

_PHONE_RE = re.compile(r"[^\d+]")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def rule_based_clean(df: pd.DataFrame, data_type: str) -> pd.DataFrame:
    schema = SCHEMA_MAP[data_type]["v19"]

    name_cols = [
        c for c in df.columns if c.lower() in ("name", "vendor name", "company")
    ]
    for col in name_cols:
        df[col] = df[col].apply(_title_case)

    phone_cols = [
        c for c in df.columns if any(k in c.lower() for k in ("phone", "mobile", "tel"))
    ]
    for col in phone_cols:
        df[col] = df[col].apply(_clean_phone)

    if "child_ids" in df.columns:
        child_name_col = next(
            (
                c
                for c in df.columns
                if c.lower() in ("child_ids/name", "contacts / name")
            ),
            None,
        )

        def _rescue_child_id(row: pd.Series) -> pd.Series:
            val = row.get("child_ids", "")
            if not isinstance(val, str):
                return row
            v = val.strip()
            if v.lower() in ("false", "true", "", "0", "1") or re.fullmatch(r"\d+", v):
                return row
            if child_name_col and (
                pd.isna(row.get(child_name_col))
                or str(row.get(child_name_col, "")).strip() == ""
            ):
                row = row.copy()
                row[child_name_col] = v.title()
            row["child_ids"] = None
            return row

        if child_name_col:
            df = df.apply(_rescue_child_id, axis=1)
            logger.info("Rescued child_ids contact names into '%s'", child_name_col)
        df.drop(columns=["child_ids"], inplace=True, errors="ignore")

    email_cols = [
        c for c in df.columns if "email" in c.lower() or "e-mail" in c.lower()
    ]
    for col in email_cols:
        df[col] = df[col].apply(_clean_email)

    web_cols = [c for c in df.columns if "website" in c.lower() or "web" in c.lower()]
    for col in web_cols:
        df[col] = df[col].apply(lambda x: x.lower() if isinstance(x, str) else x)

    company_cols = [c for c in df.columns if "is a company" in c.lower()]
    for col in company_cols:
        df[col] = df[col].apply(_coerce_bool)

    if data_type == "customer" and not company_cols:
        name_col = next(
            (
                c
                for c in df.columns
                if c.lower() in ("name", "vendor name", "description")
            ),
            None,
        )
        if name_col:
            df["Is a Company"] = df[name_col].apply(infer_is_company)
            logger.info("Inferred 'Is a Company' from '%s' column", name_col)

    for col in df.columns:
        if col.lower() in ("state_id", "state", "country_id", "country"):
            df[col] = df[col].apply(
                lambda x: (
                    None
                    if (
                        isinstance(x, str)
                        and x.strip().lower() in ("false", "true", "0")
                    )
                    else x
                )
            )

    country_col = next(
        (c for c in df.columns if c.lower() in ("country_id", "country")), None
    )
    state_col = next(
        (c for c in df.columns if c.lower() in ("state_id", "state")), None
    )

    _ADDR_HINTS = {
        "street",
        "street2",
        "address",
        "addr",
        "city",
        "area",
        "location",
        "region",
        "zone",
        "district",
        "state_id",
        "country_id",
        "child_ids/street",
    }
    addr_cols = [
        c
        for c in df.columns
        if (
            c.lower() in _ADDR_HINTS
            or any(k in c.lower() for k in ("street", "address", "addr", "city"))
        )
        and "type" not in c.lower()
        and "address type" not in c.lower()
    ]

    for idx, row in df.iterrows():
        state_missing = state_col is not None and (
            pd.isna(row.get(state_col))
            or str(row.get(state_col, "")).strip() in ("", "None")
        )
        country_missing = country_col is not None and (
            pd.isna(row.get(country_col))
            or str(row.get(country_col, "")).strip() in ("", "None")
        )

        if not (state_missing or country_missing):
            continue

        parts = []
        for col in addr_cols:
            v = row.get(col, "")
            if (
                isinstance(v, str)
                and v.strip()
                and v.strip().lower() not in ("false", "none", "nan")
            ):
                parts.append(v.strip())
        combined = " | ".join(parts)

        if not combined.strip():
            continue

        state_found, country_found = _extract_state_country_from_row(combined)

        if state_missing and state_found and state_col:
            df.at[idx, state_col] = state_found
        if country_missing and country_found and country_col:
            df.at[idx, country_col] = country_found

    ref_cols = [c for c in df.columns if c.lower() in ("reference", "ref")]
    for col in ref_cols:
        df[col] = df[col].apply(_strip_odoo_prefix)

    for col in df.columns:
        schema_key = col
        if schema_key in schema and schema[schema_key]["dtype"] in ("float", "int"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(
                schema[schema_key]["default"] or 0
            )

    zip_cols = [c for c in df.columns if c.lower() in ("zip", "postal", "zip code")]
    for col in zip_cols:
        df[col] = df[col].apply(
            lambda x: (
                str(int(float(x)))
                if (isinstance(x, str) and re.fullmatch(r"\d+\.0", x))
                else x
            )
        )

    _AR_MAP = {
        "horeca": "112002 Horeca Receivables",
        "retail": "112003 Retail Receivables",
        "distributor": "112001 Distributors Receivables",
        "others": "112005 Other Receivables",
        "not sales": "112006 Related Party Receivables",
    }
    cat_col = next((c for c in df.columns if c.lower() == "category"), None)
    ar_col = next((c for c in df.columns if "account receivable" in c.lower()), None)
    if cat_col and data_type == "customer":
        if ar_col is None:
            df["Account Receivable"] = None
            ar_col = "Account Receivable"
        mask = df[ar_col].isna() | (df[ar_col].astype(str).str.strip() == "")
        df.loc[mask, ar_col] = df.loc[mask, cat_col].apply(
            lambda x: (
                _AR_MAP.get(str(x).strip().lower()) if isinstance(x, str) else None
            )
        )

    branch_col = next((c for c in df.columns if c.lower() == "branch"), None)
    note_col = next((c for c in df.columns if c.lower() == "note"), None)
    if branch_col and data_type == "customer":
        if note_col is None:
            df["Note"] = None
            note_col = "Note"
        mask = df[note_col].isna() | (df[note_col].astype(str).str.strip() == "")
        df.loc[mask, note_col] = df.loc[mask, branch_col]

    _final_state_col = next(
        (c for c in df.columns if c.lower() in ("state", "state_id")), None
    )
    if _final_state_col:
        df[_final_state_col] = df[_final_state_col].apply(_normalize_ng_state)

    return df


# -- helper functions --------------------------------------------------------


def _title_case(val: Any) -> Any:
    if not isinstance(val, str) or not val.strip():
        return val
    return val.strip().title()


def _clean_phone(val: Any) -> Any:
    if not isinstance(val, str) or not val.strip():
        return val
    stripped = val.strip()
    has_plus = stripped.startswith("+")
    digits = re.sub(r"\D", "", stripped)
    return ("+" if has_plus else "") + digits if digits else None


def _clean_email(val: Any) -> Any:
    if not isinstance(val, str) or not val.strip():
        return val
    val = val.strip().lower()
    match = _EMAIL_RE.search(val)
    return match.group(0) if match else None


def _coerce_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if pd.isna(val):
        return False
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "y")
    return False


_COMPANY_KEYWORDS = {
    "ltd", "limited", "co.", "co,", "plc", "inc", "corp", "corporation", "llc", "llp",
    "nig", "nigeria", "ent", "enterprises", "enterprise", "int", "international",
    "services", "service", "solutions", "solution", "group", "associates", "association",
    "holdings", "holding", "industries", "industry", "production", "productions",
    "manufacturing", "trading", "logistics", "consulting", "consultancy", "technologies",
    "technology", "systems", "global", "agency", "agencies", "pharmaceuticals",
    "pharmaceutical", "pharmacy", "healthcare", "hospital", "clinic", "medical",
    "surgical", "laboratory", "labs", "publishing", "publishers", "media",
    "communications", "foundation", "restaurant", "supermarket", "stores", "store",
    "market", "bakery", "hotel", "suites", "ventures", "investment", "investments",
    "capital", "properties", "property", "real estate", "construction", "contractors",
    "supplies", "supply", "distribution", "distributors", "distributor", "imports",
    "exports", "resources", "management", "academy", "school", "college", "university",
    "institute", "church", "ministry", "agro", "agriculture", "agricultural", "produce",
    "farms", "farm", "integrated", "nig.", "and", "sons", "son", "brothers", "bro",
}

_NORMALIZED_COMPANY_KEYWORDS = {
    " ".join(re.findall(r"[a-z0-9]+", keyword.lower()))
    for keyword in _COMPANY_KEYWORDS
    if keyword.lower() != "and"
}
_NORMALIZED_COMPANY_KEYWORDS.update({"it", "lp"})
_COMPANY_KEYWORD_PATTERNS = tuple(
    re.compile(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])")
    for keyword in _NORMALIZED_COMPANY_KEYWORDS
)

_INTERNAL_ACCOUNT_PATTERNS = re.compile(
    r"walk[\s\-]?in|walk in|cash sale|a\/c\b|debt recovery|"
    r"online customer|regulatory|nafdac sample|^sample$",
    re.IGNORECASE,
)


def infer_is_company(name: Any) -> bool:
    if not isinstance(name, str) or not name.strip():
        return False

    normalized_name = " ".join(re.findall(r"[a-z0-9]+", name.casefold()))
    return any(pattern.search(normalized_name) for pattern in _COMPANY_KEYWORD_PATTERNS)


_WORLD_COUNTRIES: dict[str, str] = {
    "nigeria": "Nigeria", "ghana": "Ghana", "kenya": "Kenya", "south africa": "South Africa",
    "ethiopia": "Ethiopia", "tanzania": "Tanzania", "uganda": "Uganda", "egypt": "Egypt",
    "cameroon": "Cameroon", "ivory coast": "Ivory Coast", "cote d'ivoire": "Ivory Coast",
    "senegal": "Senegal", "mali": "Mali", "angola": "Angola", "mozambique": "Mozambique",
    "zambia": "Zambia", "zimbabwe": "Zimbabwe", "rwanda": "Rwanda", "botswana": "Botswana",
    "namibia": "Namibia", "benin": "Benin", "togo": "Togo", "niger": "Niger Republic",
    "chad": "Chad", "sudan": "Sudan", "somalia": "Somalia", "libya": "Libya",
    "morocco": "Morocco", "algeria": "Algeria", "tunisia": "Tunisia",
    "united kingdom": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "germany": "Germany", "france": "France", "italy": "Italy",
    "spain": "Spain", "portugal": "Portugal", "netherlands": "Netherlands", "belgium": "Belgium",
    "switzerland": "Switzerland", "austria": "Austria", "sweden": "Sweden", "norway": "Norway",
    "denmark": "Denmark", "finland": "Finland", "poland": "Poland", "czech republic": "Czech Republic",
    "hungary": "Hungary", "romania": "Romania", "greece": "Greece", "turkey": "Turkey",
    "russia": "Russia", "ukraine": "Ukraine", "ireland": "Ireland",
    "united states": "United States", "usa": "United States", "u.s.a": "United States",
    "u.s.a.": "United States", "canada": "Canada", "mexico": "Mexico", "brazil": "Brazil",
    "argentina": "Argentina", "colombia": "Colombia", "chile": "Chile", "peru": "Peru",
    "venezuela": "Venezuela", "china": "China", "india": "India", "japan": "Japan",
    "south korea": "South Korea", "indonesia": "Indonesia", "pakistan": "Pakistan",
    "bangladesh": "Bangladesh", "vietnam": "Vietnam", "thailand": "Thailand",
    "malaysia": "Malaysia", "singapore": "Singapore", "philippines": "Philippines",
    "hong kong": "Hong Kong", "taiwan": "Taiwan", "saudi arabia": "Saudi Arabia",
    "uae": "United Arab Emirates", "united arab emirates": "United Arab Emirates",
    "dubai": "United Arab Emirates", "israel": "Israel", "iran": "Iran", "iraq": "Iraq",
    "jordan": "Jordan", "lebanon": "Lebanon", "qatar": "Qatar", "kuwait": "Kuwait",
    "bahrain": "Bahrain", "australia": "Australia", "new zealand": "New Zealand",
}

_WORLD_COUNTRIES_SORTED: list[tuple[str, str]] = sorted(
    _WORLD_COUNTRIES.items(), key=lambda x: len(x[0]), reverse=True
)

_NG_STATES: dict[str, str] = {
    "abia": "Abia", "adamawa": "Adamawa", "akwa ibom": "Akwa Ibom", "akwaibom": "Akwa Ibom",
    "anambra": "Anambra", "bauchi": "Bauchi", "bayelsa": "Bayelsa", "benue": "Benue",
    "borno": "Borno", "cross river": "Cross River", "crossriver": "Cross River",
    "delta": "Delta", "ebonyi": "Ebonyi", "edo": "Edo", "ekiti": "Ekiti", "enugu": "Enugu",
    "fct": "FCT", "federal capital territory": "FCT", "abuja": "FCT", "gombe": "Gombe",
    "imo": "Imo", "jigawa": "Jigawa", "kaduna": "Kaduna", "kano": "Kano", "katsina": "Katsina",
    "kebbi": "Kebbi", "kogi": "Kogi", "kwara": "Kwara", "lagos": "Lagos", "nasarawa": "Nasarawa",
    "niger": "Niger", "ogun": "Ogun", "ondo": "Ondo", "osun": "Osun", "oyo": "Oyo",
    "plateau": "Plateau", "plateau state": "Plateau", "rivers": "Rivers", "sokoto": "Sokoto",
    "taraba": "Taraba", "yobe": "Yobe", "zamfara": "Zamfara",
}

_CITY_TO_STATE: dict[str, str] = {
    "aba": "Abia", "abakaliki": "Ebonyi", "abeokuta": "Ogun", "abuja": "FCT",
    "abulado": "Lagos", "abule ado": "Lagos", "abule egba": "Lagos", "abule iroko": "Ogun",
    "abule odu": "Lagos", "ado ekiti": "Ekiti", "ado-ekiti": "Ekiti", "agboju": "Lagos",
    "agege": "Lagos", "agidingbi": "Lagos", "aguda": "Lagos", "ajah": "Lagos",
    "ajao estate": "Lagos", "ajegunle": "Lagos", "akoka": "Lagos", "akure": "Ondo",
    "akute": "Ogun", "akwa": "Anambra", "alagbado": "Lagos", "alausa": "Lagos",
    "allen": "Lagos", "amuwo odofin": "Lagos", "amuwo-odofin": "Lagos", "anthony": "Lagos",
    "anthony village": "Lagos", "apapa": "Lagos", "apete": "Oyo", "apo": "FCT",
    "apongbon": "Lagos", "arepo": "Ogun", "asaba": "Delta", "asokoro": "FCT",
    "auchi": "Edo", "awkunanaw": "Enugu", "awoyaya": "Lagos", "badagry": "Lagos",
    "badagery": "Lagos", "badagary": "Lagos", "bariga": "Lagos", "bauchi": "Bauchi",
    "benin": "Edo", "benin city": "Edo", "berger": "Lagos", "bori": "Rivers",
    "calabar": "Cross River", "dopemu": "Lagos", "duboyi": "FCT", "dutse": "FCT",
    "dutse apo": "FCT", "ebute meta": "Lagos", "ebute metta": "Lagos",
    "ebute-metta": "Lagos", "egbe ikotun": "Lagos", "egbeda": "Lagos", "ejigbo": "Lagos",
    "eket": "Akwa Ibom", "elelenwo": "Rivers", "enugu": "Enugu", "eruwa": "Oyo",
    "fadeyi": "Lagos", "fastac town": "Lagos", "festac": "Lagos", "festac town": "Lagos",
    "festac/amuwo": "Lagos", "galadimawa": "FCT", "garki": "FCT", "gbagada": "Lagos",
    "gombe": "Gombe", "gudu": "FCT", "gwagwalada": "FCT", "gwarimpa": "FCT",
    "gwaska": "FCT", "ibadan": "Oyo", "ibafo": "Lagos", "ibeju lekki": "Lagos",
    "ibeju-lekki": "Lagos", "idimu": "Lagos", "idu": "FCT", "idumota": "Lagos",
    "ifako": "Lagos", "ifako-agege": "Lagos", "igando": "Lagos", "iganmu": "Lagos",
    "ijebu-ode": "Ogun", "ijebu ode": "Ogun", "ijebu mushin": "Ogun", "ijegun": "Lagos",
    "ijeodo": "Lagos", "ijeshatedo": "Lagos", "ijora": "Lagos", "iju": "Lagos",
    "iju ishaga": "Lagos", "ikate": "Lagos", "ikeja": "Lagos", "ikorodu": "Lagos",
    "ikosi ketu": "Lagos", "ikosi-ketu": "Lagos", "ikota": "Lagos", "ikotun": "Lagos",
    "ikoyi": "Lagos", "ilaro": "Ogun", "ilasa": "Lagos", "ilishan-remo": "Ogun",
    "ilorin": "Kwara", "ilupeju": "Lagos", "illupeju": "Lagos", "ipaja": "Lagos",
    "isale-eko": "Lagos", "isale eko": "Lagos", "iseyin": "Oyo", "ishaga": "Lagos",
    "isheri": "Lagos", "isolo": "Lagos", "itafaji": "Lagos", "itire": "Lagos",
    "iyana ipaja": "Lagos", "jabi": "FCT", "jahi": "FCT", "jericho": "Oyo",
    "jibowu": "Lagos", "jos": "Plateau", "kado": "FCT", "kaduna": "Kaduna",
    "kano": "Kano", "karu": "FCT", "katampe": "FCT", "ketu": "Lagos", "kubwa": "FCT",
    "kuje": "FCT", "lafiaji": "Lagos", "lagos": "Lagos", "lagos island": "Lagos",
    "lekki": "Lagos", "lekki ajah": "Lagos", "lekki phase 1": "Lagos", "lekki vgc": "Lagos",
    "life camp": "FCT", "lokoja": "Kogi", "lugbe": "FCT", "mabushi": "FCT",
    "magodo": "Lagos", "maitama": "FCT", "makurdi": "Benue", "mararaba": "Nasarawa",
    "marina": "Lagos", "maroko": "Lagos", "maryland": "Lagos", "matori": "Lagos",
    "mende": "Lagos", "mile 2": "Lagos", "mowe": "Ogun", "mowe/ibafo": "Ogun",
    "mushin": "Lagos", "nasarawa": "Nasarawa", "nnewi": "Anambra", "nyanya": "FCT",
    "obanikoro": "Lagos", "obantoko": "Ogun", "ogba": "Lagos", "ogbomosho": "Oyo",
    "ogere": "Ogun", "ogijo": "Ogun", "ogudu": "Lagos", "ojo": "Lagos",
    "ojodu": "Lagos", "ojodu berger": "Lagos", "ojokoro": "Lagos", "ojota": "Lagos",
    "okota": "Lagos", "okitipupa": "Ondo", "oko oba": "Lagos", "olodi": "Lagos",
    "onigbongbo": "Lagos", "onikan": "Lagos", "onipanu": "Lagos", "oniru": "Lagos",
    "onitsha": "Anambra", "oregun": "Lagos", "orile iganmu": "Lagos", "osborne": "Lagos",
    "oshodi": "Lagos", "oshodi-isolo": "Lagos", "osogbo": "Osun", "ota": "Ogun",
    "owerri": "Imo", "owerrinta": "Abia", "owo": "Ondo", "oworonshoki": "Lagos",
    "oworonsoki": "Lagos", "palmgrove": "Lagos", "pedro": "Lagos",
    "port harcourt": "Rivers", "ph": "Rivers", "sabo": "Lagos", "sagamu": "Ogun",
    "saminaka": "Kaduna", "sango ota": "Ogun", "sango-ota": "Ogun",
    "sangotedo": "Lagos", "satellite town": "Lagos", "satalite town": "Lagos",
    "satelite town": "Lagos", "shangisha": "Lagos", "shomolu": "Lagos",
    "somolu": "Lagos", "suleja": "Niger", "surulere": "Lagos", "tanke": "Kwara",
    "tinubu square": "Lagos", "ughelli": "Delta", "ugheli": "Delta",
    "umuahia": "Abia", "umunze": "Anambra", "uwani": "Enugu", "uyo": "Akwa Ibom",
    "vgc": "Lagos", "victoria island": "Lagos", "warri": "Delta", "woji": "Rivers",
    "wuse": "FCT", "wuse 2": "FCT", "wuse zone 5": "FCT", "yaba": "Lagos",
    "yenagoa": "Bayelsa", "yenegoa": "Bayelsa", "zone 5": "FCT", "zone 6 abuja": "FCT",
}

_CITY_CACHE_PATH = Path(__file__).parent / "learned_cities.json"


def _load_city_cache() -> dict[str, str]:
    if _CITY_CACHE_PATH.exists():
        try:
            with _CITY_CACHE_PATH.open("r", encoding="utf-8") as fh:
                cache = json.load(fh)
            logger.info("Loaded %d learned city mappings from cache", len(cache))
            return {k.lower(): v for k, v in cache.items()}
        except Exception as exc:
            logger.warning("Could not load city cache: %s", exc)
    return {}


def _save_city_cache(cache: dict[str, str]) -> None:
    try:
        with _CITY_CACHE_PATH.open("w", encoding="utf-8") as fh:
            json.dump(dict(sorted(cache.items())), fh, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Could not save city cache: %s", exc)


_CITY_TO_STATE.update(_load_city_cache())

_STATE_NAMES_SORTED = sorted(_NG_STATES.keys(), key=len, reverse=True)
_STATE_REGEX = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in _STATE_NAMES_SORTED) + r")\s*(state)?\b",
    re.IGNORECASE,
)


def _normalize_ng_state(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    key = value.strip().lower()
    if key in _NG_STATES:
        return _NG_STATES[key]
    stripped = re.sub(r"\s+state$", "", key).strip()
    return _NG_STATES.get(stripped, value)


def _extract_state_country_from_row(combined: str) -> tuple[str | None, str | None]:
    if not isinstance(combined, str) or not combined.strip():
        return None, None

    text_lower = combined.strip().lower()

    _TERRITORY_NAMES = {"hong kong", "macau", "macao", "puerto rico", "dubai", "taiwan"}
    found_countries: list[str] = []
    for country_lower, country_proper in _WORLD_COUNTRIES_SORTED:
        if re.search(r"\b" + re.escape(country_lower) + r"\b", text_lower):
            if country_lower == "nigeria":
                break
            found_countries.append((country_lower, country_proper))
    if found_countries:
        sovereign = [
            (cl, cp) for cl, cp in found_countries if cl not in _TERRITORY_NAMES
        ]
        best = sovereign[0] if sovereign else found_countries[0]
        return None, best[1]

    _STREET_WORDS_RE = re.compile(
        r"^(street|road|avenue|close|lane|way|crescent|drive|place|court|str|rd|blvd)\b",
        re.IGNORECASE,
    )
    for m in _STATE_REGEX.finditer(text_lower):
        raw_match = m.group(1).lower()
        state = _NG_STATES.get(raw_match)
        if not state:
            continue
        after = text_lower[m.end() :].strip().lstrip(",. |")
        if _STREET_WORDS_RE.match(after):
            continue
        _COMPOUND_ROAD_RE = re.compile(
            r"^\w+\s+(expressway|highway|bypass|motorway|freeway|road|street|way)\b",
            re.IGNORECASE,
        )
        if _COMPOUND_ROAD_RE.match(after):
            continue
        return state, "Nigeria"

    _STREET_SUFFIXES = {
        "street", "road", "avenue", "close", "lane", "way", "crescent", "drive",
        "place", "court", "boulevard", "expressway", "bypass", "highway",
        "freeway", "motorway", "str", "rd", "express",
    }
    tokens = re.split(r"[,|\s]+", text_lower.rstrip("."))
    tokens = [t for t in tokens if t]

    for window in (3, 2, 1):
        if len(tokens) >= window:
            candidate = " ".join(tokens[-window:])
            state = _CITY_TO_STATE.get(candidate)
            if state:
                return state, "Nigeria"

    for i in range(len(tokens)):
        if i + 1 < len(tokens) and tokens[i + 1] in _STREET_SUFFIXES:
            continue
        for window in (3, 2, 1):
            phrase = " ".join(tokens[i : i + window])
            state = _CITY_TO_STATE.get(phrase)
            if state:
                return state, "Nigeria"

    return None, None


def _strip_odoo_prefix(val: Any) -> Any:
    if not isinstance(val, str):
        return val
    if val.startswith("__export__"):
        return None
    return val.strip()


# ===========================================================================
# 5. AI ADDRESS PARSER
# ===========================================================================


def ai_parse_addresses(
    addresses: list[str],
    client: anthropic.Anthropic,
    batch_size: int = 20,
) -> list[dict]:
    empty = {
        "street": None, "street2": None, "city": None,
        "state": None, "zip": None, "country": None,
    }
    if batch_size < 1:
        raise ValueError("Address batch size must be at least 1")

    normalized_addresses = [
        address.strip() if isinstance(address, str) else "" for address in addresses
    ]
    unique_addresses = list(
        dict.fromkeys(address for address in normalized_addresses if address)
    )
    request_count = (len(unique_addresses) + batch_size - 1) // batch_size
    logger.info(
        "AI address parsing: %d rows, %d unique non-empty addresses, %d provider requests at batch size %d",
        len(addresses), len(unique_addresses), request_count, batch_size,
    )
    parsed_by_address: dict[str, dict] = {}

    for i in range(0, len(unique_addresses), batch_size):
        batch = unique_addresses[i : i + batch_size]
        parsed = _ai_address_batch(batch, client)
        parsed_by_address.update(zip(batch, parsed))
        if i + batch_size < len(unique_addresses):
            time.sleep(0.3)

    return [
        parsed_by_address.get(address, empty.copy()) for address in normalized_addresses
    ]


def _ai_address_batch(batch: list[str], client: anthropic.Anthropic) -> list[dict]:
    empty = {
        "street": None, "street2": None, "city": None,
        "state": None, "zip": None, "country": None,
    }

    numbered = {str(i): addr for i, addr in enumerate(batch)}

    system_prompt = (
        "You are an international address parsing specialist. "
        "Return ONLY valid JSON – no prose, no code fences."
    )
    user_prompt = f"""Parse each address string into clean, structured Odoo address components.
These strings may be messy: combined fields, extra tokens, inconsistent formatting.

INPUT (JSON object, key = index, value = raw combined address string):
{json.dumps(numbered, indent=2)}

Return a JSON object where each key is the same index and the value is:
{{
  "street":  "house number + street name only",
  "street2": "estate / area / landmark / additional direction, or null",
  "city":    "city or town name only",
  "state":   "state, county, or province name only",
  "zip":     "postal or zip code, or null",
  "country": "full sovereign country name, or null if genuinely ambiguous"
}}

PARSING RULES — read carefully:
- Extract ONLY what belongs in each field. Do not bleed one field into another.
- "street"  = the actual house/plot number + street name. No city, no state, no country.
- "street2" = estate name, area name, landmark, floor/suite — only if present.
- "city"    = the city or town. NOT the state. Lagos is both a city and a state —
              if the address says "Ikeja, Lagos", then city=Ikeja, state=Lagos.
              If only "Lagos" appears with no other city clue, city=Lagos, state=Lagos.
- "state"   = Nigerian state (Lagos, Ogun, Rivers, FCT, Kano, etc.) or equivalent
              for other countries. NEVER put a city name here.
- "country" = infer from city/state/street context. Default to "Nigeria" only when
              all other signals point to Nigeria. Use null if truly ambiguous.
- Title-case all output values.
- Use null (never empty string) for missing fields.

Return ONLY the JSON object. No prose, no markdown.
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            raw_text = _complete_with_fallback(
                client, system_prompt, user_prompt,
                max_tokens=max(1500, len(batch) * 60),
            )
            raw_text = re.sub(
                r"^```[a-z]*\n?|```$", "", raw_text, flags=re.MULTILINE
            ).strip()
            parsed_map: dict[str, dict] = json.loads(raw_text)
            return [parsed_map.get(str(i), empty.copy()) for i in range(len(batch))]
        except (json.JSONDecodeError, _LLMUnavailable) as exc:
            logger.warning("Address batch attempt %d failed: %s", attempt + 1, exc)
            time.sleep(2**attempt)

    return [empty.copy() for _ in batch]


# ===========================================================================
# 5b. AI COUNTRY / STATE RESOLVER
# ===========================================================================


def ai_resolve_country_state(
    rows: list[dict],
    client: anthropic.Anthropic,
    batch_size: int = 30,
) -> dict[int, dict]:
    results: dict[int, dict] = {}
    empty = {"state": None, "country": None}

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        batch_results = _ai_country_state_batch(batch, client)
        results.update(batch_results)
        if i + batch_size < len(rows):
            time.sleep(0.3)

    return results


def _ai_country_state_batch(
    rows: list[dict],
    client: anthropic.Anthropic,
) -> dict[int, dict]:
    empty = {"state": None, "country": None}
    numbered = {str(r["idx"]): r["combined_address"] for r in rows}

    system_prompt = (
        "You are an international address parsing specialist. "
        "Return ONLY valid JSON – no prose, no code fences."
    )
    user_prompt = f"""For each address string below, identify the country, state/region, and city.
These addresses may be partial, misspelled, or have no space between city and country.

INPUT (JSON object — key = row index, value = raw address text):
{json.dumps(numbered, indent=2)}

Return a JSON object where each key is the same row index and the value is:
{{"state": "...", "country": "...", "city": "..."}}

Rules:
- "country" = full sovereign country name (e.g. "Nigeria", "United Kingdom", "China", "India").
  Infer from city names, street names, postal codes, language patterns, or any other clue.
  Examples: "AJEGUNLE" → Nigeria, "Chichester" → United Kingdom, "New Delhi" → India,
  "Portharcourt" or "PORTHACOURT" (typo) → Nigeria (Rivers State).
- "state" = state, county, province, or region within that country.
  For Nigeria use exact state names: Lagos, Rivers, Ogun, FCT, Kano, etc.
  For UK use county names. For US use state names. For others use province/region.
- "city" = the canonical, correctly-spelled city or town name you identified.
  This is used to build a lookup cache so the same city never needs AI resolution again.
  Use null if no city is identifiable.
- Use null for state/country/city if the address is completely ambiguous (e.g. just a P.O. Box).
- Title-case all values.
- Do NOT default to Nigeria — only use it when you are confident.

Return ONLY the JSON object.
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            raw_text = _complete_with_fallback(
                client, system_prompt, user_prompt, max_tokens=1000
            )
            raw_text = re.sub(
                r"^```[a-z]*\n?|```$", "", raw_text, flags=re.MULTILINE
            ).strip()
            parsed: dict[str, dict] = json.loads(raw_text)
            return {r["idx"]: parsed.get(str(r["idx"]), empty.copy()) for r in rows}
        except (json.JSONDecodeError, _LLMUnavailable) as exc:
            logger.warning(
                "AI country/state batch attempt %d failed: %s", attempt + 1, exc
            )
            time.sleep(2**attempt)

    return {r["idx"]: empty.copy() for r in rows}


# ===========================================================================
# 5c. AI FIELD-LEVEL CLEANER
# ===========================================================================


def ai_clean_flagged_fields(
    df: pd.DataFrame,
    flagged_fields: list[str],
    client: anthropic.Anthropic,
    batch_size: int = 25,
) -> pd.DataFrame:
    for field in flagged_fields:
        if field not in df.columns:
            continue

        mask_dirty = df[field].notna() & (df[field].astype(str).str.strip() != "")
        unique_vals = df.loc[mask_dirty, field].astype(str).unique().tolist()

        if not unique_vals:
            continue

        logger.info(
            "AI field clean: '%s' — %d unique values to check", field, len(unique_vals)
        )

        corrections: dict[str, str | None] = {}
        for i in range(0, len(unique_vals), batch_size):
            batch = unique_vals[i : i + batch_size]
            batch_result = _ai_field_clean_batch(field, batch, client)
            corrections.update(batch_result)
            if i + batch_size < len(unique_vals):
                time.sleep(0.3)

        df[field] = (
            df[field]
            .astype(str)
            .map(lambda v: corrections.get(v, v) if pd.notna(v) and v.strip() else v)
        )
        df[field] = df[field].replace({"None": None, "nan": None, "": None})

    return df


def _ai_field_clean_batch(
    field_name: str,
    values: list[str],
    client: anthropic.Anthropic,
) -> dict[str, str | None]:
    numbered = {str(i): v for i, v in enumerate(values)}

    _field_rules: dict[str, str] = {
        "phone": (
            "Strip any person name or label prefix. Keep only the phone number digits and "
            "leading +. If the value contains no digits at all, return null."
        ),
        "mobile": (
            "Strip any person name or label prefix. Keep only the phone number digits and "
            "leading +. If multiple numbers appear, keep the first. If no digits, return null."
        ),
        "state": (
            "The value should be a Nigerian state name (e.g. Lagos, Kano, Rivers, FCT). "
            "If it is a city name or any non-state value, return null. "
            "Correct obvious typos (e.g. 'Lagod' → 'Lagos'). Return the state name only."
        ),
        "country": (
            "The value should be a country name only (e.g. Nigeria, Ghana, United Kingdom). "
            "If it contains a full address, city, or is not a country name, return null. "
            "Normalise to the standard English country name."
        ),
    }
    rule = _field_rules.get(
        field_name.lower(), "Clean the value — remove noise, fix obvious errors."
    )

    system_prompt = (
        "You are a data cleaning specialist. "
        "Return ONLY valid JSON — no prose, no markdown, no code fences."
    )
    user_prompt = f"""Clean the following values for the Odoo field "{field_name}".

RULE: {rule}

VALUES TO CLEAN (JSON array):
{json.dumps(values, indent=2)}

Return a JSON object mapping each original value to its cleaned version,
or null if the value should be blanked out entirely:
{{
  "original value 1": "cleaned value 1",
  "original value 2": null
}}

Return ONLY the JSON object.
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            raw_text = _complete_with_fallback(
                client, system_prompt, user_prompt, max_tokens=1000
            )
            raw_text = re.sub(
                r"^```[a-z]*\n?|```$", "", raw_text, flags=re.MULTILINE
            ).strip()
            result: dict[str, str | None] = json.loads(raw_text)
            return {
                str(k): (str(v) if v is not None else None) for k, v in result.items()
            }
        except (json.JSONDecodeError, _LLMUnavailable) as exc:
            logger.warning(
                "Field clean batch attempt %d failed for '%s': %s",
                attempt + 1, field_name, exc,
            )
            time.sleep(2**attempt)

    logger.warning(
        "Field clean failed for '%s' — returning values unchanged", field_name
    )
    return {v: v for v in values}


# ===========================================================================
# 6. COLUMN REMAPPER
# ===========================================================================


def apply_column_mapping(
    df: pd.DataFrame,
    mapping: dict[str, str | None],
    schema: dict[str, dict],
    data_type: str,
    client: anthropic.Anthropic,
    flags: dict[str, list[str]] | None = None,
    address_batch_size: int = 20,
) -> pd.DataFrame:
    flags = flags or {"needs_address_split": [], "needs_field_clean": []}
    rename_map: dict[str, str] = {k: v for k, v in mapping.items() if v is not None}
    df = df.rename(columns=rename_map)

    df = df.loc[:, ~df.columns.duplicated(keep="first")]

    _addr_field_map = {
        "street": "Street", "street2": "Street2", "city": "City",
        "state": "State", "zip": "Zip", "country": "Country",
    }
    needs_split_odoo = set()
    for raw_col in flags.get("needs_address_split", []):
        odoo_name = mapping.get(raw_col)
        if odoo_name and odoo_name in df.columns:
            needs_split_odoo.add(odoo_name)
        elif raw_col in df.columns:
            needs_split_odoo.add(raw_col)

    if needs_split_odoo:
        logger.info(
            "AI address splitting flagged columns: %s", sorted(needs_split_odoo)
        )
        combined_addrs = (
            df[sorted(needs_split_odoo)]
            .fillna("")
            .astype(str)
            .apply(lambda row: " | ".join(v.strip() for v in row if v.strip()), axis=1)
            .tolist()
        )
        parsed = ai_parse_addresses(
            combined_addrs, client, batch_size=address_batch_size
        )
        addr_df = pd.DataFrame(parsed)

        for ai_key, odoo_field in _addr_field_map.items():
            parsed_vals = addr_df[ai_key].values
            if odoo_field not in df.columns:
                df[odoo_field] = parsed_vals
            elif odoo_field in needs_split_odoo:
                positions = list(range(len(parsed_vals)))
                for p in positions:
                    if parsed_vals[p] not in (None, ""):
                        df.iloc[p, df.columns.get_loc(odoo_field)] = parsed_vals[p]
            else:
                mask = df[odoo_field].isna() | (
                    df[odoo_field].astype(str).str.strip() == ""
                )
                positions = mask.to_numpy().nonzero()[0]
                df.iloc[positions, df.columns.get_loc(odoo_field)] = [
                    parsed_vals[p] for p in positions
                ]

        for col in needs_split_odoo:
            if col in df.columns and col not in _addr_field_map.values():
                df.drop(columns=[col], inplace=True, errors="ignore")

    needs_clean = flags.get("needs_field_clean", [])
    if needs_clean:
        logger.info("AI field cleaning flagged fields: %s", needs_clean)
        df = ai_clean_flagged_fields(df, needs_clean, client)

    _country_col = next(
        (c for c in df.columns if c.lower() in ("country", "country_id")), None
    )
    _state_col = next(
        (c for c in df.columns if c.lower() in ("state", "state_id")), None
    )
    _addr_hint_keys = {
        "street", "street2", "city", "area", "location", "region",
        "district", "child_ids/street",
    }
    _addr_text_cols = [
        c
        for c in df.columns
        if c.lower() in _addr_hint_keys
        or any(k in c.lower() for k in ("street", "address", "addr", "city"))
        and "type" not in c.lower()
    ]

    _unresolved: list[dict] = []
    for idx, row in df.iterrows():
        country_blank = (
            _country_col is None
            or pd.isna(row.get(_country_col))
            or str(row.get(_country_col, "")).strip() in ("", "None")
        )
        state_blank = (
            _state_col is None
            or pd.isna(row.get(_state_col))
            or str(row.get(_state_col, "")).strip() in ("", "None")
        )
        if not (country_blank or state_blank):
            continue

        parts = [
            str(row[c]).strip()
            for c in _addr_text_cols
            if isinstance(row.get(c), str)
            and row[c].strip()
            and row[c].strip().lower() not in ("false", "none", "nan")
        ]
        combined = " | ".join(parts)
        if combined.strip():
            _unresolved.append({"idx": idx, "combined_address": combined})

    if _unresolved:
        logger.info(
            "AI country/state fallback: resolving %d unresolved rows …",
            len(_unresolved),
        )
        ai_geo = ai_resolve_country_state(_unresolved, client)

        for item in _unresolved:
            idx = item["idx"]
            resolved = ai_geo.get(idx, {})
            ai_state = resolved.get("state")
            ai_country = resolved.get("country")

            if (
                _country_col
                and ai_country
                and (
                    pd.isna(df.at[idx, _country_col])
                    or str(df.at[idx, _country_col]).strip() in ("", "None")
                )
            ):
                df.at[idx, _country_col] = ai_country

            if (
                _state_col
                and ai_state
                and (
                    pd.isna(df.at[idx, _state_col])
                    or str(df.at[idx, _state_col]).strip() in ("", "None")
                )
            ):
                df.at[idx, _state_col] = ai_state

        resolved_count = sum(
            1 for item in _unresolved if ai_geo.get(item["idx"], {}).get("country")
        )
        logger.info(
            "AI country/state fallback: resolved %d/%d rows",
            resolved_count, len(_unresolved),
        )

        new_entries: dict[str, str] = {}
        for item in _unresolved:
            resolved = ai_geo.get(item["idx"], {})
            ai_city = resolved.get("city")
            ai_state = resolved.get("state")
            ai_ctry = resolved.get("country")
            if ai_city and ai_state and ai_ctry == "Nigeria":
                city_key = ai_city.strip().lower()
                if city_key and city_key not in _CITY_TO_STATE:
                    new_entries[city_key] = ai_state
                    _CITY_TO_STATE[city_key] = ai_state

        if new_entries:
            existing_cache = {}
            if _CITY_CACHE_PATH.exists():
                try:
                    with _CITY_CACHE_PATH.open("r", encoding="utf-8") as fh:
                        existing_cache = json.load(fh)
                except Exception:
                    pass
            existing_cache.update(new_entries)
            _save_city_cache(existing_cache)
            logger.info(
                "City cache: added %d new entries %s",
                len(new_entries), list(new_entries.items())[:5],
            )

    known_cols = set(schema.keys())
    cols_to_keep = [c for c in df.columns if c in known_cols]
    df = df[cols_to_keep].copy()

    if data_type == "customer" and "Is a Company" not in df.columns and "Name" in df.columns:
        df["Is a Company"] = df["Name"].apply(infer_is_company)
        logger.info("Inferred 'Is a Company' from mapped customer names")

    for field, meta in schema.items():
        if field not in df.columns:
            df[field] = meta["default"]

    df = df[[f for f in schema.keys() if f in df.columns]]

    return df


# ===========================================================================
# 7. VALIDATOR
# ===========================================================================

_INTERNAL_ENTRY_PATTERNS = re.compile(
    r"\b("
    r"bad\s*&?\s*damage|damaged\s+goods|missing\s+items?|"
    r"shortage|suspense|suspence|"
    r"write[\s\-]?off|stock\s+adjustment|inventory\s+adjustment|"
    r"reconciliation\s+a/?c|stale\s+cheques?|"
    r"container\s+deposit"
    r")\b",
    re.IGNORECASE,
)


def detect_internal_entries(
    df: pd.DataFrame,
    name_col: str,
    category_col: str | None,
    client: anthropic.Anthropic | None,
) -> dict[int, str]:
    flagged: dict[int, str] = {}
    if name_col not in df.columns:
        return flagged

    names = df[name_col].fillna("").astype(str)

    for pos, name in enumerate(names):
        if not name.strip():
            continue
        m = _INTERNAL_ENTRY_PATTERNS.search(name)
        if m:
            flagged[pos] = (
                f"Looks like an internal accounting entry (matched: '{m.group(0)}')"
            )

    if client is not None:
        remaining_positions = [
            p for p in range(len(names)) if p not in flagged and names.iloc[p].strip()
        ]
        if remaining_positions:
            sample = _sample_for_keyword_discovery(names, remaining_positions)
            discovered_terms = _ai_discover_internal_keywords(sample, client)

            if discovered_terms:
                logger.info(
                    "Internal-entry keyword discovery found: %s", discovered_terms
                )
                discovered_regex = re.compile(
                    r"\b(" + "|".join(re.escape(t) for t in discovered_terms) + r")\b",
                    re.IGNORECASE,
                )
                for pos in remaining_positions:
                    name = names.iloc[pos].strip()
                    m = discovered_regex.search(name)
                    if m:
                        flagged[pos] = (
                            f"Looks like an internal accounting entry specific to this file "
                            f"(matched: '{m.group(0)}')"
                        )
            else:
                logger.info(
                    "Internal-entry keyword discovery found nothing — file looks clean"
                )

    if flagged:
        logger.info(
            "Internal-entry detection: %d rows flagged for review", len(flagged)
        )
    return flagged


def _sample_for_keyword_discovery(
    names: pd.Series,
    candidate_positions: list[int],
    max_sample: int = 60,
) -> list[str]:
    short_shaped = []
    other = []
    for pos in candidate_positions:
        name = names.iloc[pos].strip()
        words = name.split()
        if len(words) <= 4 and not any(ch.isdigit() for ch in name):
            short_shaped.append(name)
        else:
            other.append(name)

    sample = short_shaped[:max_sample]
    if len(sample) < max_sample:
        sample.extend(other[: max_sample - len(sample)])
    return sample


def _ai_discover_internal_keywords(
    sample_names: list[str],
    client: anthropic.Anthropic,
) -> list[str]:
    system_prompt = (
        "You are a data quality specialist reviewing an Odoo ERP customer/vendor import "
        "from an arbitrary client spreadsheet. Column names, language, and conventions vary "
        "by client. Return ONLY valid JSON — no prose, no code fences."
    )
    user_prompt = f"""Here is a sample of {len(sample_names)} names from a customer/vendor list:

{json.dumps(sample_names, indent=2)}

Most of these are real customer or vendor names (people or businesses) and should be
left alone. A SMALL NUMBER may instead be internal accounting/bookkeeping entries that
were mixed into this list by mistake — e.g. write-offs, suspense accounts, shortage or
damage claims, reconciliation buckets, regulatory/customs labels, or similar internal
line items that do not refer to an actual person or company.

Look for any such internal entries in this sample. For each one you find, extract the
SHORT distinguishing keyword or phrase that identifies it as internal (not the whole
name — just the part that signals "this is bookkeeping, not a customer").

Do NOT flag real business names just because they are short or generic-sounding —
e.g. "Amir Bakery", "Cornetta", "Big Basket" are real businesses, not internal entries.
Only flag things that are clearly accounting/operational in nature.

Return a JSON object:
{{
  "found_internal_entries": true/false,
  "keywords": ["keyword or short phrase", ...]
}}

If you find none, return {{"found_internal_entries": false, "keywords": []}}.
Return ONLY the JSON object.
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            raw_text = _complete_with_fallback(
                client, system_prompt, user_prompt, max_tokens=500
            )
            raw_text = re.sub(
                r"^```[a-z]*\n?|```$", "", raw_text, flags=re.MULTILINE
            ).strip()
            parsed = json.loads(raw_text)
            if not parsed.get("found_internal_entries"):
                return []
            keywords = [
                k.strip() for k in parsed.get("keywords", []) if k and k.strip()
            ]
            return keywords
        except (json.JSONDecodeError, _LLMUnavailable) as exc:
            logger.warning(
                "Internal-entry keyword discovery attempt %d failed: %s",
                attempt + 1, exc,
            )
            time.sleep(2**attempt)

    return []


def detect_duplicates(
    df: pd.DataFrame,
    name_col: str,
    address_col: str | None,
    client: anthropic.Anthropic | None,
) -> dict[int, dict]:
    flagged: dict[int, dict] = {}
    if name_col not in df.columns:
        return flagged

    names = df[name_col].fillna("").astype(str)

    def _collapse(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    collapsed = names.apply(_collapse)

    groups: dict[str, list[int]] = {}
    for pos, key in enumerate(collapsed):
        if not key:
            continue
        groups.setdefault(key, []).append(pos)
    candidate_groups = {k: v for k, v in groups.items() if len(v) > 1}

    if not candidate_groups:
        return flagged

    logger.info(
        "Duplicate detection: %d candidate name-collision groups found",
        len(candidate_groups),
    )

    if address_col is None or address_col not in df.columns or client is None:
        logger.info(
            "Duplicate detection: no address column or no client available — "
            "skipping AI confirmation, nothing flagged (name match alone is not reliable)"
        )
        return flagged

    addresses = df[address_col].fillna("").astype(str)

    group_items = list(candidate_groups.items())
    batch_size = 15

    for i in range(0, len(group_items), batch_size):
        batch = group_items[i : i + batch_size]
        batch_payload = {}
        for gi, (_, positions) in enumerate(batch):
            batch_payload[str(gi)] = [
                {"name": names.iloc[p], "address": addresses.iloc[p]} for p in positions
            ]
        ai_results = _ai_confirm_duplicates_batch(batch_payload, client)

        for gi, (_, positions) in enumerate(batch):
            verdicts = ai_results.get(str(gi), [])
            for j in range(1, len(positions)):
                is_dupe = verdicts[j - 1] if (j - 1) < len(verdicts) else False
                if is_dupe:
                    flagged[positions[j]] = {
                        "duplicate_of": positions[0],
                        "reason": (
                            f"Likely duplicate of row {positions[0] + 2} "
                            f"(same name and address — AI confirmed)"
                        ),
                    }

        if i + batch_size < len(group_items):
            time.sleep(0.3)

    if flagged:
        logger.info(
            "Duplicate detection: %d rows flagged as duplicates of an earlier row",
            len(flagged),
        )
    return flagged


def _merge_confirmed_duplicates(
    df: pd.DataFrame,
    duplicate_flags: dict[int, dict],
) -> tuple[pd.DataFrame, dict[int, dict]]:
    if not duplicate_flags:
        return df, {}

    row_count = len(df)
    parents = list(range(row_count))

    def find_root(position: int) -> int:
        while parents[position] != position:
            parents[position] = parents[parents[position]]
            position = parents[position]
        return position

    def union(left: int, right: int) -> None:
        left_root = find_root(left)
        right_root = find_root(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for duplicate_pos, info in duplicate_flags.items():
        original_pos = info.get("duplicate_of")
        if (
            isinstance(duplicate_pos, int)
            and isinstance(original_pos, int)
            and 0 <= duplicate_pos < row_count
            and 0 <= original_pos < row_count
        ):
            union(duplicate_pos, original_pos)

    groups: dict[int, list[int]] = {}
    for position in range(row_count):
        groups.setdefault(find_root(position), []).append(position)
    groups = {root: positions for root, positions in groups.items() if len(positions) > 1}

    def is_blank_or_default(field: str, value: Any) -> bool:
        if pd.isna(value):
            return True
        if isinstance(value, str) and value.strip().lower() in ("", "none", "nan", "<na>"):
            return True
        if field in ("Customer Rank", "Supplier Rank"):
            try:
                return float(value) == 1.0
            except (TypeError, ValueError):
                return False
        if field == "Credit Limit":
            try:
                return float(value) == 0.0
            except (TypeError, ValueError):
                return False
        return False

    def completeness(position: int) -> int:
        return sum(
            not is_blank_or_default(field, df.iat[position, column_pos])
            for column_pos, field in enumerate(df.columns)
        )

    merged_df = df.copy(deep=True)
    merged_flags: dict[int, dict] = {}
    merged_group_count = 0

    for positions in groups.values():
        if len(positions) < 2:
            continue
        canonical_pos = max(positions, key=lambda pos: (completeness(pos), -pos))
        donors = sorted(
            (pos for pos in positions if pos != canonical_pos),
            key=lambda pos: (-completeness(pos), pos),
        )

        for column_pos, field in enumerate(merged_df.columns):
            if not is_blank_or_default(field, merged_df.iat[canonical_pos, column_pos]):
                continue
            for donor_pos in donors:
                donor_value = merged_df.iat[donor_pos, column_pos]
                if not is_blank_or_default(field, donor_value):
                    merged_df.iat[canonical_pos, column_pos] = donor_value
                    break

        canonical_excel_row = canonical_pos + 2
        for duplicate_pos in positions:
            if duplicate_pos == canonical_pos:
                continue
            merged_flags[duplicate_pos] = {
                "duplicate_of": canonical_pos,
                "reason": (
                    f"Duplicate of row {canonical_excel_row}; fields were merged "
                    "into the most complete record"
                ),
            }
        merged_group_count += 1

    logger.info(
        "Duplicate merge: consolidated %d confirmed groups; flagged %d extra rows",
        merged_group_count, len(merged_flags),
    )
    return merged_df, merged_flags


def _ai_confirm_duplicates_batch(
    batch_payload: dict[str, list[dict]],
    client: anthropic.Anthropic,
) -> dict[str, list[bool]]:
    system_prompt = (
        "You are a data deduplication specialist for an Odoo ERP migration. "
        "Return ONLY valid JSON — no prose, no code fences."
    )
    user_prompt = f"""Each group below contains rows whose names are nearly identical after
removing punctuation/spacing. Your job: decide if the LATER rows in each group
describe the SAME real-world customer/vendor as the FIRST row, or a DIFFERENT
one (e.g. two separate branches of the same chain in different areas/cities).

INPUT (JSON object — key = group index, value = list of {{name, address}}, in order):
{json.dumps(batch_payload, indent=2)}

For each group, compare every row AFTER the first one to the FIRST row in
that group. Use BOTH name and address — if the addresses clearly describe
different locations (different street, different area, different city),
they are DIFFERENT entities even if the names are nearly identical (this
commonly happens with multiple branches of the same business).

Return a JSON object where each key is the same group index and the value is
a list of booleans — one per row after the first — true if that row is the
SAME entity as the group's first row, false if it is a different branch/entity:
{{
  "0": [true],
  "1": [false]
}}

Return ONLY the JSON object.
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            raw_text = _complete_with_fallback(
                client, system_prompt, user_prompt, max_tokens=1500
            )
            raw_text = re.sub(
                r"^```[a-z]*\n?|```$", "", raw_text, flags=re.MULTILINE
            ).strip()
            parsed: dict[str, list[bool]] = json.loads(raw_text)
            return parsed
        except (json.JSONDecodeError, _LLMUnavailable) as exc:
            logger.warning(
                "Duplicate confirmation attempt %d failed: %s", attempt + 1, exc
            )
            time.sleep(2**attempt)

    return {}


def detect_suspicious_is_company_flags(
    df: pd.DataFrame,
    name_col: str,
    contact_name_col: str | None,
    is_company_col: str | None,
) -> dict[int, str]:
    flagged: dict[int, str] = {}
    if name_col not in df.columns or contact_name_col is None or is_company_col is None:
        return flagged
    if contact_name_col not in df.columns or is_company_col not in df.columns:
        return flagged

    names = df[name_col].fillna("").astype(str)
    contacts = df[contact_name_col].fillna("").astype(str)
    is_company_vals = df[is_company_col]

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower())

    for pos in range(len(df)):
        name = names.iloc[pos].strip()
        contact = contacts.iloc[pos].strip()
        if not name or not contact:
            continue

        same_value = _norm(name) == _norm(contact)
        if not same_value:
            continue

        is_company_val = is_company_vals.iloc[pos]
        marked_true = is_company_val is True or str(is_company_val).strip().lower() in (
            "true", "1", "yes",
        )
        if not marked_true:
            continue

        looks_personal = infer_is_company(name) is False
        if not looks_personal:
            continue

        flagged[pos] = (
            f"'Is a Company' is set to True, but '{name_col}' and '{contact_name_col}' "
            f"both hold the same value ('{name}') and the name looks like a person, "
            f"not a business — please confirm whether this should be 'Is a Company' = False"
        )

    if flagged:
        logger.info(
            "Is-a-Company mismatch detection: %d rows flagged for review", len(flagged)
        )
    return flagged


def validate_and_split(
    df: pd.DataFrame,
    data_type: str,
    version: str = "v19",
    client: anthropic.Anthropic | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[int], dict[str, int]]:
    mandatory_list = MANDATORY_FIELD[data_type][version]
    name_col = mandatory_list[0]
    category_col = next((c for c in df.columns if c.lower() == "category"), None)
    address_col = next((c for c in df.columns if c.lower() == "street"), None)
    contact_name_col = next(
        (c for c in df.columns if c.lower() == "contacts / name"), None
    )
    is_company_col = next((c for c in df.columns if c.lower() == "is a company"), None)

    duplicate_flags = detect_duplicates(df, name_col, address_col, client)
    df, duplicate_flags = _merge_confirmed_duplicates(df, duplicate_flags)
    internal_flags = detect_internal_entries(df, name_col, category_col, client)
    is_company_flags = detect_suspicious_is_company_flags(
        df, name_col, contact_name_col, is_company_col
    )

    errors: list[dict] = []
    error_positions: list[int] = []
    breakdown = {
        "clean": 0,
        "missing_mandatory_field": 0,
        "duplicate_merged": 0,
        "flagged_internal": 0,
        "suspicious_is_company_flag": 0,
    }

    for pos, (_, row) in enumerate(df.iterrows()):
        reason_code: str | None = None
        reason_text: str | None = None

        # Check ALL mandatory fields for this version (v19 = ["Name"],
        # v20 = ["Name", "Email", "Phone"]). A row is only flagged if
        # at least one required field is blank.
        missing_fields = []
        for field in mandatory_list:
            val = row.get(field)
            if pd.isna(val) or (isinstance(val, str) and not val.strip()):
                missing_fields.append(field)

        if missing_fields:
            reason_code = "missing_mandatory_field"
            reason_text = f"Missing mandatory field(s): {', '.join(missing_fields)}"

        elif pos in duplicate_flags:
            dup_of = duplicate_flags[pos]["duplicate_of"]
            reason_code = f"duplicate_of_row_{dup_of + 2}"
            reason_text = duplicate_flags[pos]["reason"]

        elif pos in internal_flags:
            reason_code = "flagged_internal_entry"
            reason_text = internal_flags[pos]

        elif pos in is_company_flags:
            reason_code = "suspicious_is_company_flag"
            reason_text = is_company_flags[pos]

        if reason_code:
            err_row = row.to_dict()
            err_row["_reason_code"] = reason_code
            err_row["_errors"] = reason_text
            err_row["_source_row"] = pos + 2
            errors.append(err_row)
            error_positions.append(pos)

            if reason_code == "missing_mandatory_field":
                breakdown["missing_mandatory_field"] += 1
            elif reason_code.startswith("duplicate_of_row_"):
                breakdown["duplicate_merged"] += 1
            elif reason_code == "flagged_internal_entry":
                breakdown["flagged_internal"] += 1
            elif reason_code == "suspicious_is_company_flag":
                breakdown["suspicious_is_company_flag"] += 1
        else:
            breakdown["clean"] += 1

    error_columns = [*df.columns, "_reason_code", "_errors", "_source_row"]
    error_df = pd.DataFrame(errors, columns=error_columns)

    logger.info(
        "Validation breakdown: %s",
        json.dumps(breakdown, indent=2),
    )
    return df, error_df, error_positions, breakdown


# ===========================================================================
# 7e. OUTPUT WORKBOOK STYLING
# ===========================================================================

_HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True)


def _style_worksheet(ws, min_width: int = 8, max_width: int = 40) -> None:
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT

    for col_idx in range(1, ws.max_column + 1):
        longest = 0
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
            cell = row[0]
            if cell.value is not None:
                longest = max(longest, len(str(cell.value)))
        width = min(max(longest + 2, min_width), max_width)
        ws.column_dimensions[get_column_letter(col_idx)].width = width


# ===========================================================================
# 8. MAIN PIPELINE ORCHESTRATOR
# ===========================================================================


def process_file(
    input_path: str | Path,
    data_type: str,  # "customer" or "vendor"
    version: str = "v19",  # Added version parameter
    output_path: str | Path | None = None,
    api_key: str | None = None,
    address_batch_size: int = 20,
) -> dict:
    input_path = Path(input_path)
    
    # This will automatically throw an error if version is not supported (e.g. v18 or v20)
    schema = get_schema(data_type, version)

    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_ODOO_READY.xlsx"
    output_path = Path(output_path)

    client = anthropic.Anthropic(
        api_key=api_key, max_retries=ANTHROPIC_MAX_RETRIES
    )

    try:
        stage_started = time.perf_counter()
        df_raw = load_raw_file(input_path)
        df_raw = ai_normalise_structure(df_raw, input_path, client)
        total_rows = len(df_raw)
        logger.info(
            "Pipeline stage 'load and structure' completed in %.2fs",
            time.perf_counter() - stage_started,
        )

        sample_rows = df_raw.head(5).to_dict(orient="records")

        logger.info("Running AI column mapping …")
        stage_started = time.perf_counter()
        mapping, flags = ai_map_columns(
            raw_columns=list(df_raw.columns),
            target_schema=schema,
            data_type=data_type,
            version=version,
            client=client,
            sample_rows=sample_rows,
        )
        logger.info(
            "Pipeline stage 'column mapping' completed in %.2fs",
            time.perf_counter() - stage_started,
        )
        logger.info("Column mapping: %s", json.dumps(mapping, indent=2))
        logger.info("Quality flags: %s", json.dumps(flags, indent=2))

        mapped_source_columns = [
            source_col
            for source_col, target_field in mapping.items()
            if target_field in schema and source_col in df_raw.columns
        ]
        if not mapped_source_columns:
            raise RuntimeError(
                "AI column mapping did not map any source column to the selected Odoo schema. "
                "No cleaned workbook was generated. Check the AI provider API key or source columns."
            )

        has_mapped_source_data = any(
            pd.notna(value) and not (isinstance(value, str) and not value.strip())
            for source_col in mapped_source_columns
            for value in df_raw[source_col]
        )
        if not has_mapped_source_data:
            raise RuntimeError(
                "All source values mapped to Odoo fields are empty. "
                "No cleaned workbook was generated."
            )

        stage_started = time.perf_counter()
        df_clean = rule_based_clean(df_raw.copy(), data_type)
        logger.info(
            "Pipeline stage 'pre-mapping cleaning' completed in %.2fs",
            time.perf_counter() - stage_started,
        )

        stage_started = time.perf_counter()
        df_mapped = apply_column_mapping(
            df_clean,
            mapping,
            schema,
            data_type,
            client,
            flags=flags,
            address_batch_size=address_batch_size,
        )

        df_mapped = rule_based_clean(df_mapped, data_type)
        logger.info(
            "Pipeline stage 'mapping and post-mapping cleaning' completed in %.2fs",
            time.perf_counter() - stage_started,
        )

        stage_started = time.perf_counter()
        df_final, df_errors, error_positions, breakdown = validate_and_split(
            df_mapped, data_type, version=version,client=client
        )
        logger.info(
            "Pipeline stage 'validation' completed in %.2fs",
            time.perf_counter() - stage_started,
        )
        clean_count = breakdown["clean"]

        stage_started = time.perf_counter()
        error_position_set = set(error_positions)
        clean_mask = [i not in error_position_set for i in range(len(df_final))]
        df_cleaned = df_final.iloc[clean_mask]

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df_cleaned.to_excel(writer, sheet_name="Cleaned", index=False)
            df_final.to_excel(writer, sheet_name="Data", index=False)
            df_errors.to_excel(writer, sheet_name="Errors", index=False)

            if error_positions:
                fill = PatternFill(
                    start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"
                )
                ws = writer.sheets["Data"]
                for pos in error_positions:
                    excel_row = pos + 2
                    for cell in ws[excel_row]:
                        cell.fill = fill

            for sheet_name in ("Cleaned", "Data", "Errors"):
                if sheet_name in writer.sheets:
                    _style_worksheet(writer.sheets[sheet_name])

        logger.info("Output written to '%s'", output_path)
        logger.info(
            "Pipeline stage 'workbook writing' completed in %.2fs",
            time.perf_counter() - stage_started,
        )

        status = "success" if df_errors.empty else "partial"

        message_parts = [f"Processed {total_rows} rows → {clean_count} clean"]
        if breakdown["duplicate_merged"]:
            message_parts.append(f"{breakdown['duplicate_merged']} possible duplicates")
        if breakdown["missing_mandatory_field"]:
            message_parts.append(
                f"{breakdown['missing_mandatory_field']} missing required fields"
            )
        if breakdown["flagged_internal"]:
            message_parts.append(
                f"{breakdown['flagged_internal']} flagged as internal entries"
            )
        if breakdown["suspicious_is_company_flag"]:
            message_parts.append(
                f"{breakdown['suspicious_is_company_flag']} with a suspicious 'Is a Company' value"
            )

        return {
            "status": status,
            "message": ", ".join(message_parts) + ".",
            "output_path": str(output_path),
            "stats": {
                "total": total_rows,
                "clean": clean_count,
                "errors": len(df_errors),
                "missing_mandatory_field": breakdown["missing_mandatory_field"],
                "duplicate_merged": breakdown["duplicate_merged"],
                "flagged_internal": breakdown["flagged_internal"],
                "suspicious_is_company_flag": breakdown["suspicious_is_company_flag"],
            },
        }

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        return {
            "status": "error",
            "message": str(exc),
            "output_path": None,
            "stats": {
                "total": 0,
                "clean": 0,
                "errors": 0,
                "missing_mandatory_field": 0,
                "duplicate_merged": 0,
                "flagged_internal": 0,
                "suspicious_is_company_flag": 0,
            },
        }


# ===========================================================================
# 9. CLI ENTRY POINT
# ===========================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Odoo Data Migration Engine")
    parser.add_argument("input", help="Path to raw input file (.xlsx / .csv)")
    parser.add_argument("data_type", choices=["customer", "vendor"], help="Record type")
    parser.add_argument("--version", default="v19", choices=["v19", "v20"], help="Odoo version")
    parser.add_argument("--output", default=None, help="Output file path (optional)")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Address parse batch size (default: 20)",
    )
    args = parser.parse_args()

    result = process_file(
        input_path=args.input,
        data_type=args.data_type,
        version=args.version,
        output_path=args.output,
        api_key=args.api_key,
        address_batch_size=args.batch_size,
    )

    print(json.dumps(result, indent=2))