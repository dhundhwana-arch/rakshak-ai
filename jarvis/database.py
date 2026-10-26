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
