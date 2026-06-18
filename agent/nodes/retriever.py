"""
Retrieves relevant chunks and team memories from the knowledge base.
Also does live Jira/Confluence lookups when specific keys are mentioned.
Sets needs_clarification=True if top result score is below threshold.
"""
import re
from agent.state import AgentState
from agent.model_policy import call_model
from agent.tools.search_knowledge import search_knowledge, CONFIDENCE_THRESHOLD
from agent.tools.memory_tool import search_memory
from agent.tools.feature_tools import get_feature_retrieval_chunks

# Matches Jira keys like CL-1524, OC-002, PROJ-99
_JIRA_KEY_RE = re.compile(r'\b([A-Z][A-Z0-9]+-\d+)\b')
_ACK_RE = re.compile(
    r"^\s*(yes|yeah|yep|sure|ok|okay|go ahead|do it|please|sounds good|that works)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_CONTEXTUAL_RE = re.compile(
    r"\b(it|that|this|those|these|they|them|same|above|earlier|previous|again|also)\b",
    re.IGNORECASE,
)


def _msg_content(msg) -> str:
    """Extract plain text from a LangChain message-like object."""
    # Anthropic content blocks often expose a direct .text property.
    text_attr = getattr(msg, "text", None)
    if isinstance(text_attr, str):
        return text_attr

    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(p for p in parts if p)
    return str(content or "")


def _is_human_message(msg) -> bool:
    """Best-effort check for a human/user message across message classes."""
    t = (getattr(msg, "type", "") or "").lower()
    cls = msg.__class__.__name__.lower()
    return t in ("human", "user") or "human" in cls


def _is_ai_message(msg) -> bool:
    """Best-effort check for an assistant message across message classes."""
    t = (getattr(msg, "type", "") or "").lower()
    cls = msg.__class__.__name__.lower()
    return t in ("ai", "assistant") or "ai" in cls or "assistant" in cls


def _build_standalone_query(messages: list) -> str:
    """
    Build a retrieval-focused standalone query from the latest user turn plus
    short conversational context (recent user turns + compressed summary).
    """
    if not messages:
        return ""

    latest = _msg_content(messages[-1]).strip()
    if not latest:
        return ""

    summary = ""
    prior_assistant_turn = ""
    prior_user_turns = []
    for msg in reversed(messages[:-1]):
        text = _msg_content(msg).strip()
        if not text:
            continue
        if not summary and text.startswith("[EARLIER CONVERSATION SUMMARY]"):
            summary = text.replace("[EARLIER CONVERSATION SUMMARY]", "", 1).strip()
            continue
        if _is_human_message(msg):
            prior_user_turns.append(text)
            if len(prior_user_turns) >= 2:
                break
        elif not prior_assistant_turn and _is_ai_message(msg):
            prior_assistant_turn = text

    is_short_followup = (
        len(latest.split()) <= 6
        or bool(_ACK_RE.match(latest))
        or bool(_CONTEXTUAL_RE.search(latest))
    )
    parts = [f"Current request: {latest}"]
    if prior_assistant_turn and is_short_followup:
        parts.append("Latest assistant prompt: " + prior_assistant_turn[:500])
    if prior_user_turns:
        prior_user_turns.reverse()
        parts.append("Recent user context: " + " | ".join(prior_user_turns))
    if summary:
        parts.append("Earlier summary: " + summary[:500])

    return "\n".join(parts)


def _rewrite_query_with_haiku(standalone_query: str, latest_user_turn: str) -> str:
    """
    One cheap rewrite pass that resolves follow-ups/pronouns into a concise
    standalone search query. Returns empty string on failure.
    """
    if not standalone_query:
        return ""

    try:
        import anthropic

        client = anthropic.Anthropic()
        system = (
            "Rewrite the user's latest request into a single standalone retrieval query. "
            "Use supplied context only. Expand pronouns/references when possible. "
            "Keep it concise (max 2 lines). Return only the rewritten query."
        )
        prompt = (
            f"Latest user request:\n{latest_user_turn}\n\n"
            f"Context for disambiguation:\n{standalone_query}\n\n"
            "Standalone retrieval query:"
        )
        resp = call_model(
            client,
            task="retrieval_rewrite",
            max_tokens=140,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        rewritten = "\n".join(_msg_content(block).strip() for block in (resp.content or []) if _msg_content(block).strip())
        return rewritten
    except Exception:
        return ""


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
            estimate_parts = []
            if issue.get("story_points") not in (None, ""):
                estimate_parts.append(f"Story points: {issue['story_points']}")
            if issue.get("original_estimate"):
                estimate_parts.append(f"Original estimate: {issue['original_estimate']}")
            if issue.get("remaining_estimate"):
                estimate_parts.append(f"Remaining estimate: {issue['remaining_estimate']}")
            estimate_line = ("\n" + "  |  ".join(estimate_parts)) if estimate_parts else ""
            live.append({
                "content": (
                    f"[Live Jira] {issue['key']}: {issue['summary']}\n"
                    f"Status: {issue['status']}  |  Type: {issue['issue_type']}  |  Assignee: {issue['assignee']}\n"
                    f"{estimate_line}"
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
    latest_query = state.get("resolved_query") or _msg_content(state["messages"][-1]).strip()
    query = latest_query if state.get("resolved_query") else (_build_standalone_query(state["messages"]) or latest_query)
    session_context = (state.get("session_context") or "").strip()
    if session_context and not state.get("resolved_query"):
        query = f"{query}\nSession context:\n{session_context[:1600]}"
    intent = state.get("intent", "qa")
    feature_id = state.get("feature_id")

    # 0. Feature-aware retrieval: session summaries + linked artefacts first
    feature_chunks = []
    if feature_id:
        feature_chunks = get_feature_retrieval_chunks(feature_id, query)

    # 1. Live Jira key lookups — explicitly mentioned tickets always resolve first
    live_chunks = _fetch_live_jira(latest_query)

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

    # Feature chunks are intentionally placed first to prioritize current
    # workspace context before broader global knowledge.
    all_chunks = feature_chunks + live_chunks + memory_chunks + chunks
    top_score = all_chunks[0]["score"] if all_chunks else 0

    # 2b. One-shot rewrite retry for ambiguous follow-ups before live search fallback.
    # Only retry when confidence is low and we don't already have explicit live Jira hits.
    if top_score < CONFIDENCE_THRESHOLD and not live_chunks:
        rewritten_query = _rewrite_query_with_haiku(query, latest_query)
        if rewritten_query and rewritten_query.lower() != query.lower():
            retry_chunks = search_knowledge(rewritten_query)
            retry_memories = search_memory(rewritten_query, top_k=2)
            retry_memory_chunks = [
                {
                    "content": f"[Team memory] {m['content']}"
                               + (f" — {m['context']}" if m.get("context") else ""),
                    "url": "",
                    "content_type": "team_memory",
                    "tags": m.get("tags", []),
                    "score": m["score"],
                    "high_confidence": m["score"] >= CONFIDENCE_THRESHOLD,
                }
                for m in retry_memories
                if m["score"] >= CONFIDENCE_THRESHOLD
            ]
            if retry_chunks or retry_memory_chunks:
                all_chunks = all_chunks + retry_memory_chunks + retry_chunks
                retry_candidates = retry_memory_chunks + retry_chunks
                retry_top = retry_candidates[0]["score"] if retry_candidates else 0
                top_score = max(top_score, retry_top)

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
