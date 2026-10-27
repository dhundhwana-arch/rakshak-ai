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
