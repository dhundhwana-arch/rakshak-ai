"""
jarvis/core/base_agent.py
-------------------------
Abstract base class for every JARVIS-OMEGA sub-agent.

Agents are the workers of the multi-agent orchestration engine. Each agent
declares a name, a human-readable description, and the keywords/intents it
handles. The `process` method receives a structured context and returns a
result dict plus an optional list of events for real-time WebSocket streaming.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentEvent:
    """A single streaming event emitted during agent execution."""
    type: str                      # 'thought' | 'tool_call' | 'tool_result' | 'final' | 'error'
    agent: str
    message: str
    payload: Optional[dict] = None
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "agent": self.agent,
            "message": self.message,
            "payload": self.payload or {},
            "timestamp": self.timestamp,
        }


@dataclass
class AgentContext:
    """Input context passed to every agent."""
    user_input: str
    session_id: str
    history: list[dict] = field(default_factory=list)
    memory: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    """Output of an agent run."""
    agent: str
    success: bool
    content: str
    events: list[AgentEvent] = field(default_factory=list)
    data: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base class. Subclasses must implement `name`, `description`,
    `handles`, and `process`."""

    def __init__(self, name: str, description: str, handles: list[str]):
        self.name = name
        self.description = description
        self.handles = handles  # keywords/intents this agent responds to

    @abstractmethod
    def process(self, context: AgentContext, emit: Callable[[AgentEvent], None]) -> AgentResult:
        """Execute the agent's work, streaming progress via `emit`."""
        ...

    def can_handle(self, user_input: str) -> float:
        """Return a confidence score (0.0-1.0) for whether this agent handles the input.

        Base implementation counts keyword hits and maps them to a confidence:
        one hit is already a meaningful signal (0.40), each extra hit adds 0.20.
        Subclasses override this to add intent-specific boosts."""
        if not self.handles or not user_input:
            return 0.0
        lowered = user_input.lower()
        hits = sum(1 for kw in self.handles if kw.lower() in lowered)
        if hits == 0:
            return 0.0
        return min(1.0, 0.40 + 0.20 * (hits - 1))

    def _emit(self, emit: Callable[[AgentEvent], None], etype: str, message: str, payload: Optional[dict] = None) -> None:
        emit(AgentEvent(type=etype, agent=self.name, message=message, payload=payload))
