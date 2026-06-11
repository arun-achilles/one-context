"""
Retrieves relevant chunks and team memories from the knowledge base.
Also does live Jira/Confluence lookups when specific keys are mentioned.
Sets needs_clarification=True if top result score is below threshold.
"""
import re
from agent.state import AgentState
from agent.tools.search_knowledge import search_knowledge, CONFIDENCE_THRESHOLD
from agent.tools.memory_tool import search_memory

# Matches Jira keys like CL-1524, OC-002, PROJ-99
_JIRA_KEY_RE = re.compile(r'\b([A-Z][A-Z0-9]+-\d+)\b')


def _fetch_live_jira(query: str) -> list[dict]:
    """Fetch any explicitly mentioned Jira keys directly from the API."""
    keys = _JIRA_KEY_RE.findall(query)
    if not keys:
        return []
    from agent.tools.jira_tools import get_jira_issue
    live = []
    for key in dict.fromkeys(keys):  # deduplicate, preserve order
        try:
            issue = get_jira_issue(key)
            live.append({
                "content": (
                    f"[Live Jira] {issue['key']}: {issue['summary']}\n"
                    f"Status: {issue['status']}  |  Type: {issue['issue_type']}  |  Assignee: {issue['assignee']}\n"
                    f"{issue['description'][:600]}"
                ),
                "url": issue["url"],
                "content_type": "jira_issue",
                "tags": issue.get("labels", []),
                "score": 1.0,  # live data — always authoritative
                "high_confidence": True,
                "jira_key": key,
                "jira_url": issue["url"],
                "jira_summary": issue["summary"],
            })
        except Exception:
            pass  # key not found or Jira unreachable — fall through to vector search
    return live


def _fetch_live_jira_search(query: str, intent: str) -> list[dict]:
    """Call Jira text search for pipeline queries or as a fallback for low-confidence qa."""
    from agent.tools.jira_tools import search_jira
    try:
        results = search_jira(query, max_results=5)
        return [
            {
                "content": f"[Live Jira search] {r['key']}: {r['summary']} ({r['status']})",
                "url": r["url"],
                "content_type": "jira_issue",
                "tags": [],
                "score": 0.7,
            }
            for r in results
        ]
    except Exception:
        return []


def _fetch_live_confluence_search(query: str) -> list[dict]:
    """Call Confluence text search as fallback for low-confidence qa."""
    from agent.tools.confluence_tools import search_confluence
    try:
        results = search_confluence(query, max_results=3)
        return [
            {
                "content": f"[Live Confluence] {r['title']}\n{r['excerpt']}",
                "url": r["url"],
                "content_type": "confluence_page",
                "tags": [],
                "score": 0.65,
            }
            for r in results
        ]
    except Exception:
        return []


def retriever_node(state: AgentState) -> AgentState:
    query = state["messages"][-1].content
    intent = state.get("intent", "qa")

    # 1. Live Jira key lookups — explicitly mentioned tickets always resolve first
    live_chunks = _fetch_live_jira(query)

    # 2. Vector search + team memory
    chunks = search_knowledge(query)
    memories = search_memory(query, top_k=2)

    memory_chunks = [
        {
            "content": f"[Team memory] {m['content']}"
                       + (f" — {m['context']}" if m.get("context") else ""),
            "url": "",
            "content_type": "team_memory",
            "tags": m.get("tags", []),
            "score": m["score"],
            "high_confidence": m["score"] >= CONFIDENCE_THRESHOLD,
        }
        for m in memories
        if m["score"] >= CONFIDENCE_THRESHOLD
    ]

    all_chunks = live_chunks + memory_chunks + chunks
    top_score = all_chunks[0]["score"] if all_chunks else 0

    # 3. Supplement with live API search when confidence is low or intent demands live data
    if intent == "pipeline_query":
        # Always fetch live sprint/ticket data for pipeline questions
        all_chunks = all_chunks + _fetch_live_jira_search(query, intent)
    elif top_score < CONFIDENCE_THRESHOLD and not live_chunks:
        # Low vector confidence + no explicit Jira key → try live search fallback
        all_chunks = all_chunks + _fetch_live_jira_search(query, intent) + _fetch_live_confluence_search(query)

    needs_clarification = (not live_chunks) and (top_score < CONFIDENCE_THRESHOLD) and (not all_chunks)

    return {
        **state,
        "retrieved_chunks": all_chunks,
        "needs_clarification": needs_clarification,
    }
