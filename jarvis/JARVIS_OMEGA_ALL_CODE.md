# JARVIS-OMEGA — Complete Source Code

Every file of the framework, verbatim. 22 files · 4,972 lines.

## Quick start

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your-free-key"   # optional, enables full reasoning
uvicorn main:app --host 0.0.0.0 --port 8000
# then open http://localhost:8000
```

## File index

| # | File | Purpose | Lines |
|---|---|---|---|
| 1 | `main.py` | FastAPI app, WebSocket endpoint, startup initializers | 195 |
| 2 | `config.py` | Environment variables, system paths, API keys, security policy | 141 |
| 3 | `database.py` | SQLite: chat history, memory, task logs | 192 |
| 4 | `core/base_agent.py` | Abstract base class for all sub-agents | 92 |
| 5 | `core/llm.py` | Google GenAI (Gemini) client + offline fallback | 125 |
| 6 | `core/orchestrator.py` | Multi-agent router and streaming execution loop | 192 |
| 7 | `agents/coder_agent.py` | Coder & Developer Agent | 316 |
| 8 | `agents/research_agent.py` | Research & Web Intelligence Agent | 84 |
| 9 | `agents/system_agent.py` | System & Automation Agent | 145 |
| 10 | `agents/memory_agent.py` | Memory & Context Agent | 134 |
| 11 | `tools/shell_tool.py` | Secure sandboxed shell execution | 157 |
| 12 | `tools/web_search_tool.py` | Free search aggregator (DuckDuckGo/Bing) | 133 |
| 13 | `tools/file_manager.py` | Workspace-confined file operations | 98 |
| 14 | `static/index.html` | Futuristic HUD structure | 211 |
| 15 | `static/style.css` | Cinematic sci-fi styling, responsive layout | 974 |
| 16 | `static/script.js` | WebSocket client, markdown renderer, voice input | 821 |
| 17 | `scripts/deploy_github.py` | Automated GitHub deployment | 658 |
| 18 | `requirements.txt` | Python dependencies | 8 |
| 19 | `README.md` | Full project documentation | 234 |
| 20 | `.env.example` | Environment variable template | 26 |
| 21 | `.gitignore` | Git ignore rules | 27 |
| 22 | `workspace/README.md` | Agent sandbox directory note | 9 |

---

## 1. `main.py`

**FastAPI app, WebSocket endpoint, startup initializers** — 195 lines

```python
"""
jarvis/main.py
--------------
JARVIS-OMEGA entry point: FastAPI server + WebSocket chat endpoint.

Run from the repo root:
    uvicorn jarvis.main:app --host 0.0.0.0 --port 8000

Run from inside jarvis/ (Termux-friendly):
    uvicorn main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from contextlib import asynccontextmanager
from queue import Empty, Queue
from typing import Optional

# Make absolute imports (config, core.*, agents.*, tools.*, database) resolve
# whether the app is launched as `jarvis.main:app` or `main:app`.
_JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _JARVIS_DIR not in sys.path:
    sys.path.insert(0, _JARVIS_DIR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import CORS_ORIGINS, HOST, PORT, is_configured
from core.orchestrator import Orchestrator
from database import JarvisDatabase

db = JarvisDatabase()
orchestrator = Orchestrator(db=db)

_SENTINEL = object()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 62)
    print("  JARVIS-OMEGA :: Multi-Agent Personal AI Assistant")
    print("=" * 62)
    print(f"  LLM backend : {'Gemini (google-genai)' if is_configured() else 'OFFLINE heuristic mode'}")
    print(f"  Database    : {db.db_path}")
    print(f"  Agents      : {', '.join(a.name for a in orchestrator.agents)}")
    print(f"  HUD         : http://localhost:{PORT}/")
    print(f"  WebSocket   : ws://localhost:{PORT}/ws/chat")
    print("=" * 62)
    yield


app = FastAPI(title="JARVIS-OMEGA", version="1.0.0", lifespan=lifespan)

# Wildcard origin + credentials is rejected by browsers, so only enable
# credentials when explicit origins are configured.
_allow_all = CORS_ORIGINS == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all else CORS_ORIGINS,
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(_JARVIS_DIR, "static")),
    name="static",
)


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return FileResponse(os.path.join(_JARVIS_DIR, "static", "index.html"))


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_configured": is_configured(),
        "agents": [a.name for a in orchestrator.agents],
    }


@app.get("/api/status")
async def status():
    return {
        "llm_configured": is_configured(),
        "agents": orchestrator.agent_roster(),
        "db_path": str(db.db_path),
        "host": HOST,
        "port": PORT,
    }


@app.get("/api/memory")
async def memory_dump(limit: int = 20):
    rows = db.search_memory("", limit=limit) if limit else []
    return {"count": len(rows), "memory": rows}


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(status_code=204, content=None)


# ---------------------------------------------------------------------------
# WebSocket chat
# ---------------------------------------------------------------------------
@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    session_id = "default"

    try:
        while True:
            raw = await websocket.receive_text()
            message = raw

            # Accept both plain text and {"session_id": ..., "message": ...}
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    session_id = data.get("session_id") or "default"
                    message = data.get("message", "")
            except (json.JSONDecodeError, TypeError):
                message = raw

            message = (message or "").strip()
            if not message:
                await websocket.send_text(json.dumps({
                    "type": "error", "agent": "System",
                    "message": "Empty message.", "payload": {}, "timestamp": "",
                }))
                continue

            await websocket.send_text(json.dumps({
                "type": "ack",
                "agent": "System",
                "message": "Signal acquired. Compiling response...",
                "payload": {"session_id": session_id},
                "timestamp": "",
            }))

            # Run the synchronous orchestrator generator on a worker thread
            # and pump its events through a queue so the event loop stays
            # responsive and the HUD receives true real-time updates.
            q: Queue = Queue()

            def _worker() -> None:
                try:
                    for event in orchestrator.process(session_id, message):
                        q.put(event)
                except Exception as exc:  # noqa: BLE001
                    q.put({
                        "type": "error", "agent": "System",
                        "message": f"Orchestrator crashed: {exc}",
                        "payload": {"error": str(exc)}, "timestamp": "",
                    })
                finally:
                    q.put(_SENTINEL)

            threading.Thread(target=_worker, daemon=True).start()

            while True:
                try:
                    item = await asyncio.to_thread(q.get, True, 0.2)
                except Empty:
                    continue
                if item is _SENTINEL:
                    break
                await websocket.send_text(json.dumps(item))

    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        return


# ---------------------------------------------------------------------------
# Dev entry point: `python main.py`
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
```

## 2. `config.py`

**Environment variables, system paths, API keys, security policy** — 141 lines

```python
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
```

## 3. `database.py`

**SQLite: chat history, memory, task logs** — 192 lines

```python
"""
jarvis/database.py
------------------
SQLite persistence layer for JARVIS-OMEGA.

Tables:
  * chat_history   - conversation messages (role, content, session_id, ts)
  * memory         - long-term semantic-ish memory (key, value, tags, ts)
  * task_logs      - agent/tool execution audit log (agent, tool, status, ts)

Designed for zero-budget deployment: pure stdlib sqlite3, WAL mode for
concurrent WebSocket reads/writes, works on PC and Termux.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from config import DB_PATH, LOGS_DIR


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JarvisDatabase:
    """Thin wrapper around sqlite3 with connection context management."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   TEXT NOT NULL,
                    role         TEXT NOT NULL,        -- 'user' | 'assistant' | 'system' | 'tool'
                    content      TEXT NOT NULL,
                    agent        TEXT,
                    created_at   TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chat_session
                    ON chat_history(session_id, created_at);

                CREATE TABLE IF NOT EXISTS memory (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    key          TEXT NOT NULL UNIQUE,
                    value        TEXT NOT NULL,
                    tags         TEXT,                 -- comma-separated tags
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(key);

                CREATE TABLE IF NOT EXISTS task_logs (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   TEXT NOT NULL,
                    agent        TEXT NOT NULL,
                    tool         TEXT,
                    status       TEXT NOT NULL,        -- 'ok' | 'error' | 'running'
                    input_payload TEXT,
                    output_payload TEXT,
                    created_at   TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_task_session
                    ON task_logs(session_id, created_at);
                """
            )

    # ------------------------------------------------------------------
    # Chat history
    # ------------------------------------------------------------------
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        agent: Optional[str] = None,
    ) -> int:
        with self.connection() as conn:
            cur = conn.execute(
                "INSERT INTO chat_history (session_id, role, content, agent, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, agent, _now_iso()),
            )
            return int(cur.lastrowid)

    def get_recent_messages(
        self, session_id: str, limit: int = 50
    ) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, session_id, role, content, agent, created_at "
                "FROM chat_history WHERE session_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------
    def upsert_memory(self, key: str, value: str, tags: str = "") -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO memory (key, value, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    tags  = excluded.tags,
                    updated_at = excluded.updated_at
                """,
                (key, value, tags, _now_iso(), _now_iso()),
            )

    def get_memory(self, key: str) -> Optional[str]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT value FROM memory WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def search_memory(self, query: str, limit: int = 10) -> list[dict]:
        """Simple LIKE-based semantic-ish search over memory keys/values/tags."""
        like = f"%{query}%"
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT key, value, tags, created_at, updated_at FROM memory "
                "WHERE key LIKE ? OR value LIKE ? OR tags LIKE ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (like, like, like, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Task logs
    # ------------------------------------------------------------------
    def log_task(
        self,
        session_id: str,
        agent: str,
        status: str,
        tool: Optional[str] = None,
        input_payload: Optional[str] = None,
        output_payload: Optional[str] = None,
    ) -> int:
        with self.connection() as conn:
            cur = conn.execute(
                "INSERT INTO task_logs "
                "(session_id, agent, tool, status, input_payload, output_payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, agent, tool, status, input_payload, output_payload, _now_iso()),
            )
            return int(cur.lastrowid)

    def get_recent_tasks(self, session_id: str, limit: int = 20) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, session_id, agent, tool, status, input_payload, output_payload, created_at "
                "FROM task_logs WHERE session_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]
```

## 4. `core/base_agent.py`

**Abstract base class for all sub-agents** — 92 lines

```python
"""
jarvis/core/base_agent.py
-------------------------
Abstract base class for every JARVIS-OMEGA sub-agent.

Agents are the workers of the multi-agent orchestration engine. Each agent
declares a name, a human-readable description, and the keywords/intents it
handles. The `process` method receives a structured context and returns a
result dict plus an optional list of events for real-time WebSocket streaming.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentEvent:
    """A single streaming event emitted during agent execution."""
    type: str                      # 'thought' | 'tool_call' | 'tool_result' | 'final' | 'error'
    agent: str
    message: str
    payload: Optional[dict] = None
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "agent": self.agent,
            "message": self.message,
            "payload": self.payload or {},
            "timestamp": self.timestamp,
        }


@dataclass
class AgentContext:
    """Input context passed to every agent."""
    user_input: str
    session_id: str
    history: list[dict] = field(default_factory=list)
    memory: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    """Output of an agent run."""
    agent: str
    success: bool
    content: str
    events: list[AgentEvent] = field(default_factory=list)
    data: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base class. Subclasses must implement `name`, `description`,
    `handles`, and `process`."""

    def __init__(self, name: str, description: str, handles: list[str]):
        self.name = name
        self.description = description
        self.handles = handles  # keywords/intents this agent responds to

    @abstractmethod
    def process(self, context: AgentContext, emit: Callable[[AgentEvent], None]) -> AgentResult:
        """Execute the agent's work, streaming progress via `emit`."""
        ...

    def can_handle(self, user_input: str) -> float:
        """Return a confidence score (0.0-1.0) for whether this agent handles the input.

        Base implementation counts keyword hits and maps them to a confidence:
        one hit is already a meaningful signal (0.40), each extra hit adds 0.20.
        Subclasses override this to add intent-specific boosts."""
        if not self.handles or not user_input:
            return 0.0
        lowered = user_input.lower()
        hits = sum(1 for kw in self.handles if kw.lower() in lowered)
        if hits == 0:
            return 0.0
        return min(1.0, 0.40 + 0.20 * (hits - 1))

    def _emit(self, emit: Callable[[AgentEvent], None], etype: str, message: str, payload: Optional[dict] = None) -> None:
        emit(AgentEvent(type=etype, agent=self.name, message=message, payload=payload))
```

## 5. `core/llm.py`

**Google GenAI (Gemini) client + offline fallback** — 125 lines

```python
"""
jarvis/core/llm.py
------------------
LLM abstraction for JARVIS-OMEGA.

Primary: Google GenAI SDK (Gemini) using a free API key.
Fallback: deterministic offline responder when no key is configured or the
network is unavailable — so the framework still works on a fresh Termux
install without any API keys.
"""

from __future__ import annotations

import os
from typing import Optional

from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TEMPERATURE, GEMINI_MAX_TOKENS


class LLM:
    """Small wrapper around Gemini with a safe offline fallback."""

    def __init__(self):
        self._client = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        if not GEMINI_API_KEY:
            return
        try:
            from google import genai  # type: ignore
            self._client = genai.Client(api_key=GEMINI_API_KEY)
            self._available = True
        except Exception:  # noqa: BLE001
            self._client = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available and self._client is not None

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Return generated text. Never raises; falls back offline on error."""
        if self.available:
            try:
                contents = []
                if system_prompt:
                    contents.append(f"System: {system_prompt}\n")
                contents.append(prompt)
                full = "\n".join(contents)
                resp = self._client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=full,
                    config={
                        "temperature": temperature if temperature is not None else GEMINI_TEMPERATURE,
                        "max_output_tokens": max_tokens if max_tokens is not None else GEMINI_MAX_TOKENS,
                    },
                )
                text = getattr(resp, "text", None) or ""
                if text.strip():
                    return text.strip()
            except Exception:  # noqa: BLE001
                pass  # fall through to offline
        return self._offline(prompt, system_prompt)

    def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Yield text chunks. Falls back to yielding the whole offline response."""
        if self.available:
            try:
                contents = []
                if system_prompt:
                    contents.append(f"System: {system_prompt}\n")
                contents.append(prompt)
                full = "\n".join(contents)
                stream = self._client.models.generate_content_stream(
                    model=GEMINI_MODEL,
                    contents=full,
                    config={
                        "temperature": temperature if temperature is not None else GEMINI_TEMPERATURE,
                        "max_output_tokens": max_tokens if max_tokens is not None else GEMINI_MAX_TOKENS,
                    },
                )
                for chunk in stream:
                    piece = getattr(chunk, "text", None)
                    if piece:
                        yield piece
                return
            except Exception:  # noqa: BLE001
                pass
        yield self._offline(prompt, system_prompt)

    # ------------------------------------------------------------------ #
    # Offline fallback
    # ------------------------------------------------------------------ #
    @staticmethod
    def _offline(prompt: str, system_prompt: Optional[str] = None) -> str:
        lowered = prompt.lower()
        if any(w in lowered for w in ("hello", "hi", "hey", "jarvis")):
            return "JARVIS-OMEGA online. Systems nominal. No LLM API key detected; running in offline heuristic mode. How can I assist?"
        if any(w in lowered for w in ("who are you", "what are you")):
            return "I am JARVIS-OMEGA, a local multi-agent personal assistant framework running on FastAPI + SQLite. Add a GEMINI_API_KEY to unlock full generative reasoning."
        if any(w in lowered for w in ("help", "commands")):
            return ("Available offline capabilities: system commands (sandboxed), file management, "
                    "web search (DuckDuckGo/Bing), memory store/recall, and code generation/execution. "
                    "Set GEMINI_API_KEY for advanced reasoning.")
        return ("I received your message but no generative LLM backend is available. "
                "Set GEMINI_API_KEY in your environment or .env to enable Gemini-powered reasoning. "
                "For now, try asking me to run a system command, search the web, manage files, or store memory.")


# Singleton instance
llm = LLM()
```

## 6. `core/orchestrator.py`

**Multi-agent router and streaming execution loop** — 192 lines

```python
"""
jarvis/core/orchestrator.py
---------------------------
Multi-agent orchestration engine for JARVIS-OMEGA.

Registers sub-agents, routes user intent to the highest-confidence agent,
executes the agent while streaming real-time events (thoughts, tool calls,
tool results, final answer), and persists conversation + task logs to SQLite.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator, Optional

from core.base_agent import AgentContext, AgentEvent, AgentResult
from core.llm import llm
from agents.coder_agent import CoderAgent
from agents.memory_agent import MemoryAgent
from agents.research_agent import ResearchAgent
from agents.system_agent import SystemAgent
from database import JarvisDatabase


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class Orchestrator:
    """Routes requests to specialist agents and streams their work."""

    def __init__(self, db: Optional[JarvisDatabase] = None):
        self.db = db or JarvisDatabase()
        self.agents = [
            CoderAgent(),
            ResearchAgent(),
            SystemAgent(),
            MemoryAgent(db=self.db),
        ]

    # ------------------------------------------------------------------ #
    # Routing
    # ------------------------------------------------------------------ #
    def route(self, user_input: str) -> tuple[Optional[object], float]:
        """Return (agent, confidence) for the best-matching agent."""
        best_agent = None
        best_conf = 0.0
        for agent in self.agents:
            conf = agent.can_handle(user_input)
            if conf > best_conf:
                best_conf = conf
                best_agent = agent
        if best_conf <= 0.1:
            return None, best_conf
        return best_agent, best_conf

    # ------------------------------------------------------------------ #
    # Main execution loop — a SYNC generator of event dicts.
    # The WebSocket layer pumps this from a worker thread.
    # ------------------------------------------------------------------ #
    def process(self, session_id: str, user_input: str) -> Iterator[dict]:
        self.db.add_message(session_id, "user", user_input)

        history = self.db.get_recent_messages(session_id, limit=20)
        memory_hits = self.db.search_memory(user_input, limit=5)

        context = AgentContext(
            user_input=user_input,
            session_id=session_id,
            history=history,
            memory=memory_hits,
        )

        agent, confidence = self.route(user_input)

        yield {
            "type": "route",
            "agent": agent.name if agent else "Router",
            "message": (
                f"Routed to {agent.name} agent (confidence {confidence:.0%})"
                if agent else
                "No specialist matched — engaging general responder."
            ),
            "payload": {"confidence": round(confidence, 2)},
            "timestamp": _ts(),
        }

        if agent is None:
            yield from self._general_response(session_id, context)
            return

        # Buffer agent events so we can stream them in order while still
        # getting the AgentResult at the end. Agents are synchronous.
        collected: list[dict] = []

        def _emit(event: AgentEvent) -> None:
            collected.append(event.to_dict())

        try:
            result: AgentResult = agent.process(context, _emit)
        except Exception as exc:  # noqa: BLE001
            err = {
                "type": "error",
                "agent": agent.name,
                "message": f"{agent.name} agent failed: {exc}",
                "payload": {"error": str(exc)},
                "timestamp": _ts(),
            }
            collected.append(err)
            result = AgentResult(agent.name, False, f"{agent.name} agent failed: {exc}")

        for ev in collected:
            yield ev

        yield {
            "type": "final",
            "agent": result.agent,
            "message": result.content,
            "payload": result.data or {},
            "success": result.success,
            "timestamp": _ts(),
        }

        try:
            self.db.add_message(session_id, "assistant", result.content, agent=result.agent)
            self.db.log_task(
                session_id=session_id,
                agent=result.agent,
                status="ok" if result.success else "error",
                input_payload=user_input[:2000],
                output_payload=result.content[:2000],
            )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # General responder (no agent matched)
    # ------------------------------------------------------------------ #
    def _general_response(self, session_id: str, context: AgentContext) -> Iterator[dict]:
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in context.history[-8:]
        ) or "(new session)"
        memory_text = "\n".join(
            f"{m['key']}: {m['value']}" for m in context.memory[:3]
        ) or "(none)"

        system_prompt = (
            "You are JARVIS-OMEGA, a helpful personal AI assistant. "
            "Answer concisely and helpfully. Use markdown with fenced code blocks "
            "when showing code."
        )
        prompt = (
            f"Recent conversation:\n{history_text}\n\n"
            f"Relevant long-term memory:\n{memory_text}\n\n"
            f"User: {context.user_input}\n\nAssistant:"
        )

        yield {
            "type": "thought",
            "agent": "Router",
            "message": "Consulting general reasoning model...",
            "payload": {},
            "timestamp": _ts(),
        }

        full = llm.generate(prompt, system_prompt=system_prompt)

        yield {
            "type": "final",
            "agent": "Router",
            "message": full,
            "payload": {},
            "success": True,
            "timestamp": _ts(),
        }

        try:
            self.db.add_message(session_id, "assistant", full, agent="Router")
            self.db.log_task(session_id=session_id, agent="Router", status="ok",
                             input_payload=context.user_input[:2000],
                             output_payload=full[:2000])
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # Introspection helpers (used by the HUD status panel)
    # ------------------------------------------------------------------ #
    def agent_roster(self) -> list[dict]:
        return [
            {"name": a.name, "description": a.description, "handles": a.handles}
            for a in self.agents
        ]
```

## 7. `agents/coder_agent.py`

**Coder & Developer Agent** — 316 lines

```python
"""
jarvis/agents/coder_agent.py
----------------------------
Coder & Developer Agent: generates, writes, and safely executes code snippets
(Python, Node.js, Shell, HTML/JS). All writes are scoped to the workspace;
all executions pass through the sandboxed ShellTool.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from core.base_agent import AgentContext, AgentEvent, AgentResult, BaseAgent
from core.llm import llm
from config import WORKSPACE_DIR
from tools.file_manager import FileManager, manage_file
from tools.shell_tool import ShellTool


class CoderAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Coder",
            description="Generates, writes, and safely executes code snippets.",
            handles=["code", "python", "javascript", "node", "shell", "script",
                     "write code", "execute", "run", "program", "html", "css"],
        )
        self.fm = FileManager()
        self.shell = ShellTool(work_dir=str(WORKSPACE_DIR))
        self._allowed_runners = {
            ".py": ["python", "python3"],
            ".js": ["node"],
            ".sh": ["bash", "sh"],
        }

    # ------------------------------------------------------------------ #
    def can_handle(self, user_input: str) -> float:
        score = super().can_handle(user_input)
        lowered = user_input.lower()

        # "run foo.py" / "execute foo.sh" belongs to Coder, not System.
        if re.match(r"^\s*(?:run|execute|launch)\s+[A-Za-z0-9_\-./]+\.(?:py|js|sh)\b", lowered):
            return 0.95

        if any(w in lowered for w in ("write a", "create a", "generate", "code", "script",
                                      "execute", "html", "css")):
            score = max(score, 0.65)
        return min(1.0, score)

    # ------------------------------------------------------------------ #
    def process(self, context: AgentContext, emit) -> AgentResult:
        user_input = context.user_input
        events_list: list[AgentEvent] = [
            AgentEvent("thought", self.name,
                       "Analyzing request to determine whether to write, execute, or explain code.",
                       {"input": user_input})
        ]
        emit(events_list[0])

        # Decide intent. Prefer LLM classification when a real backend is
        # configured; otherwise fall back to deterministic heuristics so the
        # agent still works fully offline.
        classification = self._classify(user_input)

        events_list.append(AgentEvent("thought", self.name,
                                      f"Classified intent: {classification}",
                                      {"classification": classification}))

        # Extract a filename if one is mentioned.
        filename = self._extract_filename(user_input)

        content = ""
        if classification == "WRITE_FILE":
            if not filename:
                filename = "generated_code.py"
            content = self._generate_code(user_input, filename)
            write_res = manage_file("write", filename, content)
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Writing file {filename}",
                                          {"file": filename, "bytes": len(content)}))
            if write_res.success:
                events_list.append(AgentEvent("tool_result", self.name,
                                              f"Wrote {filename} ({len(content)} bytes)",
                                              {"file": filename}))
            else:
                events_list.append(AgentEvent("error", self.name,
                                              f"Failed to write {filename}: {write_res.message}",
                                              {"error": write_res.message}))
                return AgentResult(self.name, False,
                                   f"Failed to write {filename}: {write_res.message}",
                                   events=events_list)

            final = (f"Wrote `{filename}` ({len(content)} bytes). "
                     f"Preview:\n\n```{self._lang(filename)}\n{content[:1500]}\n```")
            if len(content) > 1500:
                final += "\n... (truncated preview)"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, True, final, events=events_list,
                               data={"file": filename, "content": content})

        if classification == "EXECUTE":
            if not filename:
                return AgentResult(self.name, False,
                                   "No executable file specified. Ask me to write a script first, "
                                   "or name the file to run (e.g. 'run script.py').",
                                   events=events_list)
            if not (self.fm.root / filename).exists():
                return AgentResult(self.name, False,
                                   f"File `{filename}` not found in workspace. Write it first.",
                                   events=events_list)
            runner = self._pick_runner(filename)
            cmd = f"{runner} {filename}"
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Executing {cmd}",
                                          {"command": cmd}))
            res = self.shell.run(cmd)
            events_list.append(AgentEvent("tool_result", self.name,
                                          f"Execution finished (exit {res.returncode})",
                                          {"command": cmd, "returncode": res.returncode,
                                           "timed_out": res.timed_out}))
            output = res.stdout
            if res.stderr:
                output += "\n--- STDERR ---\n" + res.stderr
            if res.truncated:
                output += "\n... (output truncated)"
            final = f"Executed `{cmd}`:\n\n```\n{output or '(no output)'}\n```"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, res.success, final, events=events_list,
                               data={"command": cmd, "output": output, "returncode": res.returncode})

        if classification == "EXPLAIN":
            code_block = self._extract_code_block(user_input) or user_input
            explanation = self._explain_code(code_block)
            events_list.append(AgentEvent("final", self.name, explanation))
            return AgentResult(self.name, True, explanation, events=events_list)

        # UNKNOWN -> helpful default: generate a snippet and offer to write/run it.
        content = self._generate_code(user_input, "suggestion.py")
        events_list.append(AgentEvent("thought", self.name,
                                      "No clear intent; generated a suggested code snippet.",
                                      {"language": "python"}))
        final = (f"I'm not sure what you'd like me to do with that code. "
                 f"Here's a suggested snippet (`suggestion.py`):\n\n"
                 f"```python\n{content}\n```\n\n"
                 f"Say 'write suggestion.py' to save it, or 'run suggestion.py' to execute it.")
        events_list.append(AgentEvent("final", self.name, final))
        return AgentResult(self.name, True, final, events=events_list,
                           data={"content": content})

    # ------------------------------------------------------------------ #
    # Intent classification
    # ------------------------------------------------------------------ #
    def _classify(self, user_input: str) -> str:
        """Return one of WRITE_FILE | EXECUTE | EXPLAIN | UNKNOWN."""
        if llm.available:
            plan_prompt = (
                f"User request: {user_input}\n"
                "Classify into exactly one of: WRITE_FILE, EXECUTE, EXPLAIN, UNKNOWN.\n"
                "Reply with only the classification word."
            )
            raw = llm.generate(plan_prompt, temperature=0.0).strip().upper()
            for word in ("WRITE_FILE", "EXECUTE", "EXPLAIN", "UNKNOWN"):
                if word in raw:
                    return word
        return self._classify_heuristic(user_input)

    @staticmethod
    def _classify_heuristic(user_input: str) -> str:
        """Deterministic offline classifier."""
        lowered = user_input.lower().strip()
        has_code_fence = "```" in user_input
        mentions_file = re.search(r"[A-Za-z0-9_\-]+\.(?:py|js|sh|html|css)\b", user_input) is not None
        execute_verbs = ("run ", "execute ", "execute it", "launch ", "start ")
        write_verbs = ("write ", "create ", "generate ", "make ", "save ", "build ", "code ")

        if execute_verbs and lowered.startswith(execute_verbs):
            return "EXECUTE"
        if mentions_file and lowered.startswith("run "):
            return "EXECUTE"
        if has_code_fence or lowered.startswith(("explain", "what does this code", "review this")):
            return "EXPLAIN"
        if lowered.startswith(write_verbs) or any(v in lowered for v in write_verbs):
            return "WRITE_FILE"
        return "UNKNOWN"

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_filename(user_input: str) -> Optional[str]:
        m = re.search(r"(?:file|named|called|save|write)\s+[\"']?([A-Za-z0-9_\-./]+\.[A-Za-z0-9]+)[\"']?", user_input)
        if m:
            return m.group(1)
        m = re.search(r"([A-Za-z0-9_\-]+\.(?:py|js|sh|html|css))", user_input)
        return m.group(1) if m else None

    @staticmethod
    def _lang(filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        return {"py": "python", "js": "javascript", "sh": "bash",
                "html": "html", "css": "css"}.get(ext, "text")

    def _pick_runner(self, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        runners = self._allowed_runners.get(ext, ["python3"])
        for r in runners:
            if shutil_which(r):
                return r
        return runners[0]

    @staticmethod
    def _extract_code_block(user_input: str) -> Optional[str]:
        m = re.search(r"```(?:\w+)?\n(.*?)```", user_input, flags=re.DOTALL)
        return m.group(1).strip() if m else None

    def _generate_code(self, user_input: str, filename: str) -> str:
        lang = self._lang(filename)

        if llm.available:
            system = (
                "You are a senior software engineer. Generate clean, well-commented, "
                f"production-ready {lang} code that solves the user's request. "
                "Output ONLY the code, no markdown fences, no explanation."
            )
            return llm.generate(user_input, system_prompt=system, temperature=0.4)

        # Offline: emit a deterministic, runnable template rather than prose.
        return self._offline_template(user_input, filename)

    @staticmethod
    def _offline_template(user_input: str, filename: str) -> str:
        """Deterministic runnable scaffold used when no LLM backend is configured."""
        lowered = user_input.lower()
        ext = os.path.splitext(filename)[1].lower()

        if ext == ".py":
            if "fibonacci" in lowered or "fib" in lowered:
                return (
                    '"""Fibonacci sequence generator."""\n\n'
                    "def fibonacci(n: int) -> list[int]:\n"
                    '    """Return the first n Fibonacci numbers."""\n'
                    "    seq: list[int] = []\n"
                    "    a, b = 0, 1\n"
                    "    for _ in range(n):\n"
                    "        seq.append(a)\n"
                    "        a, b = b, a + b\n"
                    "    return seq\n\n\n"
                    'if __name__ == "__main__":\n'
                    "    print(fibonacci(10))\n"
                )
            if "hello" in lowered or "print" in lowered:
                return (
                    '"""Simple greeting script."""\n\n\n'
                    "def main() -> None:\n"
                    '    """Entry point."""\n'
                    '    print("Hello from JARVIS-OMEGA!")\n\n\n'
                    'if __name__ == "__main__":\n'
                    "    main()\n"
                )
            return (
                f'"""Generated scaffold for: {user_input[:80]}"""\n\n'
                "from __future__ import annotations\n\n\n"
                "def main() -> None:\n"
                '    """Entry point."""\n'
                f'    print("TODO: implement: {user_input[:60]}")\n\n\n'
                'if __name__ == "__main__":\n'
                "    main()\n"
            )

        if ext == ".js":
            return (
                "// Generated scaffold\n"
                "'use strict';\n\n"
                "function main() {\n"
                f"  // TODO: {user_input[:70]}\n"
                "  console.log('Hello from JARVIS-OMEGA!');\n"
                "}\n\n"
                "main();\n"
            )

        if ext == ".sh":
            return (
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n\n"
                f"# TODO: {user_input[:70]}\n"
                'echo "Hello from JARVIS-OMEGA!"\n'
            )

        if ext == ".html":
            return (
                "<!DOCTYPE html>\n"
                '<html lang="en">\n<head>\n'
                '  <meta charset="UTF-8" />\n'
                '  <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
                "  <title>JARVIS-OMEGA</title>\n"
                "</head>\n<body>\n"
                "  <h1>Hello from JARVIS-OMEGA</h1>\n"
                "</body>\n</html>\n"
            )

        if ext == ".css":
            return "/* Generated stylesheet */\nbody {\n  margin: 0;\n  font-family: system-ui, sans-serif;\n}\n"

        return f"# Generated file for: {user_input}\n"

    def _explain_code(self, code: str) -> str:
        system = ("You are a senior software engineer. Explain what the provided "
                  "code does, line by line where helpful, and note any risks.")
        return llm.generate(code, system_prompt=system, temperature=0.4)


def shutil_which(binary: str) -> bool:
    import shutil
    return shutil.which(binary) is not None
```

## 8. `agents/research_agent.py`

**Research & Web Intelligence Agent** — 84 lines

```python
"""
jarvis/agents/research_agent.py
-------------------------------
Research & Web Intelligence Agent: smart web searches, documentation
aggregation, article summarization, and live data via free scrapers/APIs.
"""

from __future__ import annotations

from core.base_agent import AgentContext, AgentEvent, AgentResult, BaseAgent
from core.llm import llm
from tools.web_search_tool import WebSearchTool, search_web


class ResearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Research",
            description="Executes web searches, aggregates documentation, and summarizes live data.",
            handles=["search", "web", "research", "lookup", "find", "what is",
                     "who is", "latest", "news", "documentation", "browse"],
        )
        self.search_tool = WebSearchTool()

    def can_handle(self, user_input: str) -> float:
        score = super().can_handle(user_input)
        lowered = user_input.lower()
        question_starts = ("what ", "who ", "where ", "when ", "why ", "how ",
                           "tell me about", "search for", "look up")
        if any(lowered.startswith(w) for w in question_starts):
            score = max(score, 0.55)
        return min(1.0, score)

    def process(self, context: AgentContext, emit) -> AgentResult:
        events_list: list[AgentEvent] = [
            AgentEvent("thought", self.name,
                       "Planning web research for the user query.",
                       {"query": context.user_input})
        ]

        query = context.user_input
        # Strip obvious assistant prefixes.
        for prefix in ("search for ", "look up ", "research ", "find "):
            if query.lower().startswith(prefix):
                query = query[len(prefix):].strip()
                break

        events_list.append(AgentEvent("tool_call", self.name,
                                      f"Searching the web: {query}",
                                      {"query": query}))
        results = self.search_tool.search(query, max_results=6)
        events_list.append(AgentEvent("tool_result", self.name,
                                      f"Found {len(results)} results",
                                      {"count": len(results)}))

        if not results:
            final = ("I couldn't find any web results for that query. "
                     "Try rephrasing, or check your internet connection.")
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, False, final, events=events_list)

        # Build an LLM-ready summary from search results.
        context_block = self.search_tool.format_for_llm(results)
        summary_prompt = (
            f"User asked: {context.user_input}\n\n"
            f"Search results:\n{context_block}\n\n"
            "Write a concise, well-structured answer using only the search results "
            "above. Cite sources by title and URL. If the results don't answer the "
            "question, say so clearly."
        )
        answer = llm.generate(summary_prompt, temperature=0.5)

        final_lines = [answer, "", "---", "Sources:"]
        for i, r in enumerate(results, 1):
            final_lines.append(f"{i}. {r.title} — {r.url}")
        final = "\n".join(final_lines)

        events_list.append(AgentEvent("final", self.name, final))
        return AgentResult(self.name, True, final, events=events_list,
                           data={"query": query, "results": [r.__dict__ for r in results]})


def search_web_convenience(query: str, max_results: int = 5) -> str:
    return search_web(query, max_results=max_results)
```

## 9. `agents/system_agent.py`

**System & Automation Agent** — 145 lines

```python
"""
jarvis/agents/system_agent.py
-----------------------------
System & Automation Agent: local system monitoring, file operations, process
management, and Termux/Linux command execution inside a sandboxed environment.
"""

from __future__ import annotations

import os
import platform
import shutil

from core.base_agent import AgentContext, AgentEvent, AgentResult, BaseAgent
from core.llm import llm
from config import WORKSPACE_DIR
from tools.file_manager import manage_file
from tools.shell_tool import ShellTool


class SystemAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="System",
            description="System monitoring, file operations, and sandboxed command execution.",
            handles=["system", "terminal", "command", "bash", "shell", "ls", "pwd",
                     "cpu", "memory", "disk", "process", "ps", "file", "folder",
                     "directory", "uptime", "whoami", "ip", "network"],
        )
        self.shell = ShellTool(work_dir=str(WORKSPACE_DIR))

    def can_handle(self, user_input: str) -> float:
        score = super().can_handle(user_input)
        lowered = user_input.lower()
        system_hints = ("ls ", "pwd", "ps ", "cpu", "ram", "disk", "uptime", "whoami",
                        "run ", "exec ", "terminal", "bash", "shell", "cat ", "df ", "free ")
        if any(h in lowered for h in system_hints):
            score = max(score, 0.7)
        return min(1.0, score)

    def process(self, context: AgentContext, emit) -> AgentResult:
        events_list: list[AgentEvent] = [
            AgentEvent("thought", self.name,
                       "Analyzing system request and checking sandbox policy.",
                       {"input": context.user_input})
        ]

        user_input = context.user_input
        lowered = user_input.lower()

        # Route to known safe diagnostics when no explicit command is given.
        if any(w in lowered for w in ("status", "system info", "sysinfo", "info")):
            return self._system_info(events_list)

        if any(w in lowered for w in ("list", "ls ", "dir", "files", "folder", "directory")):
            path = self._extract_path(user_input) or "."
            res = manage_file("list", path)
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Listing directory: {path}",
                                          {"path": path}))
            events_list.append(AgentEvent("tool_result", self.name,
                                          res.message,
                                          {"success": res.success}))
            final = f"Directory listing for `{path}`:\n\n```\n{res.content or res.message}\n```" if res.success else f"[Error] {res.message}"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, res.success, final, events=events_list)

        if any(w in lowered for w in ("read", "cat ", "open file")):
            path = self._extract_path(user_input) or "."
            res = manage_file("read", path)
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Reading file: {path}",
                                          {"path": path}))
            events_list.append(AgentEvent("tool_result", self.name,
                                          res.message,
                                          {"success": res.success}))
            final = f"Contents of `{path}`:\n\n```\n{res.content or res.message}\n```" if res.success else f"[Error] {res.message}"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, res.success, final, events=events_list)

        # Otherwise treat the whole input as a shell command to run sandboxed.
        events_list.append(AgentEvent("tool_call", self.name,
                                      f"Running sandboxed command: {user_input}",
                                      {"command": user_input}))
        res = self.shell.run(user_input)
        events_list.append(AgentEvent("tool_result", self.name,
                                      f"Exit {res.returncode}" + (" (timed out)" if res.timed_out else ""),
                                      {"command": user_input, "returncode": res.returncode,
                                       "timed_out": res.timed_out}))
        output = res.stdout
        if res.stderr:
            output += "\n--- STDERR ---\n" + res.stderr
        if res.timed_out:
            output += "\n--- Command timed out ---"
        if res.truncated:
            output += "\n--- Output truncated ---"
        final = f"Command: `{user_input}`\n\n```\n{output or '(no output)'}\n```"
        events_list.append(AgentEvent("final", self.name, final))
        return AgentResult(self.name, res.success, final, events=events_list,
                           data={"command": user_input, "output": output,
                                 "returncode": res.returncode, "timed_out": res.timed_out})

    # ------------------------------------------------------------------ #
    def _system_info(self, events_list: list[AgentEvent]) -> AgentResult:
        info_parts = []
        info_parts.append(f"Host: {platform.node()}")
        info_parts.append(f"OS: {platform.system()} {platform.release()} ({platform.version()})")
        info_parts.append(f"Architecture: {platform.machine()}")
        info_parts.append(f"Python: {platform.python_version()}")
        info_parts.append(f"CWD: {os.getcwd()}")

        # Quick shell diagnostics (all sandbox-safe, read-only).
        diag_commands = [
            ("uptime", "uptime"),
            ("whoami", "whoami"),
            ("memory", "free -h 2>/dev/null || vmstat | head -5"),
            ("disk", "df -h ."),
            ("ip", "hostname -I 2>/dev/null || ip addr show 2>/dev/null | head -20"),
        ]
        results = []
        for label, cmd in diag_commands:
            res = self.shell.run(cmd)
            results.append(f"[{label}]\n{res.stdout or res.stderr or '(no output)'}")
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Diagnostic: {label}",
                                          {"command": cmd}))
            events_list.append(AgentEvent("tool_result", self.name,
                                          f"{label} -> exit {res.returncode}",
                                          {"label": label, "returncode": res.returncode}))

        final = ("JARVIS-OMEGA System Snapshot\n"
                 "==========================\n"
                 + "\n".join(info_parts) + "\n\n"
                 + "\n\n".join(results))
        events_list.append(AgentEvent("final", self.name, final))
        return AgentResult(self.name, True, final, events=events_list)

    @staticmethod
    def _extract_path(user_input: str) -> str | None:
        import re
        m = re.search(r"(?:in|at|of|for)\s+[\"']?([A-Za-z0-9_\-./]+)[\"']?", user_input)
        if m:
            return m.group(1)
        m = re.search(r"([A-Za-z0-9_\-./]+)", user_input)
        return m.group(1) if m else None
```

## 10. `agents/memory_agent.py`

**Memory & Context Agent** — 134 lines

```python
"""
jarvis/agents/memory_agent.py
-----------------------------
Memory & Context Agent: short-term working memory and long-term persistent
memory using SQLite with simple semantic (keyword) retrieval.
"""

from __future__ import annotations

import re

from core.base_agent import AgentContext, AgentEvent, AgentResult, BaseAgent
from core.llm import llm
from database import JarvisDatabase


class MemoryAgent(BaseAgent):
    def __init__(self, db: JarvisDatabase | None = None):
        super().__init__(
            name="Memory",
            description="Stores and recalls persistent memory using SQLite.",
            handles=["remember", "recall", "memory", "store", "note", "forget",
                     "remind me", "saved"],
        )
        self.db = db or JarvisDatabase()

    def can_handle(self, user_input: str) -> float:
        score = super().can_handle(user_input)
        lowered = user_input.lower()

        # "what is <key>" should hit Memory (not Research) if we already know it.
        probe = re.sub(
            r"^\s*(?:what is|what's|recall|show memory|search memory|do you remember)\s+",
            "", user_input, flags=re.IGNORECASE,
        ).strip().rstrip("?")

        if probe:
            try:
                if self.db.get_memory(probe):
                    return 0.95
                # Partial match still signals memory intent.
                if self.db.search_memory(probe, limit=1):
                    return 0.80
            except Exception:  # noqa: BLE001
                pass

        if any(w in lowered for w in ("remember", "recall", "memory", "store", "note",
                                      "forget", "saved", "remind me")):
            score = max(score, 0.75)
        return min(1.0, score)

    def process(self, context: AgentContext, emit) -> AgentResult:
        events_list: list[AgentEvent] = [
            AgentEvent("thought", self.name,
                       "Determining memory operation (store, recall, search, or forget).",
                       {"input": context.user_input})
        ]

        user_input = context.user_input
        lowered = user_input.lower()

        # STORE: "remember that X" / "store X as Y"
        store_match = re.match(r"\s*(?:remember|store|note)\s+(.+?)\s+(?:as|under)\s+(.+)\s*$",
                               user_input, flags=re.DOTALL | re.IGNORECASE)
        if store_match:
            value = store_match.group(1).strip()
            key = store_match.group(2).strip()
            self.db.upsert_memory(key, value, tags="user-stored")
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Storing memory: {key} = {value}",
                                          {"key": key, "value": value}))
            events_list.append(AgentEvent("tool_result", self.name,
                                          "Memory stored.",
                                          {"key": key}))
            final = f"Remembered: `{key}` = {value}"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, True, final, events=events_list)

        # SIMPLE STORE: "remember X"
        simple_store = re.match(r"\s*remember\s+(.+)\s*$",
                                user_input, flags=re.DOTALL | re.IGNORECASE)
        if simple_store and not any(w in lowered for w in ("recall", "what", "show")):
            value = simple_store.group(1).strip()
            key = value[:40]
            self.db.upsert_memory(key, value, tags="user-stored")
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Storing memory: {key}",
                                          {"key": key, "value": value}))
            final = f"Remembered: `{key}` = {value}"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, True, final, events=events_list)

        # FORGET: "forget X"
        forget_match = re.match(r"\s*forget\s+(.+)\s*$",
                                user_input, flags=re.DOTALL | re.IGNORECASE)
        if forget_match:
            key = forget_match.group(1).strip()
            # We don't have delete exposed; mark as forgotten by overwriting.
            self.db.upsert_memory(key, "[FORGOTTEN]", tags="forgotten")
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Forgetting memory: {key}",
                                          {"key": key}))
            final = f"Forgotten: `{key}`"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, True, final, events=events_list)

        # RECALL/SEARCH: "recall X" / "what is X" / "search memory X"
        recall_match = re.match(r"\s*(?:recall|what is|show memory|search memory)\s+(.+)\s*$",
                                user_input, flags=re.DOTALL | re.IGNORECASE)
        query = recall_match.group(1).strip() if recall_match else user_input

        exact = self.db.get_memory(query)
        if exact:
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Recalling exact memory: {query}",
                                          {"key": query}))
            final = f"From memory — `{query}`: {exact}"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, True, final, events=events_list)

        hits = self.db.search_memory(query, limit=5)
        events_list.append(AgentEvent("tool_call", self.name,
                                      f"Searching memory for: {query}",
                                      {"query": query, "hits": len(hits)}))
        if hits:
            lines = [f"Memory matches for '{query}':"]
            for h in hits:
                lines.append(f"• {h['key']}: {h['value'][:200]}{'...' if len(h['value']) > 200 else ''}")
            final = "\n".join(lines)
        else:
            final = f"No memory found for '{query}'. Try 'remember <something> as <key>' to store it."
        events_list.append(AgentEvent("final", self.name, final))
        return AgentResult(self.name, True, final, events=events_list,
                           data={"query": query, "hits": hits})
```

## 11. `tools/shell_tool.py`

**Secure sandboxed shell execution** — 157 lines

```python
"""
jarvis/tools/shell_tool.py
--------------------------
Secure, sandboxed shell execution for the System Agent.

Runs on PC and Android Termux. Enforces a blocklist of dangerous commands
and binaries, applies a hard timeout, caps output size, and returns
structured results. Never runs with elevated privileges inside the agent.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import (
    BLOCKED_BINARIES,
    BLOCKED_COMMAND_PATTERNS,
    SHELL_MAX_OUTPUT_BYTES,
    SHELL_TIMEOUT_SECONDS,
)


@dataclass
class ShellResult:
    success: bool
    command: str
    stdout: str
    stderr: str
    returncode: Optional[int]
    timed_out: bool
    truncated: bool


class ShellTool:
    """Sandboxed command runner."""

    def __init__(self, work_dir: str | None = None):
        self.work_dir = work_dir

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def run(self, command: str) -> ShellResult:
        """Execute `command` if it passes the security policy."""
        if not command or not command.strip():
            return ShellResult(
                success=False, command=command, stdout="", stderr="",
                returncode=None, timed_out=False, truncated=False,
            )

        # 1. Pattern blocklist (substring match on the raw command line)
        for pattern in BLOCKED_COMMAND_PATTERNS:
            if pattern in command:
                return ShellResult(
                    success=False, command=command, stdout="",
                    stderr=f"[Blocked] command matches forbidden pattern: {pattern!r}",
                    returncode=None, timed_out=False, truncated=False,
                )

        # 2. Binary blocklist (first token)
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            return ShellResult(
                success=False, command=command, stdout="",
                stderr=f"[Blocked] failed to parse command: {exc}",
                returncode=None, timed_out=False, truncated=False,
            )
        if not tokens:
            return ShellResult(
                success=False, command=command, stdout="", stderr="",
                returncode=None, timed_out=False, truncated=False,
            )
        binary = os.path.basename(tokens[0])
        if binary in BLOCKED_BINARIES:
            return ShellResult(
                success=False, command=command, stdout="",
                stderr=f"[Blocked] binary not allowed: {binary}",
                returncode=None, timed_out=False, truncated=False,
            )

        # 3. Resolve the binary; refuse if it doesn't exist
        resolved = shutil.which(tokens[0])
        if resolved is None:
            return ShellResult(
                success=False, command=command, stdout="",
                stderr=f"[Blocked] binary not found in PATH: {tokens[0]}",
                returncode=None, timed_out=False, truncated=False,
            )

        # 4. Execute
        try:
            proc = subprocess.run(
                tokens,
                capture_output=True,
                text=True,
                timeout=SHELL_TIMEOUT_SECONDS,
                cwd=self.work_dir,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            truncated = False
            total = len(stdout) + len(stderr)
            if total > SHELL_MAX_OUTPUT_BYTES:
                budget = SHELL_MAX_OUTPUT_BYTES // 2
                stdout = stdout[:budget]
                stderr = stderr[:budget]
                truncated = True

            return ShellResult(
                success=(proc.returncode == 0),
                command=command,
                stdout=stdout,
                stderr=stderr,
                returncode=proc.returncode,
                timed_out=False,
                truncated=truncated,
            )
        except subprocess.TimeoutExpired:
            return ShellResult(
                success=False, command=command, stdout="", stderr="",
                returncode=None, timed_out=True, truncated=False,
            )
        except Exception as exc:  # noqa: BLE001
            return ShellResult(
                success=False, command=command, stdout="", stderr=str(exc),
                returncode=None, timed_out=False, truncated=False,
            )

    def read_file(self, path: str) -> str:
        """Convenience: read a text file safely."""
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return f"[Error reading {path}: {exc}]"

    def list_dir(self, path: str = ".") -> str:
        """Convenience: list a directory."""
        try:
            lines = []
            for p in sorted(Path(path).iterdir()):
                marker = "/" if p.is_dir() else ""
                lines.append(f"{p.name}{marker}")
            return "\n".join(lines) if lines else "(empty)"
        except Exception as exc:  # noqa: BLE001
            return f"[Error listing {path}: {exc}]"


# backward-compatible function wrapper for quick scripting
def run_command(command: str, work_dir: str | None = None) -> ShellResult:
    return ShellTool(work_dir=work_dir).run(command)
```

## 12. `tools/web_search_tool.py`

**Free search aggregator (DuckDuckGo/Bing)** — 133 lines

```python
"""
jarvis/tools/web_search_tool.py
-------------------------------
Free web-search aggregation for the Research Agent.

Primary source: DuckDuckGo HTML endpoint (no API key required).
Fallback: a lightweight Bing HTML scrape. All results are title/link/snippet
tuples so the LLM can synthesize answers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchTool:
    """Search the web using free, key-less endpoints."""

    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Run a web search and return ranked results."""
        results = self._duckduckgo_html(query, max_results)
        if not results:
            results = self._bing_html(query, max_results)
        return results[:max_results]

    # ------------------------------------------------------------------ #
    # DuckDuckGo HTML (no key, no JS)
    # ------------------------------------------------------------------ #
    def _duckduckgo_html(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": self.UA},
                timeout=15,
            )
            resp.raise_for_status()
            return self._parse_ddg(resp.text, max_results)
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _parse_ddg(html: str, max_results: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        # DDG result blocks are wrapped in .result with .result__a / .result__snippet
        # We avoid a hard HTML dependency by using lightweight regexes.
        blocks = re.findall(
            r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>',
            html,
            flags=re.DOTALL,
        )
        snippets = re.findall(
            r'<a class="result__snippet".*?>(.*?)</a>',
            html,
            flags=re.DOTALL,
        )
        for idx, (url, title) in enumerate(blocks):
            if idx >= max_results:
                break
            clean_title = re.sub(r"<.*?>", "", title).strip()
            clean_url = re.sub(r"&amp;", "&", url)
            snippet = ""
            if idx < len(snippets):
                snippet = re.sub(r"<.*?>", "", snippets[idx]).strip()
            if clean_title and clean_url:
                results.append(SearchResult(title=clean_title, url=clean_url, snippet=snippet))
        return results

    # ------------------------------------------------------------------ #
    # Bing HTML fallback
    # ------------------------------------------------------------------ #
    def _bing_html(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            resp = requests.get(
                "https://www.bing.com/search",
                params={"q": query},
                headers={"User-Agent": self.UA},
                timeout=15,
            )
            resp.raise_for_status()
            return self._parse_bing(resp.text, max_results)
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _parse_bing(html: str, max_results: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        for m in re.finditer(
            r'<li class="b_algo".*?<h2.*?<a href="([^"]+)">(.*?)</a>.*?</h2>.*?'
            r'(?:<p>(.*?)</p>)?',
            html,
            flags=re.DOTALL,
        ):
            if len(results) >= max_results:
                break
            url, title, snippet = m.group(1), m.group(2), m.group(3) or ""
            clean_title = re.sub(r"<.*?>", "", title).strip()
            clean_snippet = re.sub(r"<.*?>", "", snippet).strip()
            if clean_title and url:
                results.append(SearchResult(title=clean_title, url=url, snippet=clean_snippet))
        return results

    def format_for_llm(self, results: list[SearchResult]) -> str:
        if not results:
            return "No web results found."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.title}\n   {r.url}\n   {r.snippet}")
        return "\n".join(lines)


def search_web(query: str, max_results: int = 5) -> str:
    """Convenience function returning an LLM-ready string."""
    tool = WebSearchTool()
    results = tool.search(query, max_results=max_results)
    return tool.format_for_llm(results)
```

## 13. `tools/file_manager.py`

**Workspace-confined file operations** — 98 lines

```python
"""
jarvis/tools/file_manager.py
----------------------------
Workspace file operations for agents.

All operations are scoped to the configured workspace (config.WORKSPACE_DIR)
so agents cannot escape it. Supports read, write, list, and directory creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import WORKSPACE_DIR


@dataclass
class FileResult:
    success: bool
    path: str
    message: str
    content: Optional[str] = None


class FileManager:
    """Workspace-scoped file manager."""

    def __init__(self, root: Path | str = WORKSPACE_DIR):
        self.root = Path(root).resolve()

    def _resolve(self, path: str) -> Path:
        target = (self.root / path).resolve()
        # Ensure the resolved path stays inside the workspace root.
        if self.root not in target.parents and target != self.root:
            raise ValueError(f"Path escapes workspace: {path}")
        return target

    def read(self, path: str) -> FileResult:
        try:
            target = self._resolve(path)
            if not target.exists():
                return FileResult(False, str(target), "File not found.")
            if not target.is_file():
                return FileResult(False, str(target), "Not a file.")
            content = target.read_text(encoding="utf-8", errors="replace")
            return FileResult(True, str(target), "Read ok.", content=content)
        except Exception as exc:  # noqa: BLE001
            return FileResult(False, path, f"Read error: {exc}")

    def write(self, path: str, content: str) -> FileResult:
        try:
            target = self._resolve(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return FileResult(True, str(target), "Written ok.")
        except Exception as exc:  # noqa: BLE001
            return FileResult(False, path, f"Write error: {exc}")

    def list_dir(self, path: str = ".") -> FileResult:
        try:
            target = self._resolve(path)
            if not target.exists():
                return FileResult(False, str(target), "Directory not found.")
            if not target.is_dir():
                return FileResult(False, str(target), "Not a directory.")
            entries = []
            for p in sorted(target.iterdir()):
                marker = "/" if p.is_dir() else ""
                size = p.stat().st_size if p.is_file() else 0
                entries.append(f"{'d' if p.is_dir() else '-'} {size:>8}  {p.name}{marker}")
            return FileResult(True, str(target), "\n".join(entries) or "(empty)")
        except Exception as exc:  # noqa: BLE001
            return FileResult(False, path, f"List error: {exc}")

    def make_dir(self, path: str) -> FileResult:
        try:
            target = self._resolve(path)
            target.mkdir(parents=True, exist_ok=True)
            return FileResult(True, str(target), "Directory ensured.")
        except Exception as exc:  # noqa: BLE001
            return FileResult(False, path, f"Mkdir error: {exc}")


def manage_file(action: str, path: str, content: Optional[str] = None) -> FileResult:
    fm = FileManager()
    if action == "read":
        return fm.read(path)
    if action == "write":
        if content is None:
            return FileResult(False, path, "write requires content")
        return fm.write(path, content or "")
    if action == "list":
        return fm.list_dir(path)
    if action == "mkdir":
        return fm.make_dir(path)
    return FileResult(False, path, f"Unknown action: {action}")
```

## 14. `static/index.html`

**Futuristic HUD structure** — 211 lines

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="theme-color" content="#04070d" />
  <title>JARVIS-OMEGA // Personal AI Core</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <!-- ================= Ambient background layers ================= -->
  <div class="bg-grid" aria-hidden="true"></div>
  <div class="bg-glow bg-glow--cyan" aria-hidden="true"></div>
  <div class="bg-glow bg-glow--blue" aria-hidden="true"></div>
  <div class="scanlines" aria-hidden="true"></div>

  <div class="app" id="app">
    <!-- ======================= Top bar ======================= -->
    <header class="topbar glass">
      <div class="topbar__brand">
        <div class="reactor" aria-hidden="true">
          <span class="reactor__ring reactor__ring--1"></span>
          <span class="reactor__ring reactor__ring--2"></span>
          <span class="reactor__core"></span>
        </div>
        <div class="brand-text">
          <h1>JARVIS<span class="brand-accent">·OMEGA</span></h1>
          <p class="brand-sub">Multi-Agent Personal AI Core</p>
        </div>
      </div>

      <div class="topbar__center">
        <div class="clock" id="clock">--:--:--</div>
        <div class="clock-date" id="clockDate">—</div>
      </div>

      <div class="topbar__status">
        <div class="pill" id="llmPill" title="LLM backend status">
          <span class="dot dot--idle" id="llmDot"></span>
          <span id="llmLabel">LINKING…</span>
        </div>
        <div class="pill" id="wsPill" title="WebSocket link">
          <span class="dot dot--idle" id="wsDot"></span>
          <span id="wsLabel">OFFLINE</span>
        </div>
      </div>
    </header>

    <!-- ======================= Main grid ======================= -->
    <main class="grid">

      <!-- ------------------- LEFT: system telemetry ------------------- -->
      <aside class="panel panel--left glass">
        <section class="block">
          <h2 class="block__title"><span class="tick"></span>System Status</h2>
          <div class="stat-list">
            <div class="stat">
              <span class="stat__label">Core</span>
              <span class="stat__value" id="statCore">ONLINE</span>
            </div>
            <div class="stat">
              <span class="stat__label">Uptime</span>
              <span class="stat__value mono" id="statUptime">00:00:00</span>
            </div>
            <div class="stat">
              <span class="stat__label">Messages</span>
              <span class="stat__value mono" id="statMsgs">0</span>
            </div>
            <div class="stat">
              <span class="stat__label">Latency</span>
              <span class="stat__value mono" id="statLatency">— ms</span>
            </div>
          </div>
          <div class="meter-row">
            <span class="meter-label">Cognitive Load</span>
            <div class="meter"><i id="loadBar" style="width:8%"></i></div>
          </div>
        </section>

        <section class="block">
          <h2 class="block__title"><span class="tick"></span>Active Agents</h2>
          <ul class="agents" id="agentList">
            <li class="agent" data-agent="Router">
              <span class="agent__status"></span>
              <span class="agent__name">Router</span>
              <span class="agent__role">intent</span>
            </li>
            <li class="agent" data-agent="Coder">
              <span class="agent__status"></span>
              <span class="agent__name">Coder</span>
              <span class="agent__role">code</span>
            </li>
            <li class="agent" data-agent="Research">
              <span class="agent__status"></span>
              <span class="agent__name">Research</span>
              <span class="agent__role">web</span>
            </li>
            <li class="agent" data-agent="System">
              <span class="agent__status"></span>
              <span class="agent__name">System</span>
              <span class="agent__role">local</span>
            </li>
            <li class="agent" data-agent="Memory">
              <span class="agent__status"></span>
              <span class="agent__name">Memory</span>
              <span class="agent__role">recall</span>
            </li>
          </ul>
        </section>

        <section class="block">
          <h2 class="block__title"><span class="tick"></span>Memory Core</h2>
          <div class="stat-list">
            <div class="stat">
              <span class="stat__label">Records</span>
              <span class="stat__value mono" id="memCount">0</span>
            </div>
            <div class="stat">
              <span class="stat__label">Session</span>
              <span class="stat__value mono" id="memSession">—</span>
            </div>
          </div>
          <div class="meter-row">
            <span class="meter-label">Index Density</span>
            <div class="meter"><i id="memBar" style="width:4%"></i></div>
          </div>
        </section>

        <section class="block block--actions">
          <h2 class="block__title"><span class="tick"></span>Core Actions</h2>
          <button class="btn btn--ghost" id="btnClear">PURGE FEED</button>
          <button class="btn btn--ghost" id="btnExport">EXPORT LOG</button>
        </section>
      </aside>

      <!-- ------------------- CENTER: chat feed ------------------- -->
      <section class="panel panel--center glass">
        <div class="feed-head">
          <h2 class="block__title"><span class="tick"></span>Neural Link</h2>
          <div class="feed-head__meta mono" id="feedMeta">session: —</div>
        </div>

        <div class="feed" id="feed">
          <article class="msg msg--system">
            <div class="msg__avatar">Ω</div>
            <div class="msg__body">
              <div class="msg__meta">
                <span class="msg__author">JARVIS-OMEGA</span>
                <span class="msg__time">boot</span>
              </div>
              <div class="msg__content">
                <p>Core initialised. All subsystems nominal.</p>
                <p class="dim">Awaiting your command. Try a quick action below, or just type.</p>
              </div>
            </div>
          </article>
        </div>

        <!-- ---------------- composer ---------------- -->
        <div class="composer">
          <div class="chips">
            <button class="chip" data-cmd="system status">System status</button>
            <button class="chip" data-cmd="list files in .">List files</button>
            <button class="chip" data-cmd="search for latest FastAPI best practices">Web research</button>
            <button class="chip" data-cmd="write a python script that prints fibonacci numbers to fib.py">Write code</button>
            <button class="chip" data-cmd="remember my project is JARVIS-OMEGA as project">Save memory</button>
          </div>

          <form class="input-row" id="chatForm" autocomplete="off">
            <button type="button" class="btn btn--icon" id="btnVoice" title="Toggle voice input (Web Speech API)">
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                <path d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-5a3.5 3.5 0 0 0-7 0v5A3.5 3.5 0 0 0 12 15Z"
                      fill="none" stroke="currentColor" stroke-width="1.6"/>
                <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3.5"
                      fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
              </svg>
            </button>

            <input class="input" id="chatInput" name="message" type="text"
                   placeholder="Speak or type a command…" autocomplete="off" />

            <button class="btn btn--send" id="btnSend" type="submit" title="Transmit">
              <span>TRANSMIT</span>
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path d="M3 11.5 21 3l-8.5 18-2-7.5L3 11.5Z" fill="none"
                      stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
              </svg>
            </button>
          </form>
        </div>
      </section>

      <!-- ------------------- RIGHT: terminal ------------------- -->
      <aside class="panel panel--right glass">
        <div class="feed-head">
          <h2 class="block__title"><span class="tick"></span>Execution Trace</h2>
          <button class="mini-btn" id="btnClearLog" title="Clear trace">CLR</button>
        </div>
        <div class="terminal" id="terminal" aria-live="polite"></div>
        <div class="term-foot mono">
          <span id="termStatus">idle</span>
          <span class="term-foot__sep">/</span>
          <span id="termCount">0 events</span>
        </div>
      </aside>
    </main>
  </div>

  <script src="/static/script.js" defer></script>
</body>
</html>
```

## 15. `static/style.css`

**Cinematic sci-fi styling, responsive layout** — 974 lines

```css
/* ==========================================================================
   JARVIS-OMEGA — HUD Stylesheet
   Dark sci-fi, neon cyan/blue, glassmorphism, responsive.
   ========================================================================== */

:root {
  --bg-0: #04070d;
  --bg-1: #070c16;
  --bg-2: #0b1420;

  --cyan: #38f0ff;
  --cyan-dim: #1b9fb0;
  --blue: #2a6bff;
  --blue-dim: #1d3f8f;
  --magenta: #c04bff;
  --amber: #ffb648;
  --red: #ff5470;
  --green: #3ef2a1;

  --text: #d9ecf5;
  --text-dim: #7f97a8;
  --text-faint: #4c6273;

  --line: rgba(56, 240, 255, 0.16);
  --line-strong: rgba(56, 240, 255, 0.4);

  --glass: rgba(10, 20, 32, 0.55);
  --glass-2: rgba(8, 16, 26, 0.72);

  --glow-cyan: 0 0 12px rgba(56, 240, 255, 0.55), 0 0 42px rgba(56, 240, 255, 0.16);
  --glow-soft: 0 0 24px rgba(56, 240, 255, 0.1);

  --radius: 14px;
  --radius-sm: 9px;

  --mono: "JetBrains Mono", "SFMono-Regular", ui-monospace, "Cascadia Mono",
          Menlo, Consolas, monospace;
  --sans: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
}

* { box-sizing: border-box; }

html, body {
  height: 100%;
  margin: 0;
  padding: 0;
}

body {
  background:
    radial-gradient(1200px 800px at 12% -10%, #0a2036 0%, transparent 60%),
    radial-gradient(1000px 700px at 92% 108%, #0a1b3a 0%, transparent 62%),
    var(--bg-0);
  color: var(--text);
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.55;
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
}

.mono { font-family: var(--mono); }
.dim { color: var(--text-dim); }

/* ============================ Background FX ============================== */

.bg-grid {
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(56, 240, 255, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 240, 255, 0.045) 1px, transparent 1px);
  background-size: 56px 56px;
  mask-image: radial-gradient(circle at 50% 40%, #000 30%, transparent 78%);
  -webkit-mask-image: radial-gradient(circle at 50% 40%, #000 30%, transparent 78%);
  animation: gridDrift 26s linear infinite;
  z-index: 0;
}

@keyframes gridDrift {
  from { background-position: 0 0, 0 0; }
  to   { background-position: 56px 56px, 56px 56px; }
}

.bg-glow {
  position: fixed;
  border-radius: 50%;
  filter: blur(120px);
  pointer-events: none;
  z-index: 0;
  opacity: 0.5;
  animation: floaty 18s ease-in-out infinite alternate;
}

.bg-glow--cyan {
  width: 42vw; height: 42vw;
  background: radial-gradient(circle, rgba(56, 240, 255, 0.28), transparent 68%);
  top: -14vw; left: -10vw;
}

.bg-glow--blue {
  width: 48vw; height: 48vw;
  background: radial-gradient(circle, rgba(42, 107, 255, 0.24), transparent 68%);
  bottom: -20vw; right: -12vw;
  animation-delay: -7s;
}

@keyframes floaty {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to   { transform: translate3d(3vw, 2vw, 0) scale(1.14); }
}

.scanlines {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 2;
  background: repeating-linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0.022) 0px,
    rgba(255, 255, 255, 0.022) 1px,
    transparent 1px,
    transparent 3px
  );
  opacity: 0.55;
}

/* ============================== Layout ================================== */

.app {
  position: relative;
  z-index: 3;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
}

.glass {
  background: linear-gradient(160deg, var(--glass), var(--glass-2));
  border: 1px solid var(--line);
  border-radius: var(--radius);
  backdrop-filter: blur(16px) saturate(140%);
  -webkit-backdrop-filter: blur(16px) saturate(140%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 20px 52px rgba(0, 0, 0, 0.55),
    var(--glow-soft);
}

/* =============================== Top bar ================================ */

.topbar {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 16px;
  padding: 12px 18px;
  position: relative;
  overflow: hidden;
}

.topbar::after {
  content: "";
  position: absolute;
  left: 0; right: 0; bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--cyan), transparent);
  opacity: 0.65;
  animation: sweep 5s linear infinite;
}

@keyframes sweep {
  0%   { transform: translateX(-60%); }
  100% { transform: translateX(60%); }
}

.topbar__brand { display: flex; align-items: center; gap: 14px; min-width: 0; }

/* Arc-reactor-esque logo */
.reactor { position: relative; width: 40px; height: 40px; flex: 0 0 auto; }

.reactor__ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1.5px solid var(--line-strong);
}

.reactor__ring--1 { animation: spin 7s linear infinite; border-top-color: var(--cyan); }
.reactor__ring--2 { inset: 6px; animation: spin 4s linear infinite reverse; border-bottom-color: var(--blue); }

.reactor__core {
  position: absolute;
  inset: 14px;
  border-radius: 50%;
  background: radial-gradient(circle, #fff 0%, var(--cyan) 40%, transparent 72%);
  box-shadow: 0 0 16px var(--cyan), 0 0 34px rgba(56, 240, 255, 0.5);
  animation: pulse 2.4s ease-in-out infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse {
  0%, 100% { opacity: 0.85; transform: scale(1); }
  50%      { opacity: 1;    transform: scale(1.12); }
}

.brand-text { min-width: 0; }

.brand-text h1 {
  margin: 0;
  font-size: 18px;
  letter-spacing: 0.16em;
  font-weight: 700;
  white-space: nowrap;
  text-shadow: 0 0 18px rgba(56, 240, 255, 0.45);
}

.brand-accent { color: var(--cyan); }

.brand-sub {
  margin: 1px 0 0;
  font-size: 10px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.topbar__center { text-align: center; }

.clock {
  font-family: var(--mono);
  font-size: 20px;
  letter-spacing: 0.14em;
  color: var(--cyan);
  text-shadow: 0 0 14px rgba(56, 240, 255, 0.6);
}

.clock-date {
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.topbar__status {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 11px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(56, 240, 255, 0.05);
  color: var(--text-dim);
  white-space: nowrap;
}

.dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--text-faint);
  flex: 0 0 auto;
}

.dot--live  { background: var(--green); box-shadow: 0 0 10px var(--green); animation: pulse 1.8s infinite; }
.dot--idle  { background: var(--amber); box-shadow: 0 0 8px var(--amber); }
.dot--error { background: var(--red);   box-shadow: 0 0 10px var(--red); }

/* ============================== Main grid =============================== */

.grid {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 268px minmax(0, 1fr) 330px;
  gap: 12px;
}

.panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* corner accents */
.panel::before,
.panel::after {
  content: "";
  position: absolute;
  width: 16px; height: 16px;
  pointer-events: none;
  border-color: var(--cyan);
  opacity: 0.7;
}

.panel::before {
  top: 7px; left: 7px;
  border-top: 1.5px solid;
  border-left: 1.5px solid;
  border-top-left-radius: 5px;
}

.panel::after {
  bottom: 7px; right: 7px;
  border-bottom: 1.5px solid;
  border-right: 1.5px solid;
  border-bottom-right-radius: 5px;
}

/* ============================== Left panel ============================== */

.panel--left {
  padding: 14px;
  gap: 14px;
  overflow-y: auto;
}

.block { display: flex; flex-direction: column; gap: 9px; }

.block + .block {
  padding-top: 13px;
  border-top: 1px solid rgba(56, 240, 255, 0.09);
}

.block__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--cyan-dim);
}

.tick {
  width: 5px; height: 5px;
  background: var(--cyan);
  box-shadow: 0 0 8px var(--cyan);
  transform: rotate(45deg);
  flex: 0 0 auto;
}

.stat-list { display: flex; flex-direction: column; gap: 7px; }

.stat {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  padding: 5px 9px;
  border-radius: var(--radius-sm);
  background: rgba(56, 240, 255, 0.035);
  border: 1px solid rgba(56, 240, 255, 0.07);
}

.stat__label {
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.stat__value {
  font-size: 11px;
  color: var(--text);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stat__value.ok    { color: var(--green); text-shadow: 0 0 10px rgba(62, 242, 161, 0.5); }
.stat__value.warn  { color: var(--amber); }
.stat__value.err   { color: var(--red); }

.meter-row { display: flex; flex-direction: column; gap: 5px; }

.meter-label {
  font-size: 9px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.meter {
  height: 5px;
  border-radius: 999px;
  background: rgba(56, 240, 255, 0.1);
  overflow: hidden;
}

.meter > i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--cyan-dim), var(--cyan));
  box-shadow: 0 0 12px rgba(56, 240, 255, 0.7);
  transition: width 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}

/* Agents */
.agents { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }

.agent {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 9px;
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(56, 240, 255, 0.09);
  background: rgba(56, 240, 255, 0.03);
  transition: all 0.25s ease;
}

.agent__status {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--text-faint);
  transition: all 0.25s ease;
}

.agent__name {
  font-size: 12px;
  letter-spacing: 0.06em;
}

.agent__role {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.agent.is-active {
  border-color: var(--line-strong);
  background: rgba(56, 240, 255, 0.1);
  box-shadow: inset 0 0 18px rgba(56, 240, 255, 0.12);
}

.agent.is-active .agent__status {
  background: var(--cyan);
  box-shadow: 0 0 10px var(--cyan);
  animation: pulse 1.3s infinite;
}

.agent.is-active .agent__name { color: #fff; text-shadow: 0 0 10px rgba(56, 240, 255, 0.6); }

.agent.is-done { border-color: rgba(62, 242, 161, 0.32); }
.agent.is-done .agent__status { background: var(--green); box-shadow: 0 0 8px var(--green); }

.block--actions { gap: 7px; }

/* ============================== Buttons ================================= */

.btn {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: rgba(56, 240, 255, 0.06);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.22s ease;
}

.btn:hover {
  color: #fff;
  border-color: var(--line-strong);
  background: rgba(56, 240, 255, 0.13);
  box-shadow: 0 0 18px rgba(56, 240, 255, 0.22);
}

.btn:active { transform: translateY(1px); }

.btn:disabled { opacity: 0.45; cursor: not-allowed; }

.btn--ghost { width: 100%; }

.btn--icon {
  padding: 0;
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: var(--radius-sm);
}

.btn--icon.is-listening {
  color: var(--red);
  border-color: rgba(255, 84, 112, 0.6);
  background: rgba(255, 84, 112, 0.14);
  box-shadow: 0 0 22px rgba(255, 84, 112, 0.4);
  animation: pulse 1.2s infinite;
}

.btn--send {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  height: 42px;
  flex: 0 0 auto;
  color: #04121a;
  font-weight: 700;
  border: none;
  background: linear-gradient(135deg, var(--cyan), #6ff6ff);
  box-shadow: 0 0 20px rgba(56, 240, 255, 0.45);
}

.btn--send:hover {
  color: #04121a;
  background: linear-gradient(135deg, #6ff6ff, var(--cyan));
  box-shadow: 0 0 30px rgba(56, 240, 255, 0.7);
}

.mini-btn {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.12em;
  padding: 3px 8px;
  border-radius: 5px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text-faint);
  cursor: pointer;
  transition: all 0.2s ease;
}

.mini-btn:hover { color: var(--cyan); border-color: var(--line-strong); }

/* ============================ Center panel ============================== */

.panel--center { padding: 14px; gap: 12px; }

.feed-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex: 0 0 auto;
}

.feed-head__meta {
  font-size: 9px;
  letter-spacing: 0.1em;
  color: var(--text-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 55%;
}

.feed {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 6px 4px 2px;
  scroll-behavior: smooth;
}

/* Messages */
.msg {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 11px;
  animation: msgIn 0.38s cubic-bezier(0.22, 1, 0.36, 1);
}

@keyframes msgIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

.msg__avatar {
  width: 34px; height: 34px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: rgba(56, 240, 255, 0.07);
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 700;
  color: var(--cyan);
  flex: 0 0 auto;
}

.msg__body { min-width: 0; }

.msg__meta {
  display: flex;
  align-items: baseline;
  gap: 9px;
  margin-bottom: 5px;
}

.msg__author {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--cyan-dim);
}

.msg__time {
  font-family: var(--mono);
  font-size: 9px;
  color: var(--text-faint);
}

.msg__content {
  padding: 11px 14px;
  border-radius: 0 var(--radius) var(--radius) var(--radius);
  border: 1px solid rgba(56, 240, 255, 0.12);
  background: rgba(56, 240, 255, 0.045);
  font-size: 13.5px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.msg__content > :first-child { margin-top: 0; }
.msg__content > :last-child  { margin-bottom: 0; }
.msg__content p { margin: 0 0 8px; }
.msg__content ul, .msg__content ol { margin: 0 0 8px; padding-left: 20px; }
.msg__content li { margin: 2px 0; }
.msg__content h1, .msg__content h2, .msg__content h3 {
  margin: 10px 0 6px;
  font-size: 14px;
  letter-spacing: 0.04em;
  color: #fff;
}
.msg__content a { color: var(--cyan); text-decoration: none; border-bottom: 1px dotted var(--cyan-dim); }
.msg__content a:hover { text-shadow: 0 0 10px rgba(56, 240, 255, 0.7); }
.msg__content strong { color: #fff; }
.msg__content hr { border: none; border-top: 1px solid var(--line); margin: 10px 0; }
.msg__content blockquote {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 2px solid var(--cyan-dim);
  color: var(--text-dim);
  background: rgba(56, 240, 255, 0.04);
}

/* inline code */
.msg__content code {
  font-family: var(--mono);
  font-size: 12px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(56, 240, 255, 0.12);
  color: #8ff7ff;
}

/* code blocks */
.msg__content pre {
  position: relative;
  margin: 9px 0;
  padding: 12px 13px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: rgba(2, 6, 12, 0.85);
  overflow-x: auto;
  box-shadow: inset 0 0 26px rgba(56, 240, 255, 0.05);
}

.msg__content pre code {
  display: block;
  padding: 0;
  background: none;
  color: #b8e8f5;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre;
}

/* very light syntax tinting (regex-based) */
.tok-key  { color: #ff7ac6; }
.tok-str  { color: #9cf58a; }
.tok-num  { color: #ffc978; }
.tok-com  { color: #56707f; font-style: italic; }
.tok-fn   { color: #6fd6ff; }

/* user messages */
.msg--user .msg__avatar {
  color: var(--blue);
  border-color: rgba(42, 107, 255, 0.4);
  background: rgba(42, 107, 255, 0.12);
}

.msg--user .msg__author { color: #7fa4ff; }

.msg--user .msg__content {
  border-color: rgba(42, 107, 255, 0.28);
  background: rgba(42, 107, 255, 0.1);
}

/* system messages */
.msg--system .msg__avatar {
  color: var(--green);
  border-color: rgba(62, 242, 161, 0.35);
  background: rgba(62, 242, 161, 0.1);
}

.msg--system .msg__author { color: var(--green); }

.msg--system .msg__content {
  border-color: rgba(62, 242, 161, 0.2);
  background: rgba(62, 242, 161, 0.05);
  color: var(--text-dim);
}

/* error messages */
.msg--error .msg__content {
  border-color: rgba(255, 84, 112, 0.4);
  background: rgba(255, 84, 112, 0.1);
  color: #ffc3ce;
}

.msg--error .msg__avatar {
  color: var(--red);
  border-color: rgba(255, 84, 112, 0.4);
  background: rgba(255, 84, 112, 0.12);
}

/* thinking indicator */
.thinking { display: inline-flex; gap: 5px; align-items: center; padding: 3px 0; }
.thinking i {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--cyan);
  opacity: 0.35;
  animation: blink 1.15s infinite;
}
.thinking i:nth-child(2) { animation-delay: 0.18s; }
.thinking i:nth-child(3) { animation-delay: 0.36s; }

@keyframes blink {
  0%, 100% { opacity: 0.25; transform: scale(0.85); }
  50%      { opacity: 1;    transform: scale(1.15); box-shadow: 0 0 10px var(--cyan); }
}

/* ============================= Composer ================================= */

.composer { flex: 0 0 auto; display: flex; flex-direction: column; gap: 9px; }

.chips {
  display: flex;
  gap: 7px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}
.chips::-webkit-scrollbar { display: none; }

.chip {
  flex: 0 0 auto;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.05em;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(56, 240, 255, 0.05);
  color: var(--text-dim);
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.chip:hover {
  color: #fff;
  border-color: var(--line-strong);
  background: rgba(56, 240, 255, 0.14);
  box-shadow: 0 0 16px rgba(56, 240, 255, 0.22);
  transform: translateY(-1px);
}

.input-row {
  display: flex;
  gap: 9px;
  align-items: center;
  padding: 7px;
  border-radius: var(--radius);
  border: 1px solid var(--line);
  background: rgba(2, 6, 12, 0.6);
  transition: border-color 0.25s ease, box-shadow 0.25s ease;
}

.input-row:focus-within {
  border-color: var(--line-strong);
  box-shadow: 0 0 0 1px rgba(56, 240, 255, 0.18), 0 0 26px rgba(56, 240, 255, 0.16);
}

.input {
  flex: 1 1 auto;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text);
  font-family: var(--mono);
  font-size: 13px;
  padding: 8px 6px;
}

.input::placeholder { color: var(--text-faint); }

/* ============================== Terminal ================================ */

.panel--right { padding: 14px; gap: 10px; }

.terminal {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.65;
  padding: 10px 11px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(56, 240, 255, 0.1);
  background: rgba(1, 4, 8, 0.78);
  box-shadow: inset 0 0 34px rgba(56, 240, 255, 0.045);
}

.tline {
  display: flex;
  gap: 8px;
  padding: 1px 0;
  animation: lineIn 0.25s ease;
  border-left: 2px solid transparent;
  padding-left: 7px;
  margin-left: -7px;
}

@keyframes lineIn {
  from { opacity: 0; transform: translateX(-6px); }
  to   { opacity: 1; transform: translateX(0); }
}

.tline__time { color: #33566a; flex: 0 0 auto; }
.tline__tag  { flex: 0 0 auto; font-weight: 700; letter-spacing: 0.05em; }
.tline__msg  { color: var(--text-dim); overflow-wrap: anywhere; }

.tline--route    { border-left-color: var(--blue); }
.tline--route    .tline__tag { color: #7fa4ff; }
.tline--thought  { border-left-color: var(--cyan-dim); }
.tline--thought  .tline__tag { color: var(--cyan); }
.tline--tool     { border-left-color: var(--magenta); }
.tline--tool     .tline__tag { color: var(--magenta); }
.tline--result   { border-left-color: var(--green); }
.tline--result   .tline__tag { color: var(--green); }
.tline--final    { border-left-color: var(--green); }
.tline--final    .tline__tag { color: var(--green); }
.tline--error    { border-left-color: var(--red); }
.tline--error    .tline__tag { color: var(--red); }
.tline--error    .tline__msg { color: #ffc3ce; }
.tline--sys      { border-left-color: #2e4a5c; }
.tline--sys      .tline__tag { color: var(--text-faint); }

.term-foot {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 9px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-faint);
}

.term-foot__sep { color: var(--cyan-dim); }

/* ============================ Scrollbars ================================ */

.feed::-webkit-scrollbar,
.terminal::-webkit-scrollbar,
.panel--left::-webkit-scrollbar {
  width: 7px;
}

.feed::-webkit-scrollbar-track,
.terminal::-webkit-scrollbar-track,
.panel--left::-webkit-scrollbar-track {
  background: transparent;
}

.feed::-webkit-scrollbar-thumb,
.terminal::-webkit-scrollbar-thumb,
.panel--left::-webkit-scrollbar-thumb {
  background: rgba(56, 240, 255, 0.22);
  border-radius: 999px;
}

.feed::-webkit-scrollbar-thumb:hover,
.terminal::-webkit-scrollbar-thumb:hover,
.panel--left::-webkit-scrollbar-thumb:hover {
  background: rgba(56, 240, 255, 0.4);
}

.feed, .terminal, .panel--left {
  scrollbar-width: thin;
  scrollbar-color: rgba(56, 240, 255, 0.25) transparent;
}

/* ============================ Responsive ================================ */

@media (max-width: 1180px) {
  .grid { grid-template-columns: 232px minmax(0, 1fr) 280px; }
  .brand-sub { display: none; }
}

@media (max-width: 980px) {
  body { overflow: auto; }
  .app { height: auto; min-height: 100dvh; }
  .grid {
    grid-template-columns: 1fr;
    grid-template-areas: "center" "left" "right";
  }
  .panel--center { grid-area: center; min-height: 62vh; }
  .panel--left   { grid-area: left; }
  .panel--right  { grid-area: right; min-height: 240px; }
  .panel--left { overflow: visible; }
  .topbar { grid-template-columns: 1fr auto; }
  .topbar__center { display: none; }
}

@media (max-width: 640px) {
  .app { padding: 8px; gap: 9px; }
  .topbar { padding: 10px 12px; }
  .brand-text h1 { font-size: 15px; letter-spacing: 0.12em; }
  .reactor { width: 32px; height: 32px; }
  .reactor__core { inset: 11px; }
  .topbar__status .pill { font-size: 9px; padding: 4px 8px; }
  .btn--send span { display: none; }
  .btn--send { padding: 0 13px; }
  .msg { grid-template-columns: 28px minmax(0, 1fr); gap: 9px; }
  .msg__avatar { width: 28px; height: 28px; font-size: 11px; }
  .msg__content { font-size: 13px; padding: 10px 12px; }
  .panel--center { min-height: 66vh; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
}
```

## 16. `static/script.js`

**WebSocket client, markdown renderer, voice input** — 821 lines

```javascript
/* ==========================================================================
   JARVIS-OMEGA — HUD client
   WebSocket link, markdown rendering, voice input, live trace terminal.
   ========================================================================== */
(() => {
  "use strict";

  /* ----------------------------- DOM refs ----------------------------- */
  const $ = (id) => document.getElementById(id);

  const els = {
    feed: $("feed"),
    form: $("chatForm"),
    input: $("chatInput"),
    send: $("btnSend"),
    voice: $("btnVoice"),
    terminal: $("terminal"),
    termStatus: $("termStatus"),
    termCount: $("termCount"),
    clock: $("clock"),
    clockDate: $("clockDate"),
    wsDot: $("wsDot"),
    wsLabel: $("wsLabel"),
    llmDot: $("llmDot"),
    llmLabel: $("llmLabel"),
    statUptime: $("statUptime"),
    statMsgs: $("statMsgs"),
    statLatency: $("statLatency"),
    statCore: $("statCore"),
    loadBar: $("loadBar"),
    memBar: $("memBar"),
    memCount: $("memCount"),
    memSession: $("memSession"),
    feedMeta: $("feedMeta"),
    agentList: $("agentList"),
    btnClear: $("btnClear"),
    btnExport: $("btnExport"),
    btnClearLog: $("btnClearLog"),
  };

  /* ------------------------------ State ------------------------------- */
  const state = {
    ws: null,
    connected: false,
    busy: false,
    sessionId: "sess-" + Math.random().toString(36).slice(2, 10),
    messageCount: 0,
    eventCount: 0,
    startedAt: Date.now(),
    pendingTimer: null,
    listening: false,
    recognition: null,
    retry: 0,
    maxRetry: 20000,
  };

  /* ==================================================================== */
  /* Utilities                                                            */
  /* ==================================================================== */
  const pad = (n) => String(n).padStart(2, "0");

  function nowTime() {
    const d = new Date();
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function scrollFeed() {
    const el = els.feed;
    el.scrollTop = el.scrollHeight;
  }

  function scrollTerm() {
    els.terminal.scrollTop = els.terminal.scrollHeight;
  }

  /* ==================================================================== */
  /* Minimal, safe markdown renderer (no external deps)                   */
  /* ==================================================================== */

  const KEYWORDS = new Set([
    "def", "class", "return", "if", "else", "elif", "for", "while", "import",
    "from", "as", "try", "except", "finally", "with", "lambda", "yield",
    "async", "await", "pass", "raise", "in", "is", "not", "and", "or",
    "none", "true", "false", "None", "True", "False", "self", "const", "let",
    "var", "function", "new", "this", "throw", "catch", "switch", "case",
    "default", "break", "continue", "export", "default", "typeof", "instanceof",
    "void", "delete", "static", "public", "private", "interface", "type",
    "enum", "package", "func", "struct", "go", "defer", "map", "range", "echo",
    "then", "fi", "do", "done", "esac", "local", "fi", "sudo", "export",
  ]);

  function highlight(code, lang) {
    const esc = escapeHtml(code);
    if (!lang || ["text", "output", "plain", "log"].includes(lang)) return esc;

    // Work on escaped text; tokenise comments, strings, numbers, keywords.
    let out = esc;

    // Comments (// ... and # ...) — only when at line start or after whitespace
    out = out.replace(/(^|\n)(\s*)(#[^\n]*|\/\/[^\n]*)/g,
      (m, nl, sp, c) => `${nl}${sp}<span class="tok-com">${c}</span>`);

    // Strings (single, double, backtick)
    out = out.replace(/(&quot;.*?&quot;|&#39;.*?&#39;|`[^`]*`)/g,
      (m) => `<span class="tok-str">${m}</span>`);

    // Numbers
    out = out.replace(/\b(\d+(?:\.\d+)?)\b/g,
      (m) => `<span class="tok-num">${m}</span>`);

    // Keywords (avoid touching HTML we already injected)
    out = out.replace(/\b([A-Za-z_$][\w$]*)\b/g, (m) => {
      if (KEYWORDS.has(m) || KEYWORDS.has(m.toLowerCase())) {
        return `<span class="tok-key">${m}</span>`;
      }
      return m;
    });

    // Function calls
    out = out.replace(/\b([A-Za-z_$][\w$]*)(\s*\()/g, (m, fn, paren) => {
      if (fn.includes("span")) return m;
      return `<span class="tok-fn">${fn}</span>${paren}`;
    });

    return out;
  }

  function renderInline(text) {
    let s = escapeHtml(text);
    // inline code first (protect from other replacements)
    const codes = [];
    s = s.replace(/`([^`]+)`/g, (m, c) => {
      codes.push(c);
      return `\u0000CODE${codes.length - 1}\u0000`;
    });

    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    s = s.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    // bare URLs
    s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g,
      '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');

    s = s.replace(/\u0000CODE(\d+)\u0000/g,
      (m, i) => `<code>${codes[Number(i)]}</code>`);
    return s;
  }

  function renderMarkdown(md) {
    const lines = String(md).replace(/\r\n/g, "\n").split("\n");
    const html = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      // fenced code block
      const fence = line.match(/^```(\w*)\s*$/);
      if (fence) {
        const lang = (fence[1] || "").toLowerCase();
        const body = [];
        i++;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) {
          body.push(lines[i]);
          i++;
        }
        i++; // closing fence
        html.push(
          `<pre><code class="lang-${escapeHtml(lang || "text")}">` +
          highlight(body.join("\n"), lang) +
          `</code></pre>`
        );
        continue;
      }

      // horizontal rule
      if (/^\s*(---+|\*\*\*+|___+)\s*$/.test(line)) {
        html.push("<hr />");
        i++;
        continue;
      }

      // headings
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) {
        const lvl = Math.min(6, h[1].length);
        html.push(`<h${lvl}>${renderInline(h[2])}</h${lvl}>`);
        i++;
        continue;
      }

      // blockquote
      if (/^>\s?/.test(line)) {
        const quote = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) {
          quote.push(lines[i].replace(/^>\s?/, ""));
          i++;
        }
        html.push(`<blockquote>${renderInline(quote.join(" "))}</blockquote>`);
        continue;
      }

      // unordered list
      if (/^\s*[-*+]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*[-*+]\s+/, ""));
          i++;
        }
        html.push("<ul>" + items.map((t) => `<li>${renderInline(t)}</li>`).join("") + "</ul>");
        continue;
      }

      // ordered list
      if (/^\s*\d+[.)]\s+/.test(line)) {
        const items = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
          i++;
        }
        html.push("<ol>" + items.map((t) => `<li>${renderInline(t)}</li>`).join("") + "</ol>");
        continue;
      }

      // blank
      if (!line.trim()) {
        i++;
        continue;
      }

      // paragraph
      const para = [];
      while (
        i < lines.length &&
        lines[i].trim() &&
        !/^```/.test(lines[i]) &&
        !/^(#{1,6})\s+/.test(lines[i]) &&
        !/^\s*[-*+]\s+/.test(lines[i]) &&
        !/^\s*\d+[.)]\s+/.test(lines[i]) &&
        !/^>\s?/.test(lines[i]) &&
        !/^\s*(---+|\*\*\*+|___+)\s*$/.test(lines[i])
      ) {
        para.push(lines[i]);
        i++;
      }
      html.push(`<p>${renderInline(para.join(" "))}</p>`);
    }

    return html.join("\n");
  }

  /* ==================================================================== */
  /* Feed rendering                                                       */
  /* ==================================================================== */
  function addMessage({ role = "system", author = "JARVIS-OMEGA", avatar = "Ω", content = "", raw = false, time }) {
    const wrap = document.createElement("article");
    wrap.className = `msg msg--${role}`;

    const avatarEl = document.createElement("div");
    avatarEl.className = "msg__avatar";
    avatarEl.textContent = avatar;

    const body = document.createElement("div");
    body.className = "msg__body";

    const meta = document.createElement("div");
    meta.className = "msg__meta";
    meta.innerHTML = `<span class="msg__author">${escapeHtml(author)}</span>` +
                     `<span class="msg__time">${escapeHtml(time || nowTime())}</span>`;

    const contentEl = document.createElement("div");
    contentEl.className = "msg__content";
    if (raw) contentEl.innerHTML = content;
    else contentEl.innerHTML = renderMarkdown(content);

    body.appendChild(meta);
    body.appendChild(contentEl);
    wrap.appendChild(avatarEl);
    wrap.appendChild(body);

    els.feed.appendChild(wrap);
    scrollFeed();
    return { wrap, contentEl };
  }

  function addThinking(agentName) {
    const { wrap, contentEl } = addMessage({
      role: "system",
      author: agentName || "JARVIS-OMEGA",
      avatar: "◈",
      raw: true,
      content: `<span class="thinking"><i></i><i></i><i></i></span>
                <span class="dim" style="font-size:11px;margin-left:8px">processing…</span>`,
    });
    return wrap;
  }

  /* ==================================================================== */
  /* Terminal rendering                                                   */
  /* ==================================================================== */
  const TAG_MAP = {
    route: ["ROUTE", "tline--route"],
    thought: ["THINK", "tline--thought"],
    tool_call: ["TOOL", "tline--tool"],
    tool_result: ["RESULT", "tline--result"],
    final: ["FINAL", "tline--final"],
    error: ["ERR", "tline--error"],
    ack: ["SYS", "tline--sys"],
    sys: ["SYS", "tline--sys"],
  };

  function termLine(kind, message, agent) {
    const [tag, cls] = TAG_MAP[kind] || ["LOG", "tline--sys"];
    const line = document.createElement("div");
    line.className = `tline ${cls}`;

    const time = document.createElement("span");
    time.className = "tline__time";
    time.textContent = nowTime();

    const tagEl = document.createElement("span");
    tagEl.className = "tline__tag";
    tagEl.textContent = agent ? `[${agent}]` : `[${tag}]`;

    const msg = document.createElement("span");
    msg.className = "tline__msg";
    const short = String(message || "").replace(/\s+/g, " ").trim();
    msg.textContent = short.length > 220 ? short.slice(0, 220) + "…" : short;

    line.append(time, tagEl, msg);
    els.terminal.appendChild(line);

    // Cap the trace so memory stays bounded.
    while (els.terminal.childElementCount > 400) {
      els.terminal.removeChild(els.terminal.firstChild);
    }

    state.eventCount += 1;
    els.termCount.textContent = `${state.eventCount} event${state.eventCount === 1 ? "" : "s"}`;
    scrollTerm();
  }

  /* ==================================================================== */
  /* Agent monitor                                                        */
  /* ==================================================================== */
  function setAgentActive(name) {
    document.querySelectorAll(".agent").forEach((el) => {
      el.classList.remove("is-active");
      if (el.dataset.agent === name) el.classList.add("is-active");
    });
    const load = Math.min(96, 22 + Math.random() * 55);
    els.loadBar.style.width = `${load}%`;
  }

  function markAgentDone(name) {
    document.querySelectorAll(".agent").forEach((el) => {
      if (el.dataset.agent === name) {
        el.classList.remove("is-active");
        el.classList.add("is-done");
      }
    });
    els.loadBar.style.width = "10%";
    setTimeout(() => {
      document.querySelectorAll(".agent.is-done").forEach((el) => el.classList.remove("is-done"));
    }, 2600);
  }

  /* ==================================================================== */
  /* WebSocket                                                            */
  /* ==================================================================== */
  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    // Relative to the current origin so it works behind proxies / previews.
    return `${proto}//${location.host}/ws/chat`;
  }

  function setLink(dotEl, labelEl, stateName, text) {
    dotEl.className = `dot dot--${stateName}`;
    labelEl.textContent = text;
  }

  function connect() {
    try {
      state.ws = new WebSocket(wsUrl());
    } catch (err) {
      scheduleReconnect();
      return;
    }

    state.ws.addEventListener("open", () => {
      state.connected = true;
      state.retry = 0;
      setLink(els.wsDot, els.wsLabel, "live", "LINKED");
      termLine("sys", "Neural link established.", "System");
      els.feedMeta.textContent = `session: ${state.sessionId}`;
      els.memSession.textContent = state.sessionId.slice(-6);
    });

    state.ws.addEventListener("message", (ev) => {
      let data;
      try {
        data = JSON.parse(ev.data);
      } catch {
        return;
      }
      handleEvent(data);
    });

    state.ws.addEventListener("close", () => {
      state.connected = false;
      setLink(els.wsDot, els.wsLabel, "error", "LINK LOST");
      termLine("error", "Neural link dropped. Attempting reconnect…", "System");
      finishPending();
      scheduleReconnect();
    });

    state.ws.addEventListener("error", () => {
      setLink(els.wsDot, els.wsLabel, "error", "LINK ERR");
    });
  }

  function scheduleReconnect() {
    state.retry = Math.min(state.maxRetry, Math.max(1200, state.retry * 1.8 || 1200));
    setTimeout(() => {
      if (!state.connected) connect();
    }, state.retry);
  }

  /* --------------------------- Event handling ------------------------- */
  function handleEvent(data) {
    const type = data.type || "sys";
    const agent = data.agent || "System";
    const message = data.message || "";

    // Latency: from send to first response event.
    if (state.pendingTimer) {
      els.statLatency.textContent = `${Date.now() - state.pendingTimer} ms`;
      els.statLatency.className = "stat__value mono ok";
      state.pendingTimer = null;
    }

    switch (type) {
      case "ack":
        termLine("ack", message, agent);
        break;

      case "route":
        setAgentActive(agent);
        termLine("route", message, agent);
        break;

      case "thought":
        setAgentActive(agent);
        termLine("thought", message, agent);
        break;

      case "tool_call":
        setAgentActive(agent);
        termLine("tool_call", message, agent);
        break;

      case "tool_result":
        termLine("tool_result", message, agent);
        break;

      case "error":
        termLine("error", message, agent);
        removeThinking();
        addMessage({
          role: "error",
          author: "SYSTEM FAULT",
          avatar: "!",
          content: message,
        });
        finishPending();
        break;

      case "final":
        removeThinking();
        markAgentDone(agent);
        termLine("final", `Response delivered (${message.length} chars)`, agent);
        addMessage({
          role: "assistant",
          author: `${agent.toUpperCase()} AGENT`,
          avatar: "Ω",
          content: message,
        });
        state.messageCount += 1;
        els.statMsgs.textContent = String(state.messageCount);
        finishPending();
        refreshMemory();
        break;

      default:
        termLine("sys", message, agent);
    }
  }

  /* ------------------------- Pending indicator ------------------------ */
  let thinkingEl = null;

  function startPending(agentName) {
    state.busy = true;
    els.send.disabled = true;
    els.statCore.textContent = "BUSY";
    els.statCore.className = "stat__value warn";
    thinkingEl = addThinking(agentName);
    state.pendingTimer = Date.now();
    els.termStatus.textContent = "processing";
  }

  function removeThinking() {
    if (thinkingEl && thinkingEl.parentNode) {
      thinkingEl.parentNode.removeChild(thinkingEl);
    }
    thinkingEl = null;
  }

  function finishPending() {
    removeThinking();
    state.busy = false;
    els.send.disabled = false;
    els.statCore.textContent = "ONLINE";
    els.statCore.className = "stat__value ok";
    els.termStatus.textContent = "idle";
    document.querySelectorAll(".agent.is-active").forEach((el) => el.classList.remove("is-active"));
    els.loadBar.style.width = "8%";
  }

  /* ==================================================================== */
  /* Sending messages                                                     */
  /* ==================================================================== */
  function send(text) {
    const message = (text || "").trim();
    if (!message) return;

    if (!state.connected || !state.ws || state.ws.readyState !== WebSocket.OPEN) {
      addMessage({
        role: "error",
        author: "LINK ERROR",
        avatar: "!",
        content: "Neural link is not established. Reconnecting — please try again in a moment.",
      });
      termLine("error", "Send aborted: socket not open.", "System");
      connect();
      return;
    }

    if (state.busy) {
      termLine("sys", "Core busy; message queued request ignored.", "System");
      return;
    }

    addMessage({
      role: "user",
      author: "OPERATOR",
      avatar: "▸",
      content: message,
    });
    termLine("sys", `Transmitting: ${message}`, "Operator");

    try {
      state.ws.send(JSON.stringify({
        session_id: state.sessionId,
        message,
      }));
    } catch (err) {
      termLine("error", `Transmit failed: ${err}`, "System");
      return;
    }

    startPending("ROUTER");
    els.input.value = "";
    els.input.focus();
    state.messageCount += 1;
    els.statMsgs.textContent = String(state.messageCount);
  }

  /* ==================================================================== */
  /* Voice input (Web Speech API)                                         */
  /* ==================================================================== */
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function initVoice() {
    if (!SpeechRecognition) {
      els.voice.disabled = true;
      els.voice.title = "Speech recognition not supported in this browser";
      return;
    }

    const rec = new SpeechRecognition();
    rec.lang = navigator.language || "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;

    rec.addEventListener("result", (ev) => {
      let transcript = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        transcript += ev.results[i][0].transcript;
      }
      els.input.value = transcript;
      if (ev.results[ev.results.length - 1].isFinal) {
        stopVoice();
        const text = transcript.trim();
        if (text) send(text);
      }
    });

    rec.addEventListener("error", (ev) => {
      termLine("error", `Voice error: ${ev.error}`, "System");
      stopVoice();
    });

    rec.addEventListener("end", () => stopVoice());

    state.recognition = rec;
    els.voice.addEventListener("click", toggleVoice);
  }

  function toggleVoice() {
    if (state.listening) {
      stopVoice();
    } else {
      startVoice();
    }
  }

  function startVoice() {
    if (!state.recognition) return;
    try {
      state.recognition.start();
      state.listening = true;
      els.voice.classList.add("is-listening");
      els.input.placeholder = "Listening…";
      els.termStatus.textContent = "listening";
      termLine("sys", "Voice input engaged.", "System");
    } catch (err) {
      termLine("error", `Cannot start voice: ${err.message}`, "System");
    }
  }

  function stopVoice() {
    state.listening = false;
    els.voice.classList.remove("is-listening");
    els.input.placeholder = "Speak or type a command…";
    els.termStatus.textContent = "idle";
    try {
      if (state.recognition) state.recognition.stop();
    } catch { /* noop */ }
  }

  /* ==================================================================== */
  /* Clock, uptime, status polling                                        */
  /* ==================================================================== */
  function tickClock() {
    const d = new Date();
    els.clock.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    els.clockDate.textContent = d.toLocaleDateString(undefined, {
      weekday: "short", year: "numeric", month: "short", day: "2-digit",
    });

    const elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
    const h = pad(Math.floor(elapsed / 3600));
    const m = pad(Math.floor((elapsed % 3600) / 60));
    const s = pad(elapsed % 60);
    els.statUptime.textContent = `${h}:${m}:${s}`;
  }

  async function refreshStatus() {
    try {
      const res = await fetch("/api/status", { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();

      if (data.llm_configured) {
        setLink(els.llmDot, els.llmLabel, "live", "GEMINI");
      } else {
        setLink(els.llmDot, els.llmLabel, "idle", "OFFLINE AI");
      }

      if (Array.isArray(data.agents) && data.agents.length) {
        // Keep the static roster markup; just annotate titles.
        data.agents.forEach((a) => {
          const el = document.querySelector(`.agent[data-agent="${a.name}"]`);
          if (el) el.title = a.description || a.name;
        });
      }
    } catch {
      setLink(els.llmDot, els.llmLabel, "error", "NO CORE");
    }
  }

  async function refreshMemory() {
    try {
      const res = await fetch("/api/memory?limit=100", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const count = data.count || 0;
      els.memCount.textContent = String(count);
      els.memBar.style.width = `${Math.min(100, 4 + count * 6)}%`;
    } catch { /* silent */ }
  }

  /* ==================================================================== */
  /* Wiring                                                               */
  /* ==================================================================== */
  function init() {
    // Form submit
    els.form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      send(els.input.value);
    });

    // Quick action chips
    document.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const cmd = chip.dataset.cmd;
        if (cmd) {
          els.input.value = cmd;
          send(cmd);
        }
      });
    });

    // Enter to send (Shift+Enter newline not applicable to input, keep simple)
    els.input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        send(els.input.value);
      }
      if (ev.key === "Escape") {
        els.input.value = "";
        els.input.blur();
      }
    });

    // Global "/" focus shortcut
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "/" && document.activeElement !== els.input) {
        ev.preventDefault();
        els.input.focus();
      }
    });

    // Clear feed
    els.btnClear.addEventListener("click", () => {
      els.feed.innerHTML = "";
      addMessage({
        role: "system",
        author: "JARVIS-OMEGA",
        avatar: "Ω",
        content: "Feed purged. Core still online.",
      });
      termLine("sys", "Conversation feed purged by operator.", "System");
    });

    // Clear trace
    els.btnClearLog.addEventListener("click", () => {
      els.terminal.innerHTML = "";
      state.eventCount = 0;
      els.termCount.textContent = "0 events";
      termLine("sys", "Execution trace cleared.", "System");
    });

    // Export log
    els.btnExport.addEventListener("click", () => {
      const lines = [];
      els.terminal.querySelectorAll(".tline").forEach((l) => {
        lines.push(l.textContent.trim());
      });
      const text =
        `JARVIS-OMEGA execution trace\n` +
        `session: ${state.sessionId}\n` +
        `exported: ${new Date().toISOString()}\n` +
        `${"-".repeat(60)}\n` +
        lines.join("\n") + "\n";

      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `jarvis-trace-${Date.now()}.log`;
      a.click();
      URL.revokeObjectURL(url);
      termLine("sys", "Execution trace exported.", "System");
    });

    // Boot sequence
    tickClock();
    setInterval(tickClock, 1000);

    initVoice();
    connect();
    refreshStatus();
    refreshMemory();

    setInterval(refreshStatus, 20000);
    setInterval(refreshMemory, 30000);

    termLine("sys", "HUD initialised. Awaiting neural link…", "System");
    els.input.focus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
```

## 17. `scripts/deploy_github.py`

**Automated GitHub deployment** — 658 lines

```python
#!/usr/bin/env python3
"""
scripts/deploy_github.py
------------------------
Automated GitHub deployment for JARVIS-OMEGA.

What it does
------------
1. Verifies we are in the JARVIS project root.
2. Initialises `.git` if missing (and sets a sane default branch).
3. Writes a standard `.gitignore` (secrets, caches, DBs, venvs).
4. Generates a comprehensive README.md if one does not already exist.
5. Stages all files and creates an initial commit (if there are changes).
6. Creates the GitHub repo (via `gh`) and pushes — or prints exact
   manual instructions if `gh` is unavailable.

Usage
-----
    python scripts/deploy_github.py                     # interactive
    python scripts/deploy_github.py --repo jarvis-omega --user myname
    python scripts/deploy_github.py --private --no-push
    python scripts/deploy_github.py --dry-run

Zero external dependencies — stdlib only. Works on PC and Termux.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent          # .../jarvis
REPO_ROOT = PROJECT_ROOT.parent           # repo containing jarvis/


DEFAULT_REPO_NAME = "jarvis-omega"
DEFAULT_BRANCH = "main"


GITIGNORE = """\
# ------------------------- Secrets & environment -------------------------
.env
.env.*
*.env
!.env.example
secrets.json
*.pem
*.key
credentials.json

# ------------------------- Python ---------------------------------------
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# ------------------------- Virtual environments --------------------------
.venv/
venv/
ENV/
env/
.python-version

# ------------------------- Databases & data ------------------------------
*.db
*.db-wal
*.db-shm
*.sqlite
*.sqlite3
data/
jarvis_omega.db*

# ------------------------- Logs ------------------------------------------
*.log
logs/

# ------------------------- Testing / tooling -----------------------------
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.tox/
.nox/

# ------------------------- Editors / OS ----------------------------------
.vscode/
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db
desktop.ini

# ------------------------- Node (if you extend the HUD) ------------------
node_modules/
npm-debug.log*
yarn-error.log*
"""


README = """\
# JARVIS-OMEGA

> A zero-budget, multi-agent personal AI assistant with a futuristic sci-fi HUD.
> FastAPI + WebSockets + Google Gemini + SQLite. Runs on PC and Android Termux.

---

## Features

- **Multi-agent orchestration** — a master router dispatches work to four
  specialist agents (Coder, Research, System, Memory) based on intent confidence.
- **Real-time streaming** — every thought, tool call and result is pushed to the
  HUD over WebSockets as it happens.
- **Futuristic HUD** — glassmorphism panels, neon cyan accents, live execution
  trace, markdown + syntax-highlighted code, voice input via Web Speech API.
- **Secure sandbox** — shell execution is blocklisted, time-limited and
  output-capped; file operations are confined to the workspace.
- **Persistent memory** — SQLite-backed conversation history, long-term memory
  and task audit logs.
- **Offline fallback** — runs without any API key in heuristic mode; add a free
  Gemini key for full reasoning.
- **One-command GitHub deploy** — `scripts/deploy_github.py` bootstraps git,
  `.gitignore`, README, commit and push.

---

## Architecture

```
Browser HUD (index.html/style.css/script.js)
        │  WebSocket /ws/chat
        ▼
main.py  (FastAPI + CORS + static mount)
        │
        ▼
core/orchestrator.py  ── intent routing + event streaming
        │
        ├── agents/coder_agent.py      code generation / safe execution
        ├── agents/research_agent.py   web search + summarisation
        ├── agents/system_agent.py     diagnostics / sandboxed commands
        └── agents/memory_agent.py     store & recall persistent memory
                 │
                 ├── tools/shell_tool.py       sandboxed subprocess runner
                 ├── tools/web_search_tool.py  DuckDuckGo / Bing scraping
                 ├── tools/file_manager.py     workspace-scoped file ops
                 ├── core/llm.py               Gemini + offline fallback
                 └── database.py               SQLite persistence
```

---

## Installation — Desktop / Server

```bash
git clone <your-repo-url> jarvis-omega
cd jarvis-omega/jarvis

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt

export GEMINI_API_KEY="your-free-key"   # optional but recommended
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open <http://localhost:8000>.

Get a free API key at <https://aistudio.google.com/apikey>.

---

## Installation — Android (Termux)

```bash
pkg update && pkg upgrade -y
pkg install -y python git rust binutils libffi openssl

git clone <your-repo-url> ~/jarvis-omega
cd ~/jarvis-omega/jarvis

pip install -r requirements.txt

export GEMINI_API_KEY="your-free-key"
uvicorn main:app --host 0.0.0.0 --port 8080
```

Open <http://localhost:8080> in your phone browser.

**Termux tips**

- Long builds can be killed in the background: run `termux-wake-lock` first, and
  disable battery optimisation for Termux in Android settings.
- If `pip install` fails on a package, retry with `pkg install python-numpy` or
  build tools: `pkg install build-essential cmake`.
- To reach the HUD from another device on the same network, use the phone's
  `ip addr show wlan0` address with port 8080.

---

## Configuration

Environment variables (or a `.env` file in `jarvis/` — see `.env.example`).
Shell exports always take precedence over the file:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key — enables full reasoning |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Model ID |
| `GEMINI_TEMPERATURE` | `0.7` | Sampling temperature |
| `GEMINI_MAX_TOKENS` | `2048` | Max output tokens |
| `JARVIS_HOST` | `0.0.0.0` | Bind address |
| `JARVIS_PORT` | `8000` | Bind port |
| `JARVIS_CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `JARVIS_WORKSPACE` | `jarvis/workspace` | Directory agents may read/write and run commands in |
| `JARVIS_SHELL_TIMEOUT` | `30` | Shell command timeout (seconds) |
| `JARVIS_SHELL_MAX_OUTPUT` | `65536` | Max captured output bytes |

---

## Usage

Type a command, or use a quick-action chip:

| You say | Agent | What happens |
|---|---|---|
| `system status` | System | OS, CPU, memory, disk, network snapshot |
| `list files in .` | System | Workspace directory listing |
| `search for FastAPI best practices` | Research | Live web search + summarised answer with sources |
| `write a python script that prints fibonacci to fib.py` | Coder | Generates and writes the file |
| `run fib.py` | Coder | Executes it in the sandbox and returns output |
| `remember my project is JARVIS as project` | Memory | Stores a long-term memory record |
| `recall project` | Memory | Retrieves it |

### HUD keyboard shortcuts

- `/` — focus the command input
- `Enter` — transmit
- `Esc` — clear input

---

## Security model

- **Command blocklist** — destructive patterns (`rm -rf /`, fork bombs, `mkfs`,
  `dd if=`, disk writes, shutdown/reboot) are rejected before execution.
- **Binary allowlist check** — blocked binaries never run; unknown binaries are
  refused if not found in `PATH`.
- **Hard timeout** — every command is killed after `JARVIS_SHELL_TIMEOUT`.
- **Output cap** — stdout/stderr are truncated to prevent memory blowups.
- **Workspace confinement** — the file manager refuses any path that resolves
  outside the configured workspace (`jarvis/workspace/` by default, or
  `JARVIS_WORKSPACE`). Point it at your code directory only if you want agents
  editing real source.
- **No secrets in git** — `.gitignore` excludes `.env`, keys and databases.

> This is a *convenience* sandbox for a personal assistant, not a security
> boundary against hostile input. Do not expose the server to the public
> internet without authentication and additional hardening.

---

## GitHub deployment

```bash
cd jarvis
python scripts/deploy_github.py --repo jarvis-omega --user <your-github-username>
```

The script initialises git, writes `.gitignore` + `README.md`, commits, then
either creates and pushes the repo with the GitHub CLI (`gh`) or prints the
exact commands for you to run.

Options:

```bash
python scripts/deploy_github.py --private     # private repo
python scripts/deploy_github.py --no-push     # commit locally only
python scripts/deploy_github.py --dry-run     # show actions, change nothing
```

---

## Project layout

```
jarvis/
├── main.py                  FastAPI app, WebSocket endpoint, static mount
├── config.py                env vars, paths, security policy
├── database.py              SQLite: chat, memory, task logs
├── requirements.txt
├── core/
│   ├── base_agent.py        abstract agent + event/context dataclasses
│   ├── llm.py               Gemini client + offline fallback
│   └── orchestrator.py      router + streaming execution loop
├── agents/
│   ├── coder_agent.py
│   ├── research_agent.py
│   ├── system_agent.py
│   └── memory_agent.py
├── tools/
│   ├── shell_tool.py        sandboxed subprocess execution
│   ├── web_search_tool.py   DuckDuckGo/Bing aggregation
│   └── file_manager.py      workspace-scoped file ops
├── static/
│   ├── index.html           HUD structure
│   ├── style.css            sci-fi styling
│   └── script.js            WebSocket client + renderer + voice
├── scripts/
│   └── deploy_github.py     automated git/GitHub deployment
├── workspace/               default agent sandbox (gitignored, seeded with a README)
└── data/                    SQLite DB + logs (gitignored)
```

---

## Troubleshooting

**`ModuleNotFoundError: config`** — run from inside `jarvis/` (`uvicorn main:app`)
or from the repo root (`uvicorn jarvis.main:app`). Both are supported.

**HUD shows `OFFLINE AI`** — no `GEMINI_API_KEY` is set. The assistant still
works in heuristic mode; export the key and restart for full reasoning.

**`LINK LOST` in the top bar** — the WebSocket dropped. The client retries
automatically; check that the server is running and the port matches.

**Voice button disabled** — the Web Speech API needs Chrome/Edge/Safari and a
secure context (`localhost` or HTTPS).

---

## License

MIT — use it, fork it, build on it.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"  {msg}")


def step(msg: str) -> None:
    print(f"\n▸ {msg}")


def run(cmd: list[str], cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def git_available() -> bool:
    return shutil.which("git") is not None


def gh_available() -> bool:
    return shutil.which("gh") is not None


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


# ---------------------------------------------------------------------------
# Deployment steps
# ---------------------------------------------------------------------------

def ensure_gitignore(root: Path, dry_run: bool) -> None:
    path = root / ".gitignore"
    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="replace")
        if ".env" in existing and "__pycache__" in existing:
            log(".gitignore already present and sane — leaving untouched.")
            return
        if dry_run:
            log(f"[dry-run] Would append missing rules to {path}")
            return
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n" + GITIGNORE)
        log(f"Appended standard rules to existing {path}")
        return

    if dry_run:
        log(f"[dry-run] Would write {path}")
        return
    path.write_text(GITIGNORE, encoding="utf-8")
    log(f"Wrote {path}")


def ensure_readme(root: Path, dry_run: bool) -> None:
    path = root / "README.md"
    if path.exists() and path.stat().st_size > 200:
        log("README.md already present — leaving untouched.")
        return
    if dry_run:
        log(f"[dry-run] Would write {path}")
        return
    path.write_text(README, encoding="utf-8")
    log(f"Wrote {path}")


def init_git(root: Path, branch: str, dry_run: bool) -> None:
    if is_git_repo(root):
        log("Git repository already initialised.")
        return
    if dry_run:
        log(f"[dry-run] Would run: git init -b {branch}")
        return
    res = run(["git", "init", "-b", branch], cwd=root)
    if res.returncode != 0:
        # Older git versions lack -b
        run(["git", "init"], cwd=root)
        run(["git", "checkout", "-b", branch], cwd=root)
    log(f"Initialised git repository on branch '{branch}'.")


def configure_identity(root: Path, dry_run: bool) -> None:
    """Set a fallback identity only if none is configured."""
    name = run(["git", "config", "user.name"], cwd=root).stdout.strip()
    email = run(["git", "config", "user.email"], cwd=root).stdout.strip()
    if not name:
        if dry_run:
            log("[dry-run] Would set local user.name")
        else:
            run(["git", "config", "user.name", "JARVIS-OMEGA Bot"], cwd=root)
            log("Set local user.name to 'JARVIS-OMEGA Bot'.")
    if not email:
        if dry_run:
            log("[dry-run] Would set local user.email")
        else:
            run(["git", "config", "user.email", "jarvis-omega@localhost"], cwd=root)
            log("Set local user.email.")


def commit_all(root: Path, branch: str, dry_run: bool) -> None:
    run(["git", "add", "-A"], cwd=root)
    status = run(["git", "status", "--porcelain"], cwd=root).stdout.strip()
    if not status:
        log("Nothing to commit — working tree clean.")
        return
    if dry_run:
        log(f"[dry-run] Would commit {len(status.splitlines())} changed path(s).")
        return
    res = run(
        ["git", "commit", "-m", "feat: initial JARVIS-OMEGA multi-agent assistant"],
        cwd=root,
    )
    if res.returncode != 0:
        log(f"Commit failed:\n{res.stderr.strip()}")
        return
    log("Created initial commit.")


def remote_exists(root: Path, remote: str) -> bool:
    out = run(["git", "remote"], cwd=root).stdout
    return remote in out.split()


def deploy(root: Path, repo: str, user: str | None, private: bool,
           branch: str, dry_run: bool, push: bool) -> None:
    step("Preparing repository files")
    ensure_gitignore(root, dry_run)
    ensure_readme(root, dry_run)

    step("Initialising git")
    init_git(root, branch, dry_run)
    configure_identity(root, dry_run)

    step("Committing files")
    commit_all(root, branch, dry_run)

    step("Connecting to GitHub")
    if dry_run:
        log("[dry-run] Would create/push GitHub repository.")
        print_manual_instructions(repo, user, branch, root)
        return

    if not push:
        log("--no-push specified; stopping after local commit.")
        print_manual_instructions(repo, user, branch, root)
        return

    slug = f"{user}/{repo}" if user else repo

    if gh_available():
        # Authenticated GitHub CLI path.
        visibility = "--private" if private else "--public"
        log(f"Using GitHub CLI to create {slug} ({'private' if private else 'public'})…")

        create = run(
            ["gh", "repo", "create", slug, visibility, "--source", ".", "--remote", "origin"],
            cwd=root,
        )
        if create.returncode != 0:
            stderr = (create.stderr or "").strip()
            if "already exists" in stderr.lower():
                log("Repository already exists — setting remote manually.")
                if user:
                    url = f"https://github.com/{slug}.git"
                    if not remote_exists(root, "origin"):
                        run(["git", "remote", "add", "origin", url], cwd=root)
                    else:
                        run(["git", "remote", "set-url", "origin", url], cwd=root)
            else:
                log(f"gh repo create failed: {stderr}")
                print_manual_instructions(repo, user, branch, root)
                return
        else:
            log(f"Created repository {slug}.")

        push_res = run(["git", "push", "-u", "origin", branch], cwd=root)
        if push_res.returncode == 0:
            log(f"Pushed branch '{branch}' to {slug}.")
            print(f"\n✅ Done — https://github.com/{slug}")
            return
        log(f"Push failed:\n{(push_res.stderr or '').strip()}")
        print_manual_instructions(repo, user, branch, root)
        return

    log("GitHub CLI (`gh`) not found.")
    print_manual_instructions(repo, user, branch, root)


def print_manual_instructions(repo: str, user: str | None, branch: str, root: Path) -> None:
    slug = f"{user}/{repo}" if user else f"<your-username>/{repo}"
    print(dedent(f"""
    ┌──────────────────────────────────────────────────────────────────┐
    │  MANUAL PUSH INSTRUCTIONS                                        │
    └──────────────────────────────────────────────────────────────────┘

    1. Create an empty repository named '{repo}' on GitHub:
         https://github.com/new

    2. From   {root}
       run:

         git remote add origin https://github.com/{slug}.git
         git branch -M {branch}
         git push -u origin {branch}

    3. For future updates:

         git add -A
         git commit -m "update: <what changed>"
         git push

    Optional — install the GitHub CLI to automate this next time:
         Termux : pkg install gh
         Debian : sudo apt install gh
         macOS  : brew install gh
       then re-run this script.
    """))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy JARVIS-OMEGA to GitHub (git init + commit + push).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--repo", default=DEFAULT_REPO_NAME,
                        help=f"GitHub repository name (default: {DEFAULT_REPO_NAME})")
    parser.add_argument("--user", default=os.environ.get("GITHUB_USER"),
                        help="GitHub username (default: $GITHUB_USER)")
    parser.add_argument("--branch", default=DEFAULT_BRANCH,
                        help=f"Branch name (default: {DEFAULT_BRANCH})")
    parser.add_argument("--private", action="store_true", help="Create a private repo")
    parser.add_argument("--no-push", action="store_true", help="Commit locally, do not push")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without changing anything")
    parser.add_argument("--root", default=str(PROJECT_ROOT),
                        help="Project root to deploy (default: the jarvis/ directory)")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    print("=" * 68)
    print("  JARVIS-OMEGA :: GitHub deployment")
    print("=" * 68)
    print(f"  project root : {root}")
    print(f"  repository   : {args.user + '/' if args.user else ''}{args.repo}")
    print(f"  branch       : {args.branch}")
    print(f"  visibility   : {'private' if args.private else 'public'}")
    print(f"  mode         : {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 68)

    if not (root / "main.py").exists():
        print(f"\n❌ {root} does not look like the JARVIS project (main.py missing).")
        print("   Pass --root /path/to/jarvis if it lives elsewhere.")
        return 2

    if not git_available():
        print("\n❌ git is not installed.")
        print("   Termux : pkg install git")
        print("   Debian : sudo apt install git")
        return 2

    try:
        deploy(
            root=root,
            repo=args.repo,
            user=args.user,
            private=args.private,
            branch=args.branch,
            dry_run=args.dry_run,
            push=not args.no_push,
        )
    except KeyboardInterrupt:
        print("\nAborted by user.")
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Deployment error: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 18. `requirements.txt`

**Python dependencies** — 8 lines

```text
fastapi>=0.104.0
uvicorn>=0.24.0
websockets>=11.0
google-genai>=0.3.0
requests>=2.31.0
pydantic>=2.5.0
aiohttp>=3.9.0
python-multipart>=0.0.6
```

## 19. `README.md`

**Full project documentation** — 234 lines

```markdown
# JARVIS-OMEGA

> A zero-budget, multi-agent personal AI assistant with a futuristic sci-fi HUD.
> FastAPI + WebSockets + Google Gemini + SQLite. Runs on PC and Android Termux.

---

## Features

- **Multi-agent orchestration** — a master router dispatches work to four
  specialist agents (Coder, Research, System, Memory) based on intent confidence.
- **Real-time streaming** — every thought, tool call and result is pushed to the
  HUD over WebSockets as it happens.
- **Futuristic HUD** — glassmorphism panels, neon cyan accents, live execution
  trace, markdown + syntax-highlighted code, voice input via Web Speech API.
- **Secure sandbox** — shell execution is blocklisted, time-limited and
  output-capped; file operations are confined to the workspace.
- **Persistent memory** — SQLite-backed conversation history, long-term memory
  and task audit logs.
- **Offline fallback** — runs without any API key in heuristic mode; add a free
  Gemini key for full reasoning.
- **One-command GitHub deploy** — `scripts/deploy_github.py` bootstraps git,
  `.gitignore`, README, commit and push.

---

## Architecture

```
Browser HUD (index.html/style.css/script.js)
        │  WebSocket /ws/chat
        ▼
main.py  (FastAPI + CORS + static mount)
        │
        ▼
core/orchestrator.py  ── intent routing + event streaming
        │
        ├── agents/coder_agent.py      code generation / safe execution
        ├── agents/research_agent.py   web search + summarisation
        ├── agents/system_agent.py     diagnostics / sandboxed commands
        └── agents/memory_agent.py     store & recall persistent memory
                 │
                 ├── tools/shell_tool.py       sandboxed subprocess runner
                 ├── tools/web_search_tool.py  DuckDuckGo / Bing scraping
                 ├── tools/file_manager.py     workspace-scoped file ops
                 ├── core/llm.py               Gemini + offline fallback
                 └── database.py               SQLite persistence
```

---

## Installation — Desktop / Server

```bash
git clone <your-repo-url> jarvis-omega
cd jarvis-omega/jarvis

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export GEMINI_API_KEY="your-free-key"   # optional but recommended
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open <http://localhost:8000>.

Get a free API key at <https://aistudio.google.com/apikey>.

---

## Installation — Android (Termux)

```bash
pkg update && pkg upgrade -y
pkg install -y python git rust binutils libffi openssl

git clone <your-repo-url> ~/jarvis-omega
cd ~/jarvis-omega/jarvis

pip install -r requirements.txt

export GEMINI_API_KEY="your-free-key"
uvicorn main:app --host 0.0.0.0 --port 8080
```

Open <http://localhost:8080> in your phone browser.

**Termux tips**

- Long builds can be killed in the background: run `termux-wake-lock` first, and
  disable battery optimisation for Termux in Android settings.
- If `pip install` fails on a package, retry with `pkg install python-numpy` or
  build tools: `pkg install build-essential cmake`.
- To reach the HUD from another device on the same network, use the phone's
  `ip addr show wlan0` address with port 8080.

---

## Configuration

Environment variables (or a `.env` file in `jarvis/` — see `.env.example`).
Shell exports always take precedence over the file:

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key — enables full reasoning |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Model ID |
| `GEMINI_TEMPERATURE` | `0.7` | Sampling temperature |
| `GEMINI_MAX_TOKENS` | `2048` | Max output tokens |
| `JARVIS_HOST` | `0.0.0.0` | Bind address |
| `JARVIS_PORT` | `8000` | Bind port |
| `JARVIS_CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `JARVIS_WORKSPACE` | `jarvis/workspace` | Directory agents may read/write and run commands in |
| `JARVIS_SHELL_TIMEOUT` | `30` | Shell command timeout (seconds) |
| `JARVIS_SHELL_MAX_OUTPUT` | `65536` | Max captured output bytes |

---

## Usage

Type a command, or use a quick-action chip:

| You say | Agent | What happens |
|---|---|---|
| `system status` | System | OS, CPU, memory, disk, network snapshot |
| `list files in .` | System | Workspace directory listing |
| `search for FastAPI best practices` | Research | Live web search + summarised answer with sources |
| `write a python script that prints fibonacci to fib.py` | Coder | Generates and writes the file |
| `run fib.py` | Coder | Executes it in the sandbox and returns output |
| `remember my project is JARVIS as project` | Memory | Stores a long-term memory record |
| `recall project` | Memory | Retrieves it |

### HUD keyboard shortcuts

- `/` — focus the command input
- `Enter` — transmit
- `Esc` — clear input

---

## Security model

- **Command blocklist** — destructive patterns (`rm -rf /`, fork bombs, `mkfs`,
  `dd if=`, disk writes, shutdown/reboot) are rejected before execution.
- **Binary allowlist check** — blocked binaries never run; unknown binaries are
  refused if not found in `PATH`.
- **Hard timeout** — every command is killed after `JARVIS_SHELL_TIMEOUT`.
- **Output cap** — stdout/stderr are truncated to prevent memory blowups.
- **Workspace confinement** — the file manager refuses any path that resolves
  outside the configured workspace (`jarvis/workspace/` by default, or
  `JARVIS_WORKSPACE`). Point it at your code directory only if you want agents
  editing real source.
- **No secrets in git** — `.gitignore` excludes `.env`, keys and databases.

> This is a *convenience* sandbox for a personal assistant, not a security
> boundary against hostile input. Do not expose the server to the public
> internet without authentication and additional hardening.

---

## GitHub deployment

```bash
cd jarvis
python scripts/deploy_github.py --repo jarvis-omega --user <your-github-username>
```

The script initialises git, writes `.gitignore` + `README.md`, commits, then
either creates and pushes the repo with the GitHub CLI (`gh`) or prints the
exact commands for you to run.

Options:

```bash
python scripts/deploy_github.py --private     # private repo
python scripts/deploy_github.py --no-push     # commit locally only
python scripts/deploy_github.py --dry-run     # show actions, change nothing
```

---

## Project layout

```
jarvis/
├── main.py                  FastAPI app, WebSocket endpoint, static mount
├── config.py                env vars, paths, security policy
├── database.py              SQLite: chat, memory, task logs
├── requirements.txt
├── core/
│   ├── base_agent.py        abstract agent + event/context dataclasses
│   ├── llm.py               Gemini client + offline fallback
│   └── orchestrator.py      router + streaming execution loop
├── agents/
│   ├── coder_agent.py
│   ├── research_agent.py
│   ├── system_agent.py
│   └── memory_agent.py
├── tools/
│   ├── shell_tool.py        sandboxed subprocess execution
│   ├── web_search_tool.py   DuckDuckGo/Bing aggregation
│   └── file_manager.py      workspace-scoped file ops
├── static/
│   ├── index.html           HUD structure
│   ├── style.css            sci-fi styling
│   └── script.js            WebSocket client + renderer + voice
├── scripts/
│   └── deploy_github.py     automated git/GitHub deployment
├── workspace/               default agent sandbox (gitignored, seeded with a README)
└── data/                    SQLite DB + logs (gitignored)
```

---

## Troubleshooting

**`ModuleNotFoundError: config`** — run from inside `jarvis/` (`uvicorn main:app`)
or from the repo root (`uvicorn jarvis.main:app`). Both are supported.

**HUD shows `OFFLINE AI`** — no `GEMINI_API_KEY` is set. The assistant still
works in heuristic mode; export the key and restart for full reasoning.

**`LINK LOST` in the top bar** — the WebSocket dropped. The client retries
automatically; check that the server is running and the port matches.

**Voice button disabled** — the Web Speech API needs Chrome/Edge/Safari and a
secure context (`localhost` or HTTPS).

---

## License

MIT — use it, fork it, build on it.
```

## 20. `.env.example`

**Environment variable template** — 26 lines

```text
# ---------------------------------------------------------------------------
# JARVIS-OMEGA configuration — copy to .env and fill in
# ---------------------------------------------------------------------------

# Google Gemini (free tier): https://aistudio.google.com/apikey
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
GEMINI_TEMPERATURE=0.7
GEMINI_MAX_TOKENS=2048

# Server
JARVIS_HOST=0.0.0.0
JARVIS_PORT=8000
JARVIS_DEBUG=false
# Comma-separated origins; "*" allows all (credentials then disabled)
JARVIS_CORS_ORIGINS=*

# Sandbox
# Directory agents may read/write; defaults to the project root
JARVIS_WORKSPACE=
JARVIS_SHELL_TIMEOUT=30
JARVIS_SHELL_MAX_OUTPUT=65536

# Optional local AI hook (Ollama / llama.cpp) — leave blank to disable
LOCAL_AI_BASE_URL=
LOCAL_AI_MODEL=
```

## 21. `.gitignore`

**Git ignore rules** — 27 lines

```text
# Secrets
.env
.env.*
*.env
!.env.example

# Python
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/

# Runtime data
data/
workspace/*
!workspace/README.md
*.db
*.db-wal
*.db-shm
*.log

# Editors / OS
.vscode/
.idea/
.DS_Store
Thumbs.db
```

## 22. `workspace/README.md`

**Agent sandbox directory note** — 9 lines

```markdown
# Agent Workspace

This directory is the default sandbox for JARVIS-OMEGA agents.

- Files written by the **Coder** agent land here.
- **System** agent commands run with this as their working directory.
- The **File Manager** refuses any path that resolves outside this root.

Change the sandbox location with the `JARVIS_WORKSPACE` environment variable.
```

---

## Required package markers

These five files are **empty** but must exist so the imports resolve.
Create them with `touch`:

```bash
touch core/__init__.py agents/__init__.py tools/__init__.py \
      static/__init__.py scripts/__init__.py
```

---

## Directory tree

```text
jarvis/
├── main.py
├── config.py
├── database.py
└── base_agent.py
└── llm.py
└── orchestrator.py
└── coder_agent.py
└── research_agent.py
└── system_agent.py
└── memory_agent.py
└── shell_tool.py
└── web_search_tool.py
└── file_manager.py
└── index.html
└── style.css
└── script.js
└── deploy_github.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
└── README.md
```
