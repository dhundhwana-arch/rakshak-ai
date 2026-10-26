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
