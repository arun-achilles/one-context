from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.router import router_node
from agent.nodes.retriever import retriever_node
from agent.nodes.reasoner import reasoner_node
from agent.nodes.act import act_node
from agent.nodes.responder import responder_node


def _route_after_route(state: AgentState) -> str:
    """After routing, skip retrieve+reason for confirmations — go straight to act.
    Skip retrieval for remember, confluence_update, and create_confluence — no knowledge lookup needed."""
    intent = state.get("intent")
    if intent == "confirm_action":
        return "act"
    if intent in ("remember", "confluence_update", "create_confluence"):
        return "reason"
    return "retrieve"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("route", router_node)
    graph.add_node("retrieve", retriever_node)
    graph.add_node("reason", reasoner_node)
    graph.add_node("act", act_node)
    graph.add_node("respond", responder_node)

    graph.set_entry_point("route")

    # After routing: confirmations skip straight to act; everything else retrieves first
    graph.add_conditional_edges(
        "route",
        _route_after_route,
        {"act": "act", "retrieve": "retrieve", "reason": "reason"},
    )

    graph.add_edge("retrieve", "reason")
    graph.add_edge("reason", "respond")
    graph.add_edge("act", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
