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

    # Build display text:
    # 1. Strip the hidden PENDING_ACTION marker (kept in AIMessage for act node)
    # 2. Replace inline [Sx] citation labels with clean superscript-style markers
    display = _MARKER_RE.sub("", answer).rstrip()
    # Convert [S1], [S2] → ¹, ² etc. for cleaner chat display
    def _to_superscript(m: re.Match) -> str:
        n = int(m.group(1))
        supers = "⁰¹²³⁴⁵⁶⁷⁸⁹"
        return "".join(supers[int(d)] for d in str(n))
    display = re.sub(r"\[S(\d+)\]", _to_superscript, display)

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
