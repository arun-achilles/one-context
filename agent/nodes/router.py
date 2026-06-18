"""
Classifies user intent and detects confirmation of pending write actions.

Intents:
  qa                — question about team knowledge, code, architecture
  pipeline_query    — sprint status, blockers, what's in progress
  story_draft       — user wants to create a Jira story
  remember          — user wants to persist a decision/fact to team memory
  confluence_update — user wants to update or append content to a Confluence page
  update_jira       — user wants to update an existing Jira ticket
  create_subtasks   — user wants to create subtasks under a Jira ticket
  create_confluence — user wants to create a new Confluence page
  confirm_action    — user is confirming a pending write (yes/create/go ahead)
  clarify           — query too vague to act on
"""
import json
import re
import anthropic
from agent.state import AgentState
from agent.model_policy import call_model

client = anthropic.Anthropic()

SYSTEM = """Classify the user's message into exactly one intent:
- qa: question about the system, codebase, architecture, decisions, or team history
- pipeline_query: question about sprint status, blockers, in-progress work, or delivery
- story_draft: user wants to draft or create a Jira story/ticket
- remember: user explicitly wants to save a decision, fact, or agreement to team memory
- confluence_update: user wants to update or append content to a Confluence page
- link_artefact: user wants to link or add a specific Jira ticket, Confluence page, or other artefact to the current feature (e.g. "add CL-1524 to this feature", "link this card to the feature")
- update_jira: user wants to update, edit, or add content to an existing Jira ticket
- create_subtasks: user wants to break down a story into subtasks or child tasks under a Jira ticket
- create_confluence: user wants to create a brand new Confluence page or document
- confirm_action: user is confirming or approving a previously shown draft (e.g. "yes", "create it", "looks good", "go ahead")
- clarify: message is too vague or ambiguous to act on

Reply with a JSON object: {"intent": "<intent>"}"""

FOLLOWUP_SYSTEM = """Resolve a short acknowledgement against the previous assistant turn.

Return JSON only with this shape:
{"action":"proceed|clarify","intent":"qa|pipeline_query|story_draft|remember|confluence_update|link_artefact|update_jira|create_subtasks|create_confluence|clarify","rewritten_request":"..."}

Rules:
- Use action=proceed only when the assistant previously proposed a concrete next step and the user's acknowledgement clearly means to continue.
- When action=proceed, rewritten_request must be a standalone user request that can be handled directly.
- If the assistant previously offered multiple distinct options and the user did not choose one, use action=clarify.
- If uncertain, use action=clarify.
- Do not invent scope beyond the prior assistant turn and provided context."""


# Patterns that strongly indicate confirmation regardless of LLM
_CONFIRM_RE = re.compile(
    r"^\s*(yes|yeah|yep|sure|ok|okay|go ahead|create it|looks good|do it|confirm|approved|correct|that'?s? (right|good|fine))\s*[.!]?\s*$",
    re.IGNORECASE,
)

_SHORT_FOLLOWUP_RE = re.compile(
    r"^\s*(ok|okay|yes|yeah|yep|sure|got it|understood|that one|this one|it|that|also|and)\b",
    re.IGNORECASE,
)
_ACK_ONLY_RE = re.compile(
    r"^\s*(?:"
    r"(yes|yeah|yep|sure|ok|okay)(?:\s+(please|give|continue|proceed|go\s+ahead|do\s+it))?"
    r"|got\s+it"
    r"|understood"
    r"|sounds\s+good"
    r"|that\s+works"
    r"|do\s+it"
    r"|go\s+ahead"
    r")\s*[.!]?\s*$",
    re.IGNORECASE,
)


def _msg_content(msg) -> str:
    """Extract plain text from a LangChain message-like object."""
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
    t = (getattr(msg, "type", "") or "").lower()
    cls = msg.__class__.__name__.lower()
    return t in ("human", "user") or "human" in cls


def _is_ai_message(msg) -> bool:
    t = (getattr(msg, "type", "") or "").lower()
    cls = msg.__class__.__name__.lower()
    return t in ("ai", "assistant") or "ai" in cls or "assistant" in cls


def _build_router_input(messages: list) -> str:
    """Provide the classifier with light conversational context for follow-up turns."""
    if not messages:
        return ""

    latest = _msg_content(messages[-1]).strip()
    if not latest:
        return ""

    # For substantive turns, classify the latest utterance directly.
    if len(latest.split()) > 8 and not _SHORT_FOLLOWUP_RE.match(latest):
        return latest

    # For short/contextual turns, include previous user + assistant turns.
    prev_user = ""
    prev_ai = ""
    for msg in reversed(messages[:-1]):
        text = _msg_content(msg).strip()
        if not text:
            continue
        if not prev_ai and _is_ai_message(msg):
            prev_ai = text
        elif not prev_user and _is_human_message(msg):
            prev_user = text
        if prev_ai and prev_user:
            break

    parts = [f"Latest user message: {latest}"]
    if prev_ai:
        parts.append(f"Previous assistant message: {prev_ai[:500]}")
    if prev_user:
        parts.append(f"Previous user message: {prev_user[:500]}")
    parts.append("Classify intent for the latest user message using the above context.")
    return "\n\n".join(parts)


def _build_router_input_with_session(state: AgentState) -> str:
    base = _build_router_input(state.get("messages", []))
    session_context = (state.get("session_context") or "").strip()
    if not session_context:
        return base
    return f"{base}\n\nSession context:\n{session_context[:1800]}"


def _get_previous_assistant_message(messages: list) -> str:
    for msg in reversed(messages[:-1]):
        text = _msg_content(msg).strip()
        if text and _is_ai_message(msg):
            return text
    return ""


def _resolve_ack_followup(state: AgentState, last_message: str) -> dict | None:
    pending_ctx = state.get("pending_context") or {}
    previous_assistant = _get_previous_assistant_message(state.get("messages", []))
    if not previous_assistant and not pending_ctx:
        return None

    prompt = json.dumps(
        {
            "latest_user_message": last_message,
            "previous_assistant_message": previous_assistant,
            "pending_question": pending_ctx.get("pending_question"),
            "pending_options": pending_ctx.get("pending_options") or [],
            "session_context": state.get("session_context") or "",
        },
        ensure_ascii=True,
    )

    try:
        response = call_model(
            client,
            task="followup_resolver",
            max_tokens=220,
            system=FOLLOWUP_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
        data = json.loads(raw)
    except Exception:
        return None

    if data.get("action") not in {"proceed", "clarify"}:
        return None
    return data


def router_node(state: AgentState) -> AgentState:
    last_message = _msg_content(state["messages"][-1]).strip()

    # Fast-path: obvious confirmation patterns
    if _CONFIRM_RE.match(last_message) and _has_pending_draft(state):
        return {**state, "intent": "confirm_action", "resolved_query": None}

    # Bare acknowledgements without a pending action are follow-ups that need
    # dialogue-state resolution, not fresh QA.
    if _ACK_ONLY_RE.match(last_message) and not _has_pending_draft(state):
        resolution = _resolve_ack_followup(state, last_message)
        if resolution and resolution.get("action") == "proceed" and resolution.get("rewritten_request"):
            return {
                **state,
                "intent": resolution.get("intent", "qa"),
                "resolved_query": resolution.get("rewritten_request"),
            }
        return {**state, "intent": "clarify", "resolved_query": None}

    response = call_model(
        client,
        task="router",
        max_tokens=30,
        system=SYSTEM,
        messages=[{"role": "user", "content": _build_router_input_with_session(state) or last_message}],
    )

    try:
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
        data = json.loads(raw)
        intent = data.get("intent", "qa")
    except (json.JSONDecodeError, IndexError):
        intent = "qa"

    valid = {"qa", "pipeline_query", "story_draft", "remember", "confluence_update",
             "link_artefact", "update_jira", "create_subtasks", "create_confluence",
             "confirm_action", "clarify"}
    if intent not in valid:
        intent = "qa"

    # Double-check: if LLM says confirm_action, verify there's actually a pending draft
    if intent == "confirm_action" and not _has_pending_draft(state):
        intent = "qa"

    return {**state, "intent": intent, "resolved_query": None}


def _has_pending_draft(state: AgentState) -> bool:
    """Check if there is a pending action in state or legacy marker in history."""
    if state.get("pending_action"):
        return True
    from langchain_core.messages import AIMessage
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage):
            return "<!-- PENDING_ACTION:" in msg.content
    return False
