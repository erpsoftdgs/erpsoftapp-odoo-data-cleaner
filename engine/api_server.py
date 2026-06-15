"""
FastAPI Backend for Odoo Data Migration Engine
================================================
Exposes /api/clean-data for Next.js frontend integration.

Run:  uvicorn api_server:app --reload --port 8000
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

# Searches from this file upward, so the project-root .env (one level up
# from engine/) is picked up regardless of the process's working directory.
load_dotenv()

from odoo_data_engine import process_file

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Odoo Data Migration API",
    description="AI-powered spreadsheet cleaning for Odoo ERP imports.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # Restrict to your Next.js domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("tmp/uploads")
OUTPUT_DIR = Path("tmp/outputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


# ---------------------------------------------------------------------------
# POST /api/clean-data
# ---------------------------------------------------------------------------
@app.post("/api/clean-data")
async def clean_data(
    file: UploadFile = File(..., description="Raw spreadsheet (.xlsx or .csv)"),
    data_type: str = Form(..., description="'customer' or 'vendor'"),
):
    """
    Accept a raw spreadsheet upload, run the full cleaning pipeline,
    and return a download link for the cleaned file.

    Form fields:
      - file      : multipart file upload
      - data_type : 'customer' or 'vendor'
    """
    if data_type not in ("customer", "vendor"):
        raise HTTPException(400, detail="data_type must be 'customer' or 'vendor'")

    allowed_extensions = {".xlsx", ".xls", ".csv"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(400, detail=f"Unsupported file type: {suffix}. Use .xlsx or .csv")

    # Save upload with unique name
    job_id = uuid.uuid4().hex[:8]
    input_path  = UPLOAD_DIR / f"{job_id}_input{suffix}"
    output_path = OUTPUT_DIR / f"{job_id}_cleaned.xlsx"
    error_path  = OUTPUT_DIR / f"{job_id}_errors.xlsx"

    try:
        with input_path.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
    finally:
        await file.close()

    # Run pipeline
    result = process_file(
        input_path=input_path,
        data_type=data_type,
        output_path=output_path,
        api_key=ANTHROPIC_API_KEY,
    )

    if result["status"] == "error":
        raise HTTPException(500, detail=result["message"])

    # Build download URLs
    base_url = "/api/download"
    response_payload = {
        "job_id":           job_id,
        "status":           result["status"],
        "message":          result["message"],
        "stats":            result["stats"],
        "download_url":     f"{base_url}/{job_id}_cleaned.xlsx",
        "error_log_url":    f"{base_url}/{job_id}_errors.xlsx" if result["error_log_path"] else None,
    }
    return JSONResponse(content=response_payload)


# ---------------------------------------------------------------------------
# GET /api/download/{filename}
# ---------------------------------------------------------------------------
@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Serve a processed output file for download."""
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(404, detail="File not found or has expired.")
    return FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "api_key_set": bool(ANTHROPIC_API_KEY),
        "openrouter_fallback_set": bool(OPENROUTER_API_KEY),
    }
