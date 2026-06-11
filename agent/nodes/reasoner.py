"""
Synthesizes answers and drafts stories using Claude Sonnet.
"""
import json
import anthropic
from agent.state import AgentState

client = anthropic.Anthropic()

# ── Q&A ──────────────────────────────────────────────────────────────────────

QA_SYSTEM = """You are One Context, an AI co-pilot for the Colleqt software delivery team.
Answer questions using only the context provided from Jira, Confluence, and codebase knowledge.

Rules:
- Base answers strictly on the provided context. Do not invent facts.
- If context only partially answers the question, say what you found and what's missing.
- If you cannot find the answer, say so explicitly — never guess.
- Always cite specific tickets, pages, or services by name so the user can follow up.
- For status/progress questions: use bullet points. For decisions/explanations: use prose."""

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
Extract the key fact or decision from their message and confirm what you're saving."""


def reasoner_node(state: AgentState) -> AgentState:
    intent = state.get("intent", "qa")
    query = state["messages"][-1].content

    if state.get("needs_clarification"):
        return _clarify(state, query)

    if intent == "story_draft":
        return _draft_story(state, query)

    if intent == "remember":
        return _prepare_memory(state, query)

    # qa, pipeline_query, confirm_action (shouldn't reach here), default
    return _answer_qa(state, query)


# ── Handlers ─────────────────────────────────────────────────────────────────

def _answer_qa(state: AgentState, query: str) -> AgentState:
    chunks = state.get("retrieved_chunks", [])
    context_parts, citations = [], []

    for i, chunk in enumerate(chunks[:6]):
        context_parts.append(
            f"[Source {i+1}] (score: {chunk['score']})\n"
            f"URL: {chunk.get('url', 'n/a')}\n"
            f"{chunk['content'][:800]}"
        )
        citations.append({"url": chunk.get("url", ""), "score": chunk["score"]})

    context = "\n\n---\n\n".join(context_parts) or "No relevant context found."
    system = _build_system(QA_SYSTEM, state)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=system,
        messages=[{
            "role": "user",
            "content": f"Question: {query}\n\nContext:\n\n{context}",
        }],
    )
    return {**state, "answer": response.content[0].text, "citations": citations}


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


def _prepare_memory(state: AgentState, query: str) -> AgentState:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=REMEMBER_SYSTEM,
        messages=[{"role": "user", "content": query}],
    )
    # Extract what to remember — everything after "remember:" / "note:" keywords
    fact = query
    for prefix in ["remember:", "note:", "save:", "record:"]:
        if prefix in query.lower():
            fact = query[query.lower().index(prefix) + len(prefix):].strip()
            break

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
