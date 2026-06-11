"""
Formats the final response with citations appended.
Preserves PENDING_ACTION markers for the act node but strips them from display.
"""
import re
from langchain_core.messages import AIMessage
from agent.state import AgentState

_MARKER_RE = re.compile(r"\n*<!-- PENDING_ACTION: .+? -->", re.DOTALL)


def responder_node(state: AgentState) -> AgentState:
    answer = state.get("answer", "I could not find an answer.")
    citations = state.get("citations", [])

    # Build display text — strip the hidden marker but keep the marker in the
    # AIMessage so the act node can find it on the next turn
    display = _MARKER_RE.sub("", answer).rstrip()

    if citations and not state.get("needs_clarification"):
        unique_urls = list(dict.fromkeys(c["url"] for c in citations if c.get("url")))
        sources = "\n".join(f"- {url}" for url in unique_urls[:5])
        display = f"{display}\n\n**Sources**\n{sources}"

    # Store full answer (with marker) in message history for the act node
    return {
        **state,
        "messages": [AIMessage(content=answer)],   # full, with marker
        "answer": display,                          # display copy, clean
    }
