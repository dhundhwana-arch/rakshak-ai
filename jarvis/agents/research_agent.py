"""
jarvis/agents/research_agent.py
-------------------------------
Research & Web Intelligence Agent: smart web searches, documentation
aggregation, article summarization, and live data via free scrapers/APIs.
"""

from __future__ import annotations

from core.base_agent import AgentContext, AgentEvent, AgentResult, BaseAgent
from core.llm import llm
from tools.web_search_tool import WebSearchTool, search_web


class ResearchAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Research",
            description="Executes web searches, aggregates documentation, and summarizes live data.",
            handles=["search", "web", "research", "lookup", "find", "what is",
                     "who is", "latest", "news", "documentation", "browse"],
        )
        self.search_tool = WebSearchTool()

    def can_handle(self, user_input: str) -> float:
        score = super().can_handle(user_input)
        lowered = user_input.lower()
        question_starts = ("what ", "who ", "where ", "when ", "why ", "how ",
                           "tell me about", "search for", "look up")
        if any(lowered.startswith(w) for w in question_starts):
            score = max(score, 0.55)
        return min(1.0, score)

    def process(self, context: AgentContext, emit) -> AgentResult:
        events_list: list[AgentEvent] = [
            AgentEvent("thought", self.name,
                       "Planning web research for the user query.",
                       {"query": context.user_input})
        ]

        query = context.user_input
        # Strip obvious assistant prefixes.
        for prefix in ("search for ", "look up ", "research ", "find "):
            if query.lower().startswith(prefix):
                query = query[len(prefix):].strip()
                break

        events_list.append(AgentEvent("tool_call", self.name,
                                      f"Searching the web: {query}",
                                      {"query": query}))
        results = self.search_tool.search(query, max_results=6)
        events_list.append(AgentEvent("tool_result", self.name,
                                      f"Found {len(results)} results",
                                      {"count": len(results)}))

        if not results:
            final = ("I couldn't find any web results for that query. "
                     "Try rephrasing, or check your internet connection.")
            events_list.append(AgentEvent("final", self.name, final))
            return AgentResult(self.name, False, final, events=events_list)

        # Build an LLM-ready summary from search results.
        context_block = self.search_tool.format_for_llm(results)
        summary_prompt = (
            f"User asked: {context.user_input}\n\n"
            f"Search results:\n{context_block}\n\n"
            "Write a concise, well-structured answer using only the search results "
            "above. Cite sources by title and URL. If the results don't answer the "
            "question, say so clearly."
        )
        answer = llm.generate(summary_prompt, temperature=0.5)

        final_lines = [answer, "", "---", "Sources:"]
        for i, r in enumerate(results, 1):
            final_lines.append(f"{i}. {r.title} — {r.url}")
        final = "\n".join(final_lines)

        events_list.append(AgentEvent("final", self.name, final))
        return AgentResult(self.name, True, final, events=events_list,
                           data={"query": query, "results": [r.__dict__ for r in results]})


def search_web_convenience(query: str, max_results: int = 5) -> str:
    return search_web(query, max_results=max_results)
