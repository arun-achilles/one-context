"""
Classifies user intent and detects confirmation of pending write actions.

Intents:
  qa                — question about team knowledge, code, architecture
  pipeline_query    — sprint status, blockers, what's in progress
  story_draft       — user wants to create a Jira story
  remember          — user wants to persist a decision/fact to team memory
  confluence_update — user wants to update or append content to a Confluence page
  confirm_action    — user is confirming a pending write (yes/create/go ahead)
  clarify           — query too vague to act on
"""
import json
import re
import anthropic
from agent.state import AgentState

client = anthropic.Anthropic()

SYSTEM = """Classify the user's message into exactly one intent:
- qa: question about the system, codebase, architecture, decisions, or team history
- pipeline_query: question about sprint status, blockers, in-progress work, or delivery
- story_draft: user wants to draft or create a Jira story/ticket
- remember: user explicitly wants to save a decision, fact, or agreement to team memory
- confluence_update: user wants to update or append content to a Confluence page
- link_artefact: user wants to link or add a specific Jira ticket, Confluence page, or other artefact to the current feature (e.g. "add CL-1524 to this feature", "link this card to the feature")
- confirm_action: user is confirming or approving a previously shown draft (e.g. "yes", "create it", "looks good", "go ahead")
- clarify: message is too vague or ambiguous to act on

Reply with a JSON object: {"intent": "<intent>"}"""


# Patterns that strongly indicate confirmation regardless of LLM
_CONFIRM_RE = re.compile(
    r"^\s*(yes|yeah|yep|sure|ok|okay|go ahead|create it|looks good|do it|confirm|approved|correct|that'?s? (right|good|fine))\s*[.!]?\s*$",
    re.IGNORECASE,
)


def router_node(state: AgentState) -> AgentState:
    last_message = state["messages"][-1].content

    # Fast-path: obvious confirmation patterns
    if _CONFIRM_RE.match(last_message) and _has_pending_draft(state):
        return {**state, "intent": "confirm_action"}

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=30,
        system=SYSTEM,
        messages=[{"role": "user", "content": last_message}],
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

    valid = {"qa", "pipeline_query", "story_draft", "remember", "confluence_update", "link_artefact", "confirm_action", "clarify"}
    if intent not in valid:
        intent = "qa"

    # Double-check: if LLM says confirm_action, verify there's actually a pending draft
    if intent == "confirm_action" and not _has_pending_draft(state):
        intent = "qa"

    return {**state, "intent": intent}


def _has_pending_draft(state: AgentState) -> bool:
    """Check if the last assistant message contains a pending action marker."""
    from langchain_core.messages import AIMessage
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage):
            return "<!-- PENDING_ACTION:" in msg.content
    return False
