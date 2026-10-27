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
