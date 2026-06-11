"""
FastAPI backend for One Context.

Run:
    uvicorn agent.api:app --reload --port 8000

Feature endpoints:
    POST  /features                          — create a feature workspace
    GET   /features                          — list all features
    GET   /features/{id}                     — feature detail + links + sessions
    PATCH /features/{id}                     — update name/description/status/jira_epic
    POST   /features/{id}/sessions           — start a new session (returns conversation_id)
    GET    /features/{id}/sessions           — list sessions with summaries
    PATCH  /features/{id}/sessions/{sid}     — update session summary
    DELETE /features/{id}/sessions/{sid}     — delete a session and its messages
    POST  /features/{id}/links               — add a linked artefact
    GET   /features/{id}/links               — list linked artefacts

Conversation endpoints:
    POST /conversations                      — create a bare conversation thread
    GET  /conversations                      — list all conversations
    GET  /conversations/{id}/messages        — message history
    POST /conversations/{id}/chat            — send a message, stream the response

Other:
    POST /webhooks/github | /webhooks/jira
    GET  /health
"""
import json
from datetime import datetime, timezone
from typing import AsyncIterator

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

from agent.graph import get_graph
from agent.tools.feature_tools import (
    create_feature, get_feature, list_features, update_feature,
    create_session, get_sessions, update_session_summary,
    link_artefact, get_links, build_feature_context, get_feature_for_conversation,
)
from db.connection import cursor

app = FastAPI(title="One Context API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class NewConversation(BaseModel):
    topic: str


class ChatRequest(BaseModel):
    message: str
    author: str | None = None   # human team member name (optional)


class ConversationOut(BaseModel):
    id: int
    topic: str
    created_at: datetime


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    author: str | None
    cited_sources: list[str]
    created_at: datetime


# Feature models
class NewFeature(BaseModel):
    name: str
    description: str | None = None
    created_by: str | None = None


class UpdateFeature(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    jira_epic: str | None = None


class FeatureOut(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    jira_epic: str | None
    created_by: str | None
    created_at: datetime


class NewSession(BaseModel):
    role: str | None = None    # po | tech_lead | dev | em
    author: str | None = None


class SessionOut(BaseModel):
    id: int
    feature_id: str
    conversation_id: int
    role: str | None
    author: str | None
    summary: str | None
    created_at: datetime


class SessionStarted(BaseModel):
    session_id: int
    conversation_id: int
    feature_id: str
    feature_context: str


class UpdateSessionSummary(BaseModel):
    summary: str


class NewLink(BaseModel):
    link_type: str
    link_id: str
    link_url: str | None = None
    title: str | None = None


class LinkOut(BaseModel):
    id: int
    link_type: str
    link_id: str
    link_url: str | None
    title: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------

@app.post("/features", response_model=FeatureOut, status_code=201)
def create_feature_endpoint(body: NewFeature):
    row = create_feature(body.name, body.description, body.created_by)
    return FeatureOut(**row)


@app.get("/features", response_model=list[dict])
def list_features_endpoint():
    return list_features()


@app.get("/features/{feature_id}")
def get_feature_endpoint(feature_id: str):
    feature = get_feature(feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    feature["sessions"] = get_sessions(feature_id)
    feature["links"] = get_links(feature_id)
    feature["context"] = build_feature_context(feature_id)
    return feature


@app.patch("/features/{feature_id}", response_model=FeatureOut)
def update_feature_endpoint(feature_id: str, body: UpdateFeature):
    row = update_feature(feature_id, **body.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(status_code=404, detail="Feature not found")
    return FeatureOut(**row)


@app.post("/features/{feature_id}/sessions", response_model=SessionStarted, status_code=201)
def start_session(feature_id: str, body: NewSession):
    feature = get_feature(feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    # Create conversation with feature name as topic
    with cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (topic) VALUES (%s) RETURNING id",
            (feature["name"],),
        )
        conv_id = cur.fetchone()["id"]

    session = create_session(feature_id, conv_id, body.role, body.author)
    context = build_feature_context(feature_id)

    return SessionStarted(
        session_id=session["id"],
        conversation_id=conv_id,
        feature_id=feature_id,
        feature_context=context,
    )


@app.get("/features/{feature_id}/sessions", response_model=list[SessionOut])
def list_sessions(feature_id: str):
    if not get_feature(feature_id):
        raise HTTPException(status_code=404, detail="Feature not found")
    return [SessionOut(**s) for s in get_sessions(feature_id)]


@app.patch("/features/{feature_id}/sessions/{session_id}", status_code=204)
def update_session(feature_id: str, session_id: int, body: UpdateSessionSummary):
    update_session_summary(session_id, body.summary)


@app.delete("/features/{feature_id}/sessions/{session_id}", status_code=204)
def delete_session(feature_id: str, session_id: int):
    with cursor() as cur:
        # Get the conversation_id for this session so we can clean up messages too
        cur.execute(
            "SELECT conversation_id FROM feature_sessions WHERE id = %s AND feature_id = %s",
            (session_id, feature_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        conv_id = row["conversation_id"]
        cur.execute("DELETE FROM messages WHERE conversation_id = %s", (conv_id,))
        cur.execute("DELETE FROM feature_sessions WHERE id = %s", (session_id,))
        cur.execute("DELETE FROM conversations WHERE id = %s", (conv_id,))


@app.post("/features/{feature_id}/links", response_model=LinkOut, status_code=201)
def add_link(feature_id: str, body: NewLink):
    if not get_feature(feature_id):
        raise HTTPException(status_code=404, detail="Feature not found")
    row = link_artefact(feature_id, body.link_type, body.link_id, body.link_url, body.title)
    return LinkOut(**row)


@app.get("/features/{feature_id}/links", response_model=list[LinkOut])
def list_links(feature_id: str):
    if not get_feature(feature_id):
        raise HTTPException(status_code=404, detail="Feature not found")
    return [LinkOut(**lnk) for lnk in get_links(feature_id)]


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@app.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(body: NewConversation):
    with cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (topic) VALUES (%s) RETURNING id, topic, created_at",
            (body.topic,),
        )
        row = cur.fetchone()
    return ConversationOut(**row)


@app.get("/conversations", response_model=list[ConversationOut])
def list_conversations():
    with cursor() as cur:
        cur.execute("SELECT id, topic, created_at FROM conversations ORDER BY created_at DESC LIMIT 100")
        return [ConversationOut(**row) for row in cur.fetchall()]


@app.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def get_messages(conversation_id: int):
    with cursor() as cur:
        cur.execute("SELECT id FROM conversations WHERE id = %s", (conversation_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")
        cur.execute(
            """SELECT id, role, content, author, cited_sources, created_at
               FROM messages WHERE conversation_id = %s ORDER BY created_at""",
            (conversation_id,),
        )
        return [MessageOut(**row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Chat — streaming
# ---------------------------------------------------------------------------

@app.post("/conversations/{conversation_id}/chat")
async def chat(conversation_id: int, body: ChatRequest):
    """
    Send a message and stream back the assistant's response as Server-Sent Events.

    Event format:
        data: {"type": "token",    "content": "..."}
        data: {"type": "sources",  "sources": [...]}
        data: {"type": "done"}
        data: {"type": "error",    "detail": "..."}
    """
    with cursor() as cur:
        cur.execute("SELECT id FROM conversations WHERE id = %s", (conversation_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Conversation not found")

    return StreamingResponse(
        _stream_chat(conversation_id, body.message, body.author),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_chat(
    conversation_id: int,
    user_message: str,
    author: str | None,
) -> AsyncIterator[str]:
    try:
        # 1. Persist the user message
        with cursor() as cur:
            cur.execute(
                """INSERT INTO messages (conversation_id, role, content, author)
                   VALUES (%s, 'user', %s, %s)""",
                (conversation_id, user_message, author),
            )
            # Load prior history for multi-turn context
            cur.execute(
                """SELECT role, content FROM messages
                   WHERE conversation_id = %s ORDER BY created_at""",
                (conversation_id,),
            )
            history_rows = cur.fetchall()

        # 2. Check if this conversation belongs to a Feature session
        feature_id = get_feature_for_conversation(conversation_id)
        feature_context = build_feature_context(feature_id) if feature_id else None

        # 3. Build LangChain message history
        # Prepend feature context as a system-style human message if present
        history = []
        if feature_context:
            history.append(HumanMessage(content=f"[FEATURE CONTEXT]\n{feature_context}"))
            history.append(AIMessage(content="Understood. I'm working in this feature context."))
        for row in history_rows:
            if row["role"] == "user":
                history.append(HumanMessage(content=row["content"]))
            else:
                history.append(AIMessage(content=row["content"]))

        # 4. Run the LangGraph agent (synchronous — graph.invoke is blocking)
        import asyncio
        graph = get_graph()
        loop = asyncio.get_event_loop()
        initial_state = {
            "messages": history,
            "feature_id": feature_id,
            "intent": None,
            "retrieved_chunks": [],
            "answer": None,
            "citations": [],
            "needs_clarification": False,
            "pending_action": None,
        }
        result = await loop.run_in_executor(
            None,
            lambda: graph.invoke(initial_state),
        )

        # 4. Extract answer and citations from final state
        final_message = result["messages"][-1]
        answer = final_message.content if hasattr(final_message, "content") else str(final_message)
        citations = result.get("citations", [])
        cited_urls = [c["url"] for c in citations if c.get("url")]

        # 5. Stream the answer token by token (word-level — graph doesn't stream internally yet)
        words = answer.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == 0 else " " + word
            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

        # 6. Send sources
        if cited_urls:
            yield f"data: {json.dumps({'type': 'sources', 'sources': cited_urls})}\n\n"

        # 7. Persist the assistant message
        with cursor() as cur:
            cur.execute(
                """INSERT INTO messages (conversation_id, role, content, cited_sources)
                   VALUES (%s, 'assistant', %s, %s)""",
                (conversation_id, answer, cited_urls),
            )

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"


# ---------------------------------------------------------------------------
# Webhooks (stubs — wired to Celery tasks in Phase 3)
# ---------------------------------------------------------------------------

@app.post("/webhooks/github", status_code=202)
async def webhook_github(payload: dict):
    """
    Receives GitHub PR merge events.
    Triggers selective re-indexing of changed files.
    Full implementation: one-context-gnp
    """
    action = payload.get("action")
    pr = payload.get("pull_request", {})
    merged = pr.get("merged", False)

    if action != "closed" or not merged:
        return {"status": "ignored"}

    repo = payload.get("repository", {}).get("full_name", "unknown")
    pr_number = pr.get("number")
    changed_files = [f["filename"] for f in payload.get("pull_request", {}).get("files", [])]

    from agent.tasks import sync_pr
    sync_pr.delay(repo, pr_number, changed_files)
    return {"status": "queued", "repo": repo, "pr": pr_number}


@app.post("/webhooks/jira", status_code=202)
async def webhook_jira(payload: dict):
    """
    Receives Jira issue update events.
    Triggers re-sync of the updated issue.
    """
    issue_key = payload.get("issue", {}).get("key")
    source_type = "jira"

    from agent.tasks import sync_issue
    sync_issue.delay(source_type, issue_key)
    return {"status": "queued", "issue": issue_key}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    try:
        with cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent.api:app", host="0.0.0.0", port=8000, reload=True)
