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
