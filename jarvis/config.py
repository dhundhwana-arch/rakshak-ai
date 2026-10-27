"""
jarvis/config.py
----------------
Central configuration for JARVIS-OMEGA.
Loads environment variables, defines system paths, API keys,
security policy, and agent behaviour constants.

Zero-budget design: no paid services required. All paths resolve
relative to the `jarvis/` package so it runs identically on PC
and Android Termux.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent          # .../jarvis
PROJECT_ROOT = BASE_DIR                             # the JARVIS project itself
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "jarvis_omega.db"
SANDBOX_DIR = BASE_DIR / "workspace"                # default agent workspace

# Ensure data directories exist at import time.
for _d in (DATA_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _load_env_file(path: Path) -> None:
    """Minimal stdlib .env loader (no python-dotenv dependency).

    Existing environment variables always win, so `export FOO=bar` in the
    shell overrides the file. Lines may be `KEY=VALUE`, `KEY="VALUE"`,
    comments (`#`) and blank lines are skipped.
    """
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key and value:
                os.environ.setdefault(key, value)
    except Exception:  # noqa: BLE001
        pass  # a broken .env must never prevent startup


ENV_FILE = BASE_DIR / ".env"
_load_env_file(ENV_FILE)                 # jarvis/.env
_load_env_file(BASE_DIR.parent / ".env")  # repo-root .env (fallback)

# Root directory the agents are allowed to touch (file manager + shell cwd).
# Defaults to jarvis/workspace/ so generated files never pollute the app
# source tree. Point JARVIS_WORKSPACE at another directory (e.g. the project
# root) if you want agents to browse/edit your actual code.
WORKSPACE_DIR = Path(
    os.environ.get("JARVIS_WORKSPACE") or str(SANDBOX_DIR)
).expanduser().resolve()

SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# API / LLM configuration
# ---------------------------------------------------------------------------
# Google Gemini (Google GenAI SDK). Set GEMINI_API_KEY in the environment
# or in a `.env` file at the project root. Free tier is sufficient.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip()
GEMINI_TEMPERATURE = float(os.environ.get("GEMINI_TEMPERATURE", "0.7") or "0.7")
GEMINI_MAX_TOKENS = int(os.environ.get("GEMINI_MAX_TOKENS", "2048") or "2048")

# Optional local AI hook (e.g. Ollama / llama.cpp) — disabled by default.
LOCAL_AI_BASE_URL = os.environ.get("LOCAL_AI_BASE_URL", "").strip()
LOCAL_AI_MODEL = os.environ.get("LOCAL_AI_MODEL", "").strip()

# ---------------------------------------------------------------------------
# Server configuration
# ---------------------------------------------------------------------------
HOST = os.environ.get("JARVIS_HOST", "0.0.0.0")
PORT = int(os.environ.get("JARVIS_PORT", "8000") or "8000")
DEBUG = os.environ.get("JARVIS_DEBUG", "false").lower() in ("1", "true", "yes")
CORS_ORIGINS = [o.strip() for o in os.environ.get("JARVIS_CORS_ORIGINS", "*").split(",") if o.strip()]

# ---------------------------------------------------------------------------
# Security / sandbox policy (System Agent + shell tool)
# ---------------------------------------------------------------------------
# Commands that are never allowed, even as a substring of the full command.
BLOCKED_COMMAND_PATTERNS = [
    "rm -rf /",
    "rm -rf~",
    ":(){ :|:& };:",          # fork bomb
    "mkfs",
    "dd if=",
    "> /dev/sda",
    "chmod -R 777 /",
    "chown -R root /",
    "mkfs.",
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
    "halt",
    "poweroff",
]

# Binaries that are never allowed to execute.
BLOCKED_BINARIES = {
    "mkfs", "fdisk", "parted", "shutdown", "reboot", "halt", "poweroff", "init",
}

# Max seconds a shell command may run before being terminated.
SHELL_TIMEOUT_SECONDS = int(os.environ.get("JARVIS_SHELL_TIMEOUT", "30") or "30")
# Max output bytes returned from a shell command.
SHELL_MAX_OUTPUT_BYTES = int(os.environ.get("JARVIS_SHELL_MAX_OUTPUT", "65536") or "65536")

# ---------------------------------------------------------------------------
# Multi-agent behaviour
# ---------------------------------------------------------------------------
MAX_ORCHESTRATION_ITERATIONS = int(os.environ.get("JARVIS_MAX_ITERATIONS", "5") or "5")
AGENT_STREAM_DELAY = float(os.environ.get("JARVIS_STREAM_DELAY", "0.0") or "0.0")

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Return True if a usable LLM backend (Gemini key or local AI) is present."""
    return bool(GEMINI_API_KEY) or bool(LOCAL_AI_BASE_URL)
