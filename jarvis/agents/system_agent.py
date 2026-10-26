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
