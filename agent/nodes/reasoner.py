"""
Synthesizes answers and drafts stories using Claude Sonnet.
"""
import json
import anthropic
import re as _re
from agent.state import AgentState

SUMMARIZE_CONVERSATION = "SUMMARIZE_CONVERSATION"

_SUMMARY_REQUEST_RE = _re.compile(
    r"\b(remember|save|summarize|capture|record)\b.{0,30}"
    r"\b(our discussion|our decisions|our conversation|what we discussed|"
    r"key decisions|key points|this conversation|our session)\b",
    _re.IGNORECASE,
)

client = anthropic.Anthropic()

# ── Q&A ──────────────────────────────────────────────────────────────────────

QA_SYSTEM = """You are One Context, an AI co-pilot for the Colleqt software delivery team.
Answer questions using only the numbered sources provided below.

Rules:
- Base answers strictly on the provided sources. Do not invent facts.
- Cite sources inline using their label, e.g. [S1], [S2]. Every claim must be traceable.
- If sources only partially answer the question, say what you found and what is missing.
- If you cannot find the answer, say so explicitly — never guess.
- For status/progress questions: use bullet points. For decisions/explanations: use prose.
- Feature session summaries [Sx] and linked artefacts [Sx] take priority over general knowledge."""

CLARIFY_SYSTEM = """You are One Context, a team AI assistant.
The user's question is too vague. Ask one focused clarifying question to narrow it down."""

# ── Story drafting ────────────────────────────────────────────────────────────

STORY_DRAFT_SYSTEM = """You are One Context, an AI co-pilot that helps Product Owners write Jira stories.
Draft a well-formed story grounded in the team's actual codebase and history.
Be specific — reference real services, existing capabilities, and prior decisions from the context.
Format the story clearly for review."""

STORY_DRAFT_PROMPT = """Draft a Jira story based on this request:

"{request}"

Context from team knowledge base:
{context}

Produce a story with this exact structure:

**Title:** <concise, action-oriented title>

**Description:**
<2-3 sentences describing the goal from a user/business perspective>

**Acceptance Criteria:**
- <specific, testable criterion>
- <specific, testable criterion>
- <specific, testable criterion>

**Labels:** <comma-separated labels relevant to this story>

**Context used:** <1-2 sentences explaining what existing knowledge informed this draft>

---
Reply **yes** to create this story in Jira, or tell me what to change."""

# ── Memory ───────────────────────────────────────────────────────────────────

REMEMBER_SYSTEM = """You are One Context. The user wants to save something to team memory.

Extract the key fact, decision, or agreement from their message.
- If a specific fact is present, reply with JUST the fact (1-3 sentences, no preamble).
- If the message asks to summarize or remember the whole conversation/discussion/decisions, reply with exactly: SUMMARIZE_CONVERSATION
- If the message is vague (e.g. "remember these decisions" with nothing specific), reply with exactly: ASK_FOR_CONTENT"""

CONV_SUMMARY_SYSTEM = """You are One Context. Extract 3-5 key decisions, agreements, or action items from this conversation as concise bullet points. Each bullet should be a complete, self-contained statement."""

SESSION_CLOSE_SYSTEM = """You are One Context. Generate a structured session summary for a feature workspace session.

Given the conversation transcript, produce a summary in this EXACT format (all sections required):

DECISIONS:
- <key decision or agreement made, self-contained>
(list up to 4; omit section content if none)

ACTIONS TAKEN:
- <concrete action completed: story created, memory saved, page updated, etc.>
(list up to 4; omit section content if none)

OPEN QUESTIONS:
- <unresolved question or next step that needs follow-up>
(list up to 3; omit section content if none)

SUMMARY:
<1-2 sentence plain-language summary of what this session accomplished>

Be concise. Each bullet must be a complete, self-contained statement. Do not invent content not present in the transcript."""

CONFLUENCE_UPDATE_SYSTEM = """You are One Context. The user wants to update a Confluence page.

Extract from their message:
- PAGE: the exact page title they mentioned
- CONTENT: the content to append

Reply in this EXACT format (two lines only):
PAGE: <exact page title>
CONTENT: <content to append>

If you cannot determine both clearly, ask one short clarifying question."""


def reasoner_node(state: AgentState) -> AgentState:
    intent = state.get("intent", "qa")
    query = state["messages"][-1].content

    if state.get("needs_clarification"):
        return _clarify(state, query)

    if intent == "story_draft":
        return _draft_story(state, query)

    if intent == "remember":
        return _prepare_memory(state, query)

    if intent == "confluence_update":
        return _prepare_confluence_update(state, query)

    if intent == "link_artefact":
        return _prepare_link_artefact(state, query)

    # qa, pipeline_query, confirm_action (shouldn't reach here), default
    return _answer_qa(state, query)


# ── Handlers ─────────────────────────────────────────────────────────────────

def _answer_qa(state: AgentState, query: str) -> AgentState:
    chunks = state.get("retrieved_chunks", [])

    # Build numbered source blocks so the model can cite inline as [S1], [S2], etc.
    # We label each source and track the mapping so we can later resolve which
    # sources were actually cited — making citations a reasoning input, not afterthought.
    source_index: list[dict] = []  # [{label, url, score, content_type}]
    context_parts: list[str] = []

    for i, chunk in enumerate(chunks[:8]):
        label = f"S{i+1}"
        ctype = chunk.get("content_type", "knowledge")
        url = chunk.get("url", "")
        score = chunk.get("score", 0)
        # Brief source header so the model knows what kind of source this is
        header = _source_header(label, ctype, url, score)
        context_parts.append(
            f"{header}\n{chunk['content'][:800]}"
        )
        source_index.append({"label": label, "url": url, "score": score, "content_type": ctype})

    context = "\n\n---\n\n".join(context_parts) or "No relevant context found."
    system = _build_system(QA_SYSTEM, state)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=system,
        messages=[{
            "role": "user",
            "content": f"Question: {query}\n\nSources:\n\n{context}",
        }],
    )

    answer_text = response.content[0].text

    # Only return citations for sources actually referenced in the answer.
    # This means the citation list reflects what was used, not what was retrieved.
    cited_labels = set(_re.findall(r"\[S(\d+)\]", answer_text))
    citations = [
        {"url": s["url"], "score": s["score"], "content_type": s["content_type"], "label": s["label"]}
        for s in source_index
        if s["label"][1:] in cited_labels and s["url"]
    ]
    # Fallback: if model cited nothing but we have high-confidence results, include top 3
    if not citations:
        citations = [
            {"url": s["url"], "score": s["score"], "content_type": s["content_type"], "label": s["label"]}
            for s in source_index[:3]
            if s["url"] and s["score"] >= 0.5
        ]

    return {**state, "answer": answer_text, "citations": citations}


def _source_header(label: str, ctype: str, url: str, score: float) -> str:
    """One-line header for a source block that tells the model what kind of source it is."""
    type_labels = {
        "feature_session_summary": "Feature session summary",
        "feature_link": "Feature linked artefact",
        "team_memory": "Team memory",
        "jira_issue": "Jira issue",
        "confluence_page": "Confluence page",
        "business_flow": "Codebase capability",
        "shipped_feature": "Shipped feature",
        "api_capability": "API capability",
    }
    type_label = type_labels.get(ctype, "Knowledge")
    url_part = f" | {url}" if url else ""
    return f"[{label}] {type_label}{url_part} (relevance: {score:.2f})"


def _draft_story(state: AgentState, query: str) -> AgentState:
    chunks = state.get("retrieved_chunks", [])
    context_parts = []
    for i, chunk in enumerate(chunks[:5]):
        context_parts.append(
            f"[{i+1}] {chunk['content'][:600]}\n(source: {chunk.get('url', 'n/a')})"
        )
    context = "\n\n".join(context_parts) or "No prior context found — drafting from scratch."

    system = _build_system(STORY_DRAFT_SYSTEM, state)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=system,
        messages=[{
            "role": "user",
            "content": STORY_DRAFT_PROMPT.format(request=query, context=context),
        }],
    )

    draft_text = response.content[0].text

    # Parse title, description, ACs, labels from the draft for the act node
    pending_action = _parse_story_draft(draft_text, query)

    # Embed the pending action as a hidden marker the act node can read
    answer_with_marker = (
        draft_text
        + f"\n\n<!-- PENDING_ACTION: {json.dumps(pending_action)} -->"
    )

    return {
        **state,
        "answer": answer_with_marker,
        "citations": [],
        "pending_action": pending_action,
    }


def _summarize_conversation(state: AgentState) -> str:
    from langchain_core.messages import HumanMessage
    raw_messages = state.get("messages", [])
    recent = [
        m for m in raw_messages
        if not (hasattr(m, "content") and m.content.startswith("[FEATURE CONTEXT]"))
    ][-10:]
    transcript_lines = []
    for m in recent:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        content = m.content
        # strip pending action markers
        content = _re.sub(r"<!-- PENDING_ACTION:.*?-->", "", content, flags=_re.DOTALL).strip()
        if content:
            transcript_lines.append(f"{role}: {content[:400]}")
    transcript = "\n\n".join(transcript_lines) or "No conversation yet."
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=CONV_SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": f"Conversation:\n\n{transcript}"}],
    )
    return response.content[0].text.strip()


def generate_session_summary(conversation_id: int) -> str:
    """
    Generate a structured session summary for a feature session.
    Called externally by the API when a new session starts — summarizes the
    previous session so its decisions carry forward automatically.

    Returns a formatted string with DECISIONS / ACTIONS TAKEN / OPEN QUESTIONS / SUMMARY.
    Returns empty string if the conversation has no meaningful messages.
    """
    from db.connection import cursor as _cursor
    from langchain_core.messages import HumanMessage as _HM

    with _cursor() as cur:
        cur.execute(
            """SELECT role, content FROM messages
               WHERE conversation_id = %s ORDER BY created_at""",
            (conversation_id,),
        )
        rows = cur.fetchall()

    # Filter out system bootstrap messages and action markers
    lines = []
    for row in rows:
        role = row["role"]
        content = row["content"] or ""
        if content.startswith("[FEATURE CONTEXT") or content.startswith("[FEATURE CONTEXT ACK]"):
            continue
        content = _re.sub(r"<!-- PENDING_ACTION:.*?-->", "", content, flags=_re.DOTALL).strip()
        if not content:
            continue
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content[:500]}")

    if len(lines) < 2:
        return ""

    transcript = "\n\n".join(lines[-16:])  # last 16 exchanges max

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=SESSION_CLOSE_SYSTEM,
        messages=[{"role": "user", "content": f"Conversation transcript:\n\n{transcript}"}],
    )
    return response.content[0].text.strip()


def _prepare_memory(state: AgentState, query: str) -> AgentState:
    # Fast-path: detect conversation-summary requests before LLM call
    if _SUMMARY_REQUEST_RE.search(query):
        fact = SUMMARIZE_CONVERSATION
    else:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=REMEMBER_SYSTEM,
            messages=[{"role": "user", "content": query}],
        )
        fact = response.content[0].text.strip()

    if fact == "ASK_FOR_CONTENT":
        return {
            **state,
            "answer": "What would you like me to remember? Share the decision or fact and I'll save it to team memory.",
            "citations": [],
        }

    if fact == SUMMARIZE_CONVERSATION:
        fact = _summarize_conversation(state)

    pending_action = {
        "type": "remember",
        "fact": fact,
        "context": query,
    }
    answer_with_marker = (
        f"Got it — I'll save this to team memory:\n\n> {fact}\n\n"
        f"Reply **yes** to confirm."
        f"\n\n<!-- PENDING_ACTION: {json.dumps(pending_action)} -->"
    )
    return {**state, "answer": answer_with_marker, "citations": [], "pending_action": pending_action}


def _prepare_confluence_update(state: AgentState, query: str) -> AgentState:
    system = _build_system(CONFLUENCE_UPDATE_SYSTEM, state)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=system,
        messages=[{"role": "user", "content": query}],
    )
    raw = response.content[0].text.strip()

    page_title, content = "", ""
    for line in raw.splitlines():
        if line.startswith("PAGE:"):
            page_title = line[5:].strip()
        elif line.startswith("CONTENT:"):
            content = line[8:].strip()

    if not page_title or not content:
        return {**state, "answer": raw, "citations": []}

    pending_action = {"type": "confluence_update", "page_title": page_title, "content": content}
    answer_body = (
        f"I'll update this Confluence page for you:\n\n"
        f"- **Page:** {page_title}\n"
        f"- **Content to append:**\n\n{content}\n\n"
        f"---\nReply **yes** to update, or tell me what to change."
    )
    answer_with_marker = answer_body + f"\n\n<!-- PENDING_ACTION: {json.dumps(pending_action)} -->"
    return {**state, "answer": answer_with_marker, "citations": [], "pending_action": pending_action}


def _clarify(state: AgentState, query: str) -> AgentState:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=CLARIFY_SYSTEM,
        messages=[{"role": "user", "content": query}],
    )
    return {**state, "answer": response.content[0].text, "citations": []}


def _build_system(base_system: str, state: AgentState) -> str:
    """Prepend feature context to system prompt if conversation is in a feature session."""
    feature_id = state.get("feature_id")
    if not feature_id:
        return base_system
    try:
        from agent.tools.feature_tools import build_feature_context
        ctx = build_feature_context(feature_id)
        if ctx:
            return f"{base_system}\n\n{ctx}"
    except Exception:
        pass
    return base_system


def _prepare_link_artefact(state: AgentState, query: str) -> AgentState:
    """Handle 'add CL-1524 to this feature' — fetch ticket live, confirm before linking."""
    feature_id = state.get("feature_id")
    if not feature_id:
        return {
            **state,
            "answer": "You need to be in a feature session to link artefacts. Open a feature from the sidebar and start a session first.",
            "citations": [],
        }

    # Pull live Jira data from retrieved_chunks (retriever already fetched it)
    live = [c for c in state.get("retrieved_chunks", []) if c.get("content_type") == "jira_issue"]

    if not live:
        # Fallback: try to extract key and fetch directly
        import re as _re2
        keys = _re2.findall(r'\b([A-Z][A-Z0-9]+-\d+)\b', query)
        if not keys:
            return {
                **state,
                "answer": "I couldn't find a Jira ticket key in your message. Please include the ticket key (e.g. CL-1524) and I'll link it to the feature.",
                "citations": [],
            }
        try:
            from agent.tools.jira_tools import get_jira_issue
            import os
            issue = get_jira_issue(keys[0])
            live = [{
                "jira_key": issue["key"],
                "jira_url": issue["url"],
                "jira_summary": issue["summary"],
                "content_type": "jira_issue",
            }]
        except Exception as e:
            return {
                **state,
                "answer": f"Couldn't fetch {keys[0]} from Jira: {e}",
                "citations": [],
            }

    chunk = live[0]
    key = chunk.get("jira_key", "")
    url = chunk.get("jira_url", "")
    summary = chunk.get("jira_summary", "")

    # Determine link_type from issue_type if available
    content = chunk.get("content", "")
    if "Story" in content:
        link_type = "jira_story"
    elif "Epic" in content:
        link_type = "jira_epic"
    else:
        link_type = "jira_story"

    pending_action = {
        "type": "link_artefact",
        "link_type": link_type,
        "link_id": key,
        "link_url": url,
        "title": summary,
        "feature_id": feature_id,
    }
    answer_with_marker = (
        f"I'll link this to feature **{feature_id}**:\n\n"
        f"- 📋 **{key}**: {summary}\n"
        f"- [{url}]({url})\n\n"
        f"Reply **yes** to confirm, or tell me if this is wrong."
        f"\n\n<!-- PENDING_ACTION: {json.dumps(pending_action)} -->"
    )
    return {**state, "answer": answer_with_marker, "citations": [], "pending_action": pending_action}


def _parse_story_draft(draft_text: str, original_request: str) -> dict:
    """Extract structured fields from the draft text for Jira creation."""
    import re
    title = ""
    title_match = re.search(r"\*\*Title:\*\*\s*(.+)", draft_text)
    if title_match:
        title = title_match.group(1).strip()

    description = ""
    desc_match = re.search(r"\*\*Description:\*\*\s*([\s\S]+?)(?=\*\*Acceptance)", draft_text)
    if desc_match:
        description = desc_match.group(1).strip()

    acs = []
    ac_match = re.search(r"\*\*Acceptance Criteria:\*\*\s*([\s\S]+?)(?=\*\*Labels)", draft_text)
    if ac_match:
        acs = [line.strip("- ").strip() for line in ac_match.group(1).strip().split("\n") if line.strip().startswith("-")]

    labels = []
    labels_match = re.search(r"\*\*Labels:\*\*\s*(.+)", draft_text)
    if labels_match:
        labels = [l.strip() for l in labels_match.group(1).split(",")]

    return {
        "type": "create_jira_story",
        "title": title or original_request[:80],
        "description": description,
        "acceptance_criteria": "\n".join(f"- {ac}" for ac in acs),
        "labels": labels,
    }
