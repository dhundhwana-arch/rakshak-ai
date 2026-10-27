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
