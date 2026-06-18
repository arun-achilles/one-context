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
import re
import os
from datetime import datetime, timezone
from typing import AsyncIterator
import psycopg2

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

from agent.graph import get_graph
from agent.model_policy import call_model
from agent.tools.feature_tools import (
    create_feature, get_feature, list_features, update_feature,
    create_session, get_sessions, update_session_summary,
    link_artefact, get_links, build_feature_context, get_feature_for_conversation,
)
from db.connection import cursor

app = FastAPI(title="One Context API", version="0.1.0")

_ENABLE_HISTORY_COMPRESSION = os.getenv("ENABLE_HISTORY_COMPRESSION", "0").strip() != "0"

_PENDING_MARKER_RE = re.compile(r"\n*<!-- PENDING_ACTION: .+? -->", re.DOTALL)


def _ensure_conversation_state_columns() -> None:
    """Add pending-state and structured-memory columns to conversations if needed."""
    with cursor() as cur:
        cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_action JSONB")
        cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_options JSONB")
        cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_question TEXT")
        cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pending_updated_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS session_goal TEXT")
        cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS session_decisions JSONB")
        cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS session_open_questions JSONB")
        cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS session_next_actions JSONB")
        cur.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS session_memory_updated_at TIMESTAMPTZ")


def _coerce_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()][:8]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _load_pending_context(conversation_id: int) -> dict | None:
    """Load persisted pending context + structured memory for a conversation."""
    try:
        with cursor() as cur:
            cur.execute(
                """SELECT pending_action, pending_options, pending_question,
                          session_goal, session_decisions, session_open_questions, session_next_actions
                   FROM conversations WHERE id = %s""",
                (conversation_id,),
            )
            row = cur.fetchone()
    except psycopg2.errors.UndefinedColumn:
        _ensure_conversation_state_columns()
        with cursor() as cur:
            cur.execute(
                """SELECT pending_action, pending_options, pending_question,
                          session_goal, session_decisions, session_open_questions, session_next_actions
                   FROM conversations WHERE id = %s""",
                (conversation_id,),
            )
            row = cur.fetchone()

    if not row:
        return None

    pending_action = row.get("pending_action")
    pending_options = row.get("pending_options") or []
    pending_question = row.get("pending_question")
    structured_memory = {
        "goal": (row.get("session_goal") or "").strip(),
        "decisions": _coerce_str_list(row.get("session_decisions")),
        "open_questions": _coerce_str_list(row.get("session_open_questions")),
        "next_actions": _coerce_str_list(row.get("session_next_actions")),
    }

    has_pending = bool(pending_action or pending_options or pending_question)
    has_memory = bool(
        structured_memory["goal"]
        or structured_memory["decisions"]
        or structured_memory["open_questions"]
        or structured_memory["next_actions"]
    )
    if not has_pending and not has_memory:
        return None

    return {
        "pending_action": pending_action,
        "pending_options": pending_options,
        "pending_question": pending_question,
        "structured_memory": structured_memory,
    }


def _strip_pending_marker(text: str) -> str:
    return _PENDING_MARKER_RE.sub("", text or "").strip()


def _normalize_structured_memory(memory: dict | None) -> dict:
    memory = memory or {}
    return {
        "goal": str(memory.get("goal") or "").strip()[:300],
        "decisions": _coerce_str_list(memory.get("decisions")),
        "open_questions": _coerce_str_list(memory.get("open_questions")),
        "next_actions": _coerce_str_list(memory.get("next_actions")),
    }


def _update_structured_memory(
    existing_memory: dict | None,
    user_message: str,
    assistant_answer: str,
    session_context: str,
) -> dict | None:
    """Update rolling structured memory from the latest turn using a cheap model."""
    try:
        import anthropic as _anthropic

        current = _normalize_structured_memory(existing_memory)
        clean_answer = _strip_pending_marker(assistant_answer)[:1200]
        clean_user = (user_message or "").strip()[:900]
        clean_session = (session_context or "").strip()[:1800]

        system = (
            "Update rolling conversation memory. Return JSON only with keys: "
            "goal (string), decisions (array), open_questions (array), next_actions (array). "
            "Keep entries concise, factual, and deduplicated. "
            "Do not invent details not in the turn/context."
        )

        prompt = json.dumps(
            {
                "existing_memory": current,
                "latest_user_message": clean_user,
                "latest_assistant_message": clean_answer,
                "session_context": clean_session,
            },
            ensure_ascii=True,
        )

        client = _anthropic.Anthropic()
        resp = call_model(
            client,
            task="memory_update",
            max_tokens=450,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw).strip()
        parsed = json.loads(raw)
        return _normalize_structured_memory(parsed)
    except Exception:
        return _normalize_structured_memory(existing_memory)


def _persist_structured_memory(conversation_id: int, memory: dict | None) -> None:
    """Persist rolling structured memory fields onto conversations."""
    mem = _normalize_structured_memory(memory)
    try:
        with cursor() as cur:
            cur.execute(
                """UPDATE conversations
                   SET session_goal = %s,
                       session_decisions = %s::jsonb,
                       session_open_questions = %s::jsonb,
                       session_next_actions = %s::jsonb,
                       session_memory_updated_at = now()
                   WHERE id = %s""",
                (
                    mem.get("goal") or None,
                    json.dumps(mem.get("decisions", [])),
                    json.dumps(mem.get("open_questions", [])),
                    json.dumps(mem.get("next_actions", [])),
                    conversation_id,
                ),
            )
    except psycopg2.errors.UndefinedColumn:
        _ensure_conversation_state_columns()
        with cursor() as cur:
            cur.execute(
                """UPDATE conversations
                   SET session_goal = %s,
                       session_decisions = %s::jsonb,
                       session_open_questions = %s::jsonb,
                       session_next_actions = %s::jsonb,
                       session_memory_updated_at = now()
                   WHERE id = %s""",
                (
                    mem.get("goal") or None,
                    json.dumps(mem.get("decisions", [])),
                    json.dumps(mem.get("open_questions", [])),
                    json.dumps(mem.get("next_actions", [])),
                    conversation_id,
                ),
            )


def _extract_pending_options(answer: str) -> list[str]:
    """Extract option bullets/numbered lines for ambiguous follow-up handling."""
    clean = _PENDING_MARKER_RE.sub("", answer or "")
    options: list[str] = []
    for raw in clean.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- ") or line.startswith("• "):
            candidate = line[2:].strip()
            if candidate:
                options.append(candidate)
            continue
        m = re.match(r"^\d+[\.)]\s+(.+)$", line)
        if m:
            candidate = m.group(1).strip()
            if candidate:
                options.append(candidate)

    # Keep order while deduplicating exact matches
    seen = set()
    deduped = []
    for opt in options:
        if opt not in seen:
            seen.add(opt)
            deduped.append(opt)
    return deduped[:6]


def _extract_pending_question(answer: str) -> str | None:
    """Capture the lead question/prompt from the assistant response."""
    clean = _PENDING_MARKER_RE.sub("", answer or "")
    for raw in clean.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- ") or line.startswith("• "):
            continue
        if re.match(r"^\d+[\.)]\s+", line):
            continue
        if line.lower().startswith("sources"):
            continue
        return line[:300]
    return None


def _persist_pending_context(conversation_id: int, pending_action: dict | None, answer: str) -> None:
    """Persist pending action + lightweight disambiguation context to conversations."""
    pending_options = _extract_pending_options(answer) if pending_action else []
    pending_question = _extract_pending_question(answer) if pending_action else None

    payload = json.dumps(pending_action) if pending_action else None

    try:
        with cursor() as cur:
            cur.execute(
                """UPDATE conversations
                   SET pending_action = %s::jsonb,
                       pending_options = %s::jsonb,
                       pending_question = %s,
                       pending_updated_at = now()
                   WHERE id = %s""",
                (payload, json.dumps(pending_options), pending_question, conversation_id),
            )
    except psycopg2.errors.UndefinedColumn:
        _ensure_conversation_state_columns()
        with cursor() as cur:
            cur.execute(
                """UPDATE conversations
                   SET pending_action = %s::jsonb,
                       pending_options = %s::jsonb,
                       pending_question = %s,
                       pending_updated_at = now()
                   WHERE id = %s""",
                (payload, json.dumps(pending_options), pending_question, conversation_id),
            )


def _infer_source_type(content_type: str | None, url: str, label: str | None = None) -> str:
    """Normalize source type for UI badges, with URL/label fallback inference."""
    ctype = (content_type or "").strip().lower()
    if ctype and ctype not in ("knowledge", "unknown"):
        return ctype

    u = (url or "").lower()
    l = (label or "").lower()
    if "/browse/" in u or re.search(r"/[a-z][a-z0-9]+-\d+", u):
        return "jira_issue"
    if "/wiki/" in u:
        return "confluence_page"
    if "/pull/" in u or "github.com" in u:
        return "feature_link"
    if "session summary" in l:
        return "feature_session_summary"
    if "team memory" in l:
        return "team_memory"
    return "knowledge"

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

    # Auto-summarize the most recent session that hasn't been summarized yet.
    # This ensures when a new session opens, prior session decisions are captured
    # and will be injected via feature context into future sessions.
    _auto_summarize_previous_session(feature_id)

    # Create conversation with feature name as topic
    with cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (topic) VALUES (%s) RETURNING id",
            (feature["name"],),
        )
        conv_id = cur.fetchone()["id"]

    session = create_session(feature_id, conv_id, body.role, body.author)
    context = build_feature_context(feature_id)

    # Persist context as initial messages — loaded by the agent on every turn,
    # filtered out in the UI via [FEATURE CONTEXT] prefix check.
    if context:
        with cursor() as cur:
            cur.execute(
                "INSERT INTO messages (conversation_id, role, content, author) VALUES (%s, 'user', %s, 'system')",
                (conv_id, f"[FEATURE CONTEXT]\n{context}"),
            )
            cur.execute(
                "INSERT INTO messages (conversation_id, role, content, author) VALUES (%s, 'assistant', %s, 'system')",
                (conv_id, "[FEATURE CONTEXT ACK]"),
            )

    return SessionStarted(
        session_id=session["id"],
        conversation_id=conv_id,
        feature_id=feature_id,
        feature_context=context,
    )


def _auto_summarize_previous_session(feature_id: str) -> None:
    """Find the most recent session with no summary and generate one for it."""
    sessions = get_sessions(feature_id)
    unsummarized = [s for s in sessions if not s.get("summary")]
    if not unsummarized:
        return
    # Summarize the most recent unsummarized session
    target = unsummarized[-1]
    conv_id = target["conversation_id"]
    session_id = target["id"]
    try:
        from agent.nodes.reasoner import generate_session_summary
        summary = generate_session_summary(conv_id)
        if summary:
            update_session_summary(session_id, summary)
    except Exception:
        pass  # never block session creation on summary failure


@app.get("/features/{feature_id}/sessions", response_model=list[SessionOut])
def list_sessions(feature_id: str):
    if not get_feature(feature_id):
        raise HTTPException(status_code=404, detail="Feature not found")
    return [SessionOut(**s) for s in get_sessions(feature_id)]


@app.post("/features/{feature_id}/sessions/{session_id}/summarize", status_code=200)
def summarize_session(feature_id: str, session_id: int):
    """
    Explicitly generate and save a summary for a session.
    Useful when a user ends a session from the UI and wants it captured immediately.
    """
    with cursor() as cur:
        cur.execute(
            "SELECT conversation_id FROM feature_sessions WHERE id = %s AND feature_id = %s",
            (session_id, feature_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        conv_id = row["conversation_id"]

    from agent.nodes.reasoner import generate_session_summary
    summary = generate_session_summary(conv_id)
    if summary:
        update_session_summary(session_id, summary)
    return {"session_id": session_id, "summary": summary or ""}


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


def _compress_history(rows: list) -> str:
    """
    Produce a compact summary of older conversation turns using Claude Haiku.
    Called only when there are more than RECENT_TURNS * 2 messages in a conversation.
    Returns empty string on failure so it never blocks the main flow.
    """
    import re as _re
    import anthropic as _anthropic

    _client = _anthropic.Anthropic()
    COMPRESS_SYSTEM = (
        "You are a conversation summarizer. Given a chat transcript, produce a concise summary "
        "(3-6 bullet points) covering: decisions made, questions asked, answers given, and any "
        "pending actions. Be specific. Use past tense. Do not invent anything not in the transcript."
    )
    lines = []
    for row in rows:
        content = row["content"] or ""
        content = _re.sub(r"<!-- PENDING_ACTION:.*?-->", "", content, flags=_re.DOTALL).strip()
        if not content or content.startswith("[FEATURE CONTEXT"):
            continue
        label = "User" if row["role"] == "user" else "Assistant"
        lines.append(f"{label}: {content[:400]}")

    if not lines:
        return ""

    transcript = "\n\n".join(lines[-20:])
    try:
        resp = call_model(
            _client,
            task="conversation_compress",
            max_tokens=350,
            system=COMPRESS_SYSTEM,
            messages=[{"role": "user", "content": f"Transcript:\n\n{transcript}"}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return ""


def _build_session_context(older_summary: str, recent_rows: list, structured_memory: dict | None = None) -> str:
    """Create a compact session-wide context snapshot shared by all nodes."""
    parts = []
    mem = _normalize_structured_memory(structured_memory)
    if mem["goal"] or mem["decisions"] or mem["open_questions"] or mem["next_actions"]:
        memory_block = [f"Goal: {mem['goal']}" if mem["goal"] else "Goal: (not set)"]
        if mem["decisions"]:
            memory_block.append("Decisions: " + " | ".join(mem["decisions"][:5]))
        if mem["open_questions"]:
            memory_block.append("Open questions: " + " | ".join(mem["open_questions"][:5]))
        if mem["next_actions"]:
            memory_block.append("Next actions: " + " | ".join(mem["next_actions"][:5]))
        parts.append("Structured memory:\n" + "\n".join(memory_block))

    if older_summary:
        parts.append(f"Earlier session summary:\n{older_summary}")

    recent_lines = []
    for row in recent_rows[-8:]:
        content = (row.get("content") or "").strip()
        if not content or content.startswith("[FEATURE CONTEXT") or content.startswith("[FEATURE CONTEXT ACK]"):
            continue
        content = _PENDING_MARKER_RE.sub("", content).strip()
        if not content:
            continue
        label = "User" if row.get("role") == "user" else "Assistant"
        recent_lines.append(f"{label}: {content[:300]}")

    if recent_lines:
        parts.append("Recent conversation:\n" + "\n".join(recent_lines))

    return "\n\n".join(parts)[:3000]


async def _stream_chat(
    conversation_id: int,
    user_message: str,
    author: str | None,
) -> AsyncIterator[str]:
    try:
        pending_context = _load_pending_context(conversation_id)
        structured_memory = (pending_context or {}).get("structured_memory") if pending_context else None

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

        # 2. Check if this conversation belongs to a Feature session (for state)
        feature_id = get_feature_for_conversation(conversation_id)
        role = None
        if feature_id:
            sessions = get_sessions(feature_id)
            session = next((s for s in sessions if s["conversation_id"] == conversation_id), None)
            role = session["role"] if session else None

        # 3. Build LangChain message history from DB with compression.
        # Keep feature bootstrap messages + last RECENT_TURNS full turns verbatim.
        # Older turns are compressed into a single summary prefix to avoid
        # token bloat and context dilution on long conversations.
        RECENT_TURNS = 10  # each turn = 1 user + 1 assistant message pair

        bootstrap_rows = []
        real_rows = []
        for row in history_rows:
            content = row["content"] or ""
            if content.startswith("[FEATURE CONTEXT") or content.startswith("[FEATURE CONTEXT ACK]"):
                bootstrap_rows.append(row)
            else:
                real_rows.append(row)

        # Split real rows into older (to compress) and recent (keep verbatim)
        cutoff = max(0, len(real_rows) - RECENT_TURNS * 2)
        old_rows = real_rows[:cutoff]
        recent_rows = real_rows[cutoff:]

        history = []

        # Feature context is injected via the system prompt in _build_system() inside the
        # reasoner. Do NOT also add bootstrap messages as conversation turns — that is the
        # duplication bug that causes token bloat and confusing repeated context.
        # (bootstrap_rows stay in DB for UI filtering but are excluded from agent input)

        compressed = ""

        # Compress older turns only when explicitly enabled. This avoids an extra
        # LLM call on the critical path for every turn.
        if _ENABLE_HISTORY_COMPRESSION and old_rows:
            compressed = _compress_history(old_rows)
            if compressed:
                history.append(HumanMessage(content=f"[EARLIER CONVERSATION SUMMARY]\n{compressed}"))
                history.append(AIMessage(content="Understood. I have context from earlier in this conversation."))

        session_context = _build_session_context(compressed, recent_rows, structured_memory)

        # Append recent turns verbatim
        for row in recent_rows:
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
            "conversation_id": conversation_id,
            "feature_id": feature_id,
            "role": role,
            "intent": None,
            "retrieved_chunks": [],
            "answer": None,
            "citations": [],
            "needs_clarification": False,
            "pending_action": (pending_context or {}).get("pending_action") if pending_context else None,
            "pending_context": pending_context,
            "resolved_query": None,
            "session_context": session_context,
            "structured_memory": _normalize_structured_memory(structured_memory),
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

        # 6. Send enriched source objects so UI can show type badges + labels
        if citations:
            rich_sources = [
                {
                    "url": c.get("url", ""),
                    "label": c.get("label", ""),
                    "content_type": _infer_source_type(
                        c.get("content_type"),
                        c.get("url", ""),
                        c.get("label", ""),
                    ),
                    "score": c.get("score", 0),
                }
                for c in citations if c.get("url")
            ]
            yield f"data: {json.dumps({'type': 'sources', 'sources': cited_urls, 'rich_sources': rich_sources})}\n\n"

        # 7. Persist the assistant message
        with cursor() as cur:
            cur.execute(
                """INSERT INTO messages (conversation_id, role, content, cited_sources)
                   VALUES (%s, 'assistant', %s, %s)""",
                (conversation_id, answer, cited_urls),
            )

        # 8. Persist pending conversation state for robust follow-up handling
        _persist_pending_context(conversation_id, result.get("pending_action"), answer)

        # 9. Update rolling structured session memory off the critical path.
        async def _background_memory_update():
            import asyncio as _asyncio
            loop = _asyncio.get_running_loop()
            updated_memory = await loop.run_in_executor(
                None,
                _update_structured_memory,
                result.get("structured_memory") or structured_memory,
                user_message,
                answer,
                session_context,
            )
            await loop.run_in_executor(
                None,
                _persist_structured_memory,
                conversation_id,
                updated_memory,
            )

        try:
            import asyncio as _asyncio
            _asyncio.create_task(_background_memory_update())
        except Exception:
            pass

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
