"""Load engine settings from OS variables, then the project-root .env file."""

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

# Keep non-empty runtime/Docker values; let .env fill missing or empty values.
RUNTIME_ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
if ENV_FILE_PATH.is_file():
    for variable_name in dotenv_values(ENV_FILE_PATH):
        if not (os.environ.get(variable_name) or "").strip():
            os.environ.pop(variable_name, None)

load_dotenv(dotenv_path=ENV_FILE_PATH, override=False)

ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip() or None
if RUNTIME_ANTHROPIC_API_KEY:
    ANTHROPIC_API_KEY_SOURCE = "process environment"
elif ANTHROPIC_API_KEY:
    ANTHROPIC_API_KEY_SOURCE = str(ENV_FILE_PATH)
else:
    ANTHROPIC_API_KEY_SOURCE = "not configured"

OPENROUTER_API_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip() or None
OPENROUTER_MODEL = (
    os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free").strip()
    or "meta-llama/llama-3.3-70b-instruct:free"
)
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip() or None
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip() or "gemini-3.1-flash-lite"

ANTHROPIC_MAX_RETRIES = int(os.getenv("ANTHROPIC_MAX_RETRIES") or 3)
ANTHROPIC_RATE_LIMIT_RPM = float(os.getenv("RATE_LIMIT_RPM") or 5)
GEMINI_RATE_LIMIT_RPM = float(os.getenv("GEMINI_RATE_LIMIT_RPM") or 15)
