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
