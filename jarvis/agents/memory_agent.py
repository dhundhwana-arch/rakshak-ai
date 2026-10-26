"""
jarvis/agents/memory_agent.py
-----------------------------
Memory & Context Agent: short-term working memory and long-term persistent
memory using SQLite with simple semantic (keyword) retrieval.
"""

from __future__ import annotations

import re

from core.base_agent import AgentContext, AgentEvent, AgentResult, BaseAgent
from core.llm import llm
from database import JarvisDatabase


class MemoryAgent(BaseAgent):
    def __init__(self, db: JarvisDatabase | None = None):
        super().__init__(
            name="Memory",
            description="Stores and recalls persistent memory using SQLite.",
            handles=["remember", "recall", "memory", "store", "note", "forget",
                     "remind me", "saved"],
        )
        self.db = db or JarvisDatabase()

    def can_handle(self, user_input: str) -> float:
        score = super().can_handle(user_input)
        lowered = user_input.lower()

        # "what is <key>" should hit Memory (not Research) if we already know it.
        probe = re.sub(
            r"^\s*(?:what is|what's|recall|show memory|search memory|do you remember)\s+",
            "", user_input, flags=re.IGNORECASE,
        ).strip().rstrip("?")

        if probe:
            try:
                if self.db.get_memory(probe):
                    return 0.95
                # Partial match still signals memory intent.
                if self.db.search_memory(probe, limit=1):
                    return 0.80
            except Exception:  # noqa: BLE001
                pass

        if any(w in lowered for w in ("remember", "recall", "memory", "store", "note",
                                      "forget", "saved", "remind me")):
            score = max(score, 0.75)
        return min(1.0, score)

    def process(self, context: AgentContext, emit) -> AgentResult:
        events_list: list[AgentEvent] = [
            AgentEvent("thought", self.name,
                       "Determining memory operation (store, recall, search, or forget).",
                       {"input": context.user_input})
        ]

        user_input = context.user_input
        lowered = user_input.lower()

        # STORE: "remember that X" / "store X as Y"
        store_match = re.match(r"\s*(?:remember|store|note)\s+(.+?)\s+(?:as|under)\s+(.+)\s*$",
                               user_input, flags=re.DOTALL | re.IGNORECASE)
        if store_match:
            value = store_match.group(1).strip()
            key = store_match.group(2).strip()
            self.db.upsert_memory(key, value, tags="user-stored")
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Storing memory: {key} = {value}",
                                          {"key": key, "value": value}))
            events_list.append(AgentEvent("tool_result", self.name,
                                          "Memory stored.",
                                          {"key": key}))
            final = f"Remembered: `{key}` = {value}"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, True, final, events=events_list)

        # SIMPLE STORE: "remember X"
        simple_store = re.match(r"\s*remember\s+(.+)\s*$",
                                user_input, flags=re.DOTALL | re.IGNORECASE)
        if simple_store and not any(w in lowered for w in ("recall", "what", "show")):
            value = simple_store.group(1).strip()
            key = value[:40]
            self.db.upsert_memory(key, value, tags="user-stored")
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Storing memory: {key}",
                                          {"key": key, "value": value}))
            final = f"Remembered: `{key}` = {value}"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, True, final, events=events_list)

        # FORGET: "forget X"
        forget_match = re.match(r"\s*forget\s+(.+)\s*$",
                                user_input, flags=re.DOTALL | re.IGNORECASE)
        if forget_match:
            key = forget_match.group(1).strip()
            # We don't have delete exposed; mark as forgotten by overwriting.
            self.db.upsert_memory(key, "[FORGOTTEN]", tags="forgotten")
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Forgetting memory: {key}",
                                          {"key": key}))
            final = f"Forgotten: `{key}`"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, True, final, events=events_list)

        # RECALL/SEARCH: "recall X" / "what is X" / "search memory X"
        recall_match = re.match(r"\s*(?:recall|what is|show memory|search memory)\s+(.+)\s*$",
                                user_input, flags=re.DOTALL | re.IGNORECASE)
        query = recall_match.group(1).strip() if recall_match else user_input

        exact = self.db.get_memory(query)
        if exact:
            events_list.append(AgentEvent("tool_call", self.name,
                                          f"Recalling exact memory: {query}",
                                          {"key": query}))
            final = f"From memory — `{query}`: {exact}"
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, True, final, events=events_list)

        hits = self.db.search_memory(query, limit=5)
        events_list.append(AgentEvent("tool_call", self.name,
                                      f"Searching memory for: {query}",
                                      {"query": query, "hits": len(hits)}))
        if hits:
            lines = [f"Memory matches for '{query}':"]
            for h in hits:
                lines.append(f"• {h['key']}: {h['value'][:200]}{'...' if len(h['value']) > 200 else ''}")
            final = "\n".join(lines)
        else:
            final = f"No memory found for '{query}'. Try 'remember <something> as <key>' to store it."
        events_list.append(AgentEvent("final", self.name, final))
        return AgentResult(self.name, True, final, events=events_list,
                           data={"query": query, "hits": hits})
