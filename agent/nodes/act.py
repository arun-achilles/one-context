"""
Executes confirmed write actions: create Jira story, update Confluence, save memory.
Only runs when intent == confirm_action.
"""
import json
import re
from langchain_core.messages import AIMessage
from agent.state import AgentState


def act_node(state: AgentState) -> AgentState:
    # Extract the pending action from the last assistant message
    pending_action = _extract_pending_action(state)
    if not pending_action:
        return {**state, "answer": "Nothing to confirm — I don't see a pending action."}

    action_type = pending_action.get("type")

    if action_type == "create_jira_story":
        return _create_story(state, pending_action)

    if action_type == "remember":
        return _save_memory(state, pending_action)

    if action_type == "confluence_update":
        return _update_confluence(state, pending_action)

    if action_type == "link_artefact":
        return _do_link_artefact(state, pending_action)

    return {**state, "answer": f"Unknown action type: {action_type}"}


def _create_story(state: AgentState, action: dict) -> AgentState:
    from agent.tools.jira_tools import create_jira_story
    try:
        result = create_jira_story(
            title=action["title"],
            description=action["description"],
            acceptance_criteria=action.get("acceptance_criteria", ""),
            labels=action.get("labels", []),
        )
        answer = (
            f"✓ Created **{result['key']}** in Jira.\n\n"
            f"[Open in Jira]({result['url']})"
        )
        # Auto-link to feature if this conversation is in a feature session
        feature_id = state.get("feature_id")
        if feature_id:
            try:
                from agent.tools.feature_tools import link_artefact
                link_artefact(
                    feature_id=feature_id,
                    link_type="jira_story",
                    link_id=result["key"],
                    link_url=result["url"],
                    title=action.get("title", result["key"]),
                )
            except Exception:
                pass  # linking failure shouldn't block the response

    except Exception as e:
        answer = f"Failed to create Jira story: {e}"

    return {**state, "answer": answer, "citations": [], "pending_action": None}


def _save_memory(state: AgentState, action: dict) -> AgentState:
    from agent.tools.memory_tool import remember
    try:
        result = remember(
            fact=action["fact"],
            context=action.get("context"),
        )
        answer = f"✓ Saved to team memory (id: {result['memory_id']}).\n\n> {action['fact']}"
        feature_id = state.get("feature_id")
        if feature_id:
            try:
                from agent.tools.feature_tools import link_artefact
                link_artefact(
                    feature_id=feature_id,
                    link_type="memory",
                    link_id=str(result["memory_id"]),
                    link_url=None,
                    title=action["fact"][:80],
                )
            except Exception:
                pass
    except Exception as e:
        answer = f"Failed to save memory: {e}"

    return {**state, "answer": answer, "citations": [], "pending_action": None}


def _update_confluence(state: AgentState, action: dict) -> AgentState:
    from agent.tools.confluence_tools import update_confluence_page
    try:
        result = update_confluence_page(
            page_title=action["page_title"],
            new_content=action["content"],
            append=True,
        )
        page_id = result.get("page_id", "")
        url = result.get("url", "")
        version = result.get("version", "?")
        answer = (
            f"✓ Updated Confluence page **{action['page_title']}** (v{version}).\n\n"
            f"[Open in Confluence]({url})"
        )
        feature_id = state.get("feature_id")
        if feature_id:
            try:
                from agent.tools.feature_tools import link_artefact
                link_artefact(
                    feature_id=feature_id,
                    link_type="confluence_page",
                    link_id=str(page_id),
                    link_url=url,
                    title=action["page_title"],
                )
            except Exception:
                pass
    except Exception as e:
        answer = f"Failed to update Confluence page: {e}"
    return {**state, "answer": answer, "citations": [], "pending_action": None}


def _do_link_artefact(state: AgentState, action: dict) -> AgentState:
    from agent.tools.feature_tools import link_artefact
    feature_id = action.get("feature_id") or state.get("feature_id")
    if not feature_id:
        return {**state, "answer": "No active feature — open a feature session first.", "citations": [], "pending_action": None}
    try:
        link_artefact(
            feature_id=feature_id,
            link_type=action["link_type"],
            link_id=action["link_id"],
            link_url=action.get("link_url"),
            title=action.get("title", action["link_id"]),
        )
        answer = (
            f"✓ Linked **{action['link_id']}** to feature **{feature_id}**.\n\n"
            f"> {action.get('title', '')}\n\n"
            + (f"[Open in Jira]({action['link_url']})" if action.get("link_url") else "")
        )
    except Exception as e:
        answer = f"Failed to link artefact: {e}"
    return {**state, "answer": answer, "citations": [], "pending_action": None}


def _extract_pending_action(state: AgentState) -> dict | None:
    """Find the <!-- PENDING_ACTION: {...} --> marker in the last assistant message."""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage):
            match = re.search(r"<!-- PENDING_ACTION: (.+?) -->", msg.content)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    return None
    return None
