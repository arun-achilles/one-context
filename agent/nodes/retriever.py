"""
Retrieves relevant chunks and team memories from the knowledge base.
Sets needs_clarification=True if top result score is below threshold.
"""
from agent.state import AgentState
from agent.tools.search_knowledge import search_knowledge, CONFIDENCE_THRESHOLD
from agent.tools.memory_tool import search_memory


def retriever_node(state: AgentState) -> AgentState:
    query = state["messages"][-1].content

    chunks = search_knowledge(query)
    memories = search_memory(query, top_k=2)

    # Prepend high-scoring memories as top context
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

    all_chunks = memory_chunks + chunks
    top_score = all_chunks[0]["score"] if all_chunks else 0
    needs_clarification = top_score < CONFIDENCE_THRESHOLD

    return {
        **state,
        "retrieved_chunks": all_chunks,
        "needs_clarification": needs_clarification,
    }
