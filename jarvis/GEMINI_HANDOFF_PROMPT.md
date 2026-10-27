# Gemini Handoff Prompt — JARVIS-OMEGA

Copy everything in the **Prompt** section below, paste it into
[gemini.google.com](https://gemini.google.com), then attach
`JARVIS_OMEGA_ALL_CODE.md` (or `JARVIS_OMEGA.tar.gz`).

The bundle is ~173 KB ≈ **43k tokens** — well inside Gemini's 1M-token
context window, so the whole codebase fits in a single message.

---

## Prompt

```text
You are a principal AI systems architect and senior Python engineer.
I'm attaching the complete source of JARVIS-OMEGA, a zero-budget,
multi-agent personal AI assistant built with FastAPI, WebSockets,
Google GenAI (Gemini), and SQLite.

Architecture:
- main.py           FastAPI app, /ws/chat WebSocket, static HUD mount
- config.py         env/.env loader, paths, API keys, security policy
- database.py       SQLite: chat_history, memory, task_logs (WAL mode)
- core/base_agent.py    abstract BaseAgent + AgentEvent/Context/Result
- core/llm.py           Gemini client with offline heuristic fallback
- core/orchestrator.py  confidence-based router + streaming loop
- agents/           coder, research, system, memory (one file each)
- tools/            shell_tool (sandboxed), web_search_tool, file_manager
- static/           index.html, style.css, script.js (sci-fi HUD)
- scripts/deploy_github.py   automated git init/commit/push

Design constraints I care about:
1. Zero budget — free tiers and local execution only.
2. Must run on both desktop and Android Termux (no heavy native deps).
3. Works with NO API key (offline heuristic mode), and better with one.
4. Shell execution is sandboxed: blocklist + timeout + output caps.
5. File ops confined to a workspace dir (no path traversal).
6. Real-time streaming: every thought/tool call reaches the HUD.

Please read the whole codebase first, then do the following:

[ PICK ONE OR MORE — delete the rest ]

A. CODE REVIEW
   Identify real bugs, race conditions, and security gaps. For each:
   file, line, why it's wrong, and the concrete fix. Rank by severity.
   Be specific — no generic advice.

B. SECURITY AUDIT
   The shell sandbox is a convenience guard, not a security boundary.
   Show me exactly how it can be bypassed (give working examples),
   then propose a hardened design (allowlist? container? both?).

C. AGENT QUALITY
   The router uses keyword-confidence scoring in BaseAgent.can_handle().
   Evaluate the trade-offs vs. LLM-based intent classification.
   Propose a hybrid that stays free but routes more accurately.

D. FEATURE EXTENSION
   Design and write the code to add: [describe your feature].
   Match the existing code style, keep it modular, no new heavy deps.

E. TERMUX COMPATIBILITY
   Flag anything that will break on Android/Termux (aarch64, no glibc
   assumptions, pip wheels that need compiling) and give workarounds.

Output format: markdown, code in fenced blocks with filenames.
If something in my constraints is a bad idea, say so directly.
```

---

## Tips

- **Attach the file** rather than pasting 173 KB as text — cleaner and
  faster. `.md` and `.zip` both work; if you use the tarball, note that
  Gemini may not extract `.tar.gz`, so prefer the `.md` or re-zip as `.zip`.
- **One task per message.** Asking for A+B+C+E at once produces shallow
  output. Start with B (security), then A.
- **Ask it to cite line numbers.** It makes the review verifiable instead
  of plausible-sounding.
- **Verify before acting.** Gemini can be confidently wrong about code it
  only skimmed. Spot-check any claimed bug against the actual file.

---

## Where the files live

| Artifact | Location |
|---|---|
| All source, one document | `jarvis/JARVIS_OMEGA_ALL_CODE.md` |
| Raw GitHub link | `https://raw.githubusercontent.com/dhundhwana-arch/rakshak-ai/arena/0974a75f-rakshak-ai/jarvis/JARVIS_OMEGA_ALL_CODE.md` |
| Branch | `arena/0974a75f-rakshak-ai` (commit `86a2982`) |
| Live archive | `/home/user/JARVIS_OMEGA.tar.gz` (86 KB) |
