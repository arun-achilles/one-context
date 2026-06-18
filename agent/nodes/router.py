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

PLANNER_SYSTEM = """You are an intent planner for a delivery assistant.

Choose one intent from:
- qa
- pipeline_query
- story_draft
- remember
- confluence_update
- link_artefact
- update_jira
- create_subtasks
- create_confluence
- confirm_action
- clarify

Return JSON only with this exact shape:
{"intent":"...","confidence":0.0,"rewritten_request":"..."}

Rules:
- confidence must be between 0 and 1.
- rewritten_request should be empty unless the latest user message is a short contextual follow-up.
- Use session context and pending context when available.
- If uncertain, choose clarify with low confidence.
- Do not invent new scope beyond provided context."""

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

_VALID_INTENTS = {
    "qa", "pipeline_query", "story_draft", "remember", "confluence_update",
    "link_artefact", "update_jira", "create_subtasks", "create_confluence",
    "confirm_action", "clarify",
}
_INTENT_CONFIDENCE_THRESHOLD = 0.55

_ROLE_ROUTING_HINTS = {
    "po": "PO users often ask for scope, acceptance criteria, stories, and prioritization.",
    "ba": "BA users often ask for requirements clarification, business rules, and process details.",
    "dev": "Dev users often ask for implementation details, technical updates, and task breakdowns.",
    "qa": "QA users often ask for test cases, edge cases, validation criteria, and defects.",
    "tech_lead": "Tech leads often ask for architecture, risks, implementation plans, and technical decisions.",
}


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


def _plan_intent(state: AgentState, last_message: str) -> dict | None:
    pending_ctx = state.get("pending_context") or {}
    role = (state.get("role") or "").strip().lower()
    payload = {
        "latest_user_message": last_message,
        "router_context": _build_router_input_with_session(state),
        "session_context": state.get("session_context") or "",
        "role": role or "unknown",
        "role_hint": _ROLE_ROUTING_HINTS.get(role, "General routing behavior."),
        "has_pending_action": bool(state.get("pending_action")),
        "pending_question": pending_ctx.get("pending_question"),
        "pending_options": pending_ctx.get("pending_options") or [],
    }
    try:
        response = call_model(
            client,
            task="router",
            max_tokens=220,
            system=PLANNER_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=True)}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
        data = json.loads(raw)
    except Exception:
        return None

    intent = str(data.get("intent", "")).strip()
    if intent not in _VALID_INTENTS:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    rewritten = str(data.get("rewritten_request", "") or "").strip()

    return {
        "intent": intent,
        "confidence": confidence,
        "rewritten_request": rewritten,
    }


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

    plan = _plan_intent(state, last_message)
    if plan:
        intent = plan["intent"]
        confidence = plan["confidence"]
        rewritten = plan["rewritten_request"]

        # confirm_action must have a pending draft/action.
        if intent == "confirm_action" and not _has_pending_draft(state):
            if _ACK_ONLY_RE.match(last_message):
                resolution = _resolve_ack_followup(state, last_message)
                if resolution and resolution.get("action") == "proceed" and resolution.get("rewritten_request"):
                    return {
                        **state,
                        "intent": resolution.get("intent", "qa"),
                        "resolved_query": resolution.get("rewritten_request"),
                    }
            intent = "clarify"

        if confidence >= _INTENT_CONFIDENCE_THRESHOLD:
            return {
                **state,
                "intent": intent,
                "resolved_query": rewritten or None,
            }

    # Minimal safety fallback only.
    if _ACK_ONLY_RE.match(last_message) and not _has_pending_draft(state):
        resolution = _resolve_ack_followup(state, last_message)
        if resolution and resolution.get("action") == "proceed" and resolution.get("rewritten_request"):
            return {
                **state,
                "intent": resolution.get("intent", "qa"),
                "resolved_query": resolution.get("rewritten_request"),
            }
        return {**state, "intent": "clarify", "resolved_query": None}

    if _has_pending_draft(state) and _CONFIRM_RE.match(last_message):
        return {**state, "intent": "confirm_action", "resolved_query": None}

    return {**state, "intent": "qa", "resolved_query": None}


def _has_pending_draft(state: AgentState) -> bool:
    """Check if there is a pending action in state or legacy marker in history."""
    if state.get("pending_action"):
        return True
    from langchain_core.messages import AIMessage
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage):
            return "<!-- PENDING_ACTION:" in msg.content
    return False
