"""
jarvis/core/orchestrator.py
---------------------------
Multi-agent orchestration engine for JARVIS-OMEGA.

Registers sub-agents, routes user intent to the highest-confidence agent,
executes the agent while streaming real-time events (thoughts, tool calls,
tool results, final answer), and persists conversation + task logs to SQLite.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator, Optional

from core.base_agent import AgentContext, AgentEvent, AgentResult
from core.llm import llm
from agents.coder_agent import CoderAgent
from agents.memory_agent import MemoryAgent
from agents.research_agent import ResearchAgent
from agents.system_agent import SystemAgent
from database import JarvisDatabase


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class Orchestrator:
    """Routes requests to specialist agents and streams their work."""

    def __init__(self, db: Optional[JarvisDatabase] = None):
        self.db = db or JarvisDatabase()
        self.agents = [
            CoderAgent(),
            ResearchAgent(),
            SystemAgent(),
            MemoryAgent(db=self.db),
        ]

    # ------------------------------------------------------------------ #
    # Routing
    # ------------------------------------------------------------------ #
    def route(self, user_input: str) -> tuple[Optional[object], float]:
        """Return (agent, confidence) for the best-matching agent."""
        best_agent = None
        best_conf = 0.0
        for agent in self.agents:
            conf = agent.can_handle(user_input)
            if conf > best_conf:
                best_conf = conf
                best_agent = agent
        if best_conf <= 0.1:
            return None, best_conf
        return best_agent, best_conf

    # ------------------------------------------------------------------ #
    # Main execution loop — a SYNC generator of event dicts.
    # The WebSocket layer pumps this from a worker thread.
    # ------------------------------------------------------------------ #
    def process(self, session_id: str, user_input: str) -> Iterator[dict]:
        self.db.add_message(session_id, "user", user_input)

        history = self.db.get_recent_messages(session_id, limit=20)
        memory_hits = self.db.search_memory(user_input, limit=5)

        context = AgentContext(
            user_input=user_input,
            session_id=session_id,
            history=history,
            memory=memory_hits,
        )

        agent, confidence = self.route(user_input)

        yield {
            "type": "route",
            "agent": agent.name if agent else "Router",
            "message": (
                f"Routed to {agent.name} agent (confidence {confidence:.0%})"
                if agent else
                "No specialist matched — engaging general responder."
            ),
            "payload": {"confidence": round(confidence, 2)},
            "timestamp": _ts(),
        }

        if agent is None:
            yield from self._general_response(session_id, context)
            return

        # Buffer agent events so we can stream them in order while still
        # getting the AgentResult at the end. Agents are synchronous.
        collected: list[dict] = []

        def _emit(event: AgentEvent) -> None:
            collected.append(event.to_dict())

        try:
            result: AgentResult = agent.process(context, _emit)
        except Exception as exc:  # noqa: BLE001
            err = {
                "type": "error",
                "agent": agent.name,
                "message": f"{agent.name} agent failed: {exc}",
                "payload": {"error": str(exc)},
                "timestamp": _ts(),
            }
            collected.append(err)
            result = AgentResult(agent.name, False, f"{agent.name} agent failed: {exc}")

        for ev in collected:
            yield ev

        yield {
            "type": "final",
            "agent": result.agent,
            "message": result.content,
            "payload": result.data or {},
            "success": result.success,
            "timestamp": _ts(),
        }

        try:
            self.db.add_message(session_id, "assistant", result.content, agent=result.agent)
            self.db.log_task(
                session_id=session_id,
                agent=result.agent,
                status="ok" if result.success else "error",
                input_payload=user_input[:2000],
                output_payload=result.content[:2000],
            )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # General responder (no agent matched)
    # ------------------------------------------------------------------ #
    def _general_response(self, session_id: str, context: AgentContext) -> Iterator[dict]:
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in context.history[-8:]
        ) or "(new session)"
        memory_text = "\n".join(
            f"{m['key']}: {m['value']}" for m in context.memory[:3]
        ) or "(none)"

        system_prompt = (
            "You are JARVIS-OMEGA, a helpful personal AI assistant. "
            "Answer concisely and helpfully. Use markdown with fenced code blocks "
            "when showing code."
        )
        prompt = (
            f"Recent conversation:\n{history_text}\n\n"
            f"Relevant long-term memory:\n{memory_text}\n\n"
            f"User: {context.user_input}\n\nAssistant:"
        )

        yield {
            "type": "thought",
            "agent": "Router",
            "message": "Consulting general reasoning model...",
            "payload": {},
            "timestamp": _ts(),
        }

        full = llm.generate(prompt, system_prompt=system_prompt)

        yield {
            "type": "final",
            "agent": "Router",
            "message": full,
            "payload": {},
            "success": True,
            "timestamp": _ts(),
        }

        try:
            self.db.add_message(session_id, "assistant", full, agent="Router")
            self.db.log_task(session_id=session_id, agent="Router", status="ok",
                             input_payload=context.user_input[:2000],
                             output_payload=full[:2000])
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # Introspection helpers (used by the HUD status panel)
    # ------------------------------------------------------------------ #
    def agent_roster(self) -> list[dict]:
        return [
            {"name": a.name, "description": a.description, "handles": a.handles}
            for a in self.agents
        ]
