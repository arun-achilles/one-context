from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # full conversation history
    intent: str | None                        # qa | pipeline_query | story_draft | remember | confirm_action | clarify
    retrieved_chunks: list[dict]              # vector search results
    answer: str | None                        # final answer text
    citations: list[dict]                     # [{title, url, score}]
    needs_clarification: bool
    pending_action: dict | None               # write action awaiting user confirmation
    feature_id: str | None                    # set if conversation belongs to a feature session
    role: str | None                           # session role: po | ba | tech_lead | dev | qa
