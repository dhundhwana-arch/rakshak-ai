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
