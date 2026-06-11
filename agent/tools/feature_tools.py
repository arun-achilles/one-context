"""
Feature workspace tools — create, retrieve, and link artefacts to Features.

A Feature is a named, persistent workspace shared across PO, Tech Lead, and Dev.
It exists before a Jira epic and accumulates all linked artefacts as work progresses.
"""
import re

from db.connection import cursor


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------

def create_feature(name: str, description: str | None = None, created_by: str | None = None) -> dict:
    with cursor() as cur:
        cur.execute(
            """INSERT INTO features (name, description, created_by)
               VALUES (%s, %s, %s)
               RETURNING id, name, description, status, jira_epic, created_by, created_at""",
            (name, description, created_by),
        )
        return dict(cur.fetchone())


def get_feature(feature_id: str) -> dict | None:
    with cursor() as cur:
        cur.execute(
            "SELECT id, name, description, status, jira_epic, created_by, created_at, updated_at FROM features WHERE id = %s",
            (feature_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def list_features() -> list[dict]:
    with cursor() as cur:
        cur.execute(
            """SELECT f.id, f.name, f.description, f.status, f.jira_epic, f.created_by, f.created_at,
                      COUNT(DISTINCT fs.id) AS session_count,
                      COUNT(DISTINCT fl.id) AS link_count
               FROM features f
               LEFT JOIN feature_sessions fs ON fs.feature_id = f.id
               LEFT JOIN feature_links fl ON fl.feature_id = f.id
               GROUP BY f.id
               ORDER BY f.updated_at DESC""",
        )
        return [dict(r) for r in cur.fetchall()]


def update_feature(feature_id: str, **kwargs) -> dict | None:
    allowed = {"name", "description", "status", "jira_epic"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return get_feature(feature_id)
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [feature_id]
    with cursor() as cur:
        cur.execute(
            f"UPDATE features SET {set_clause}, updated_at = now() WHERE id = %s RETURNING id, name, description, status, jira_epic, created_by, created_at, updated_at",
            values,
        )
        row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def create_session(feature_id: str, conversation_id: int, role: str | None = None, author: str | None = None) -> dict:
    with cursor() as cur:
        cur.execute(
            """INSERT INTO feature_sessions (feature_id, conversation_id, role, author)
               VALUES (%s, %s, %s, %s)
               RETURNING id, feature_id, conversation_id, role, author, created_at""",
            (feature_id, conversation_id, role, author),
        )
        return dict(cur.fetchone())


def get_sessions(feature_id: str) -> list[dict]:
    with cursor() as cur:
        cur.execute(
            """SELECT fs.id, fs.feature_id, fs.conversation_id, fs.role, fs.author,
                      fs.summary, fs.created_at
               FROM feature_sessions fs
               WHERE fs.feature_id = %s
               ORDER BY fs.created_at""",
            (feature_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def update_session_summary(session_id: int, summary: str) -> None:
    with cursor() as cur:
        cur.execute("UPDATE feature_sessions SET summary = %s WHERE id = %s", (summary, session_id))


def get_feature_for_conversation(conversation_id: int) -> str | None:
    """Reverse lookup: given a conversation_id, return its feature_id (or None)."""
    with cursor() as cur:
        cur.execute(
            "SELECT feature_id FROM feature_sessions WHERE conversation_id = %s LIMIT 1",
            (conversation_id,),
        )
        row = cur.fetchone()
    return row["feature_id"] if row else None


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

def link_artefact(
    feature_id: str,
    link_type: str,
    link_id: str,
    link_url: str | None = None,
    title: str | None = None,
) -> dict:
    with cursor() as cur:
        cur.execute(
            """INSERT INTO feature_links (feature_id, link_type, link_id, link_url, title)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING
               RETURNING id, feature_id, link_type, link_id, link_url, title""",
            (feature_id, link_type, link_id, link_url, title),
        )
        row = cur.fetchone()
        if not row:
            # Already existed — fetch it
            cur.execute(
                "SELECT id, feature_id, link_type, link_id, link_url, title FROM feature_links WHERE feature_id=%s AND link_id=%s",
                (feature_id, link_id),
            )
            row = cur.fetchone()
    return dict(row) if row else {}


def get_links(feature_id: str) -> list[dict]:
    with cursor() as cur:
        cur.execute(
            """SELECT id, link_type, link_id, link_url, title, created_at
               FROM feature_links WHERE feature_id = %s ORDER BY created_at""",
            (feature_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_feature_retrieval_chunks(
    feature_id: str,
    query: str,
    *,
    session_limit: int = 5,
    link_limit: int = 12,
) -> list[dict]:
    """
    Build high-priority retrieval chunks from feature-local context.

    These chunks are intended to be searched before global vector knowledge
    so active feature conversations stay grounded in linked artefacts and
    prior session decisions.
    """
    q_tokens = _tokenize(query)
    chunks: list[dict] = []

    # 1) Prior feature session summaries
    with cursor() as cur:
        cur.execute(
            """SELECT role, author, summary, created_at
               FROM feature_sessions
               WHERE feature_id = %s AND summary IS NOT NULL AND summary <> ''
               ORDER BY created_at DESC
               LIMIT %s""",
            (feature_id, session_limit),
        )
        summaries = cur.fetchall()

    for row in summaries:
        role = row.get("role") or "unknown"
        author = row.get("author") or "unknown"
        summary = row.get("summary") or ""
        created = str(row.get("created_at") or "")[:10]
        match_boost = _match_boost(q_tokens, summary)
        score = min(0.98, 0.86 + match_boost)
        chunks.append(
            {
                "content": f"[Feature session summary] {created} ({role}, {author})\n{summary}",
                "url": "",
                "content_type": "feature_session_summary",
                "tags": ["feature", "session", role],
                "score": round(score, 3),
                "high_confidence": True,
            }
        )

    # 2) Linked artefacts for this feature
    with cursor() as cur:
        cur.execute(
            """SELECT link_type, link_id, link_url, title, created_at
               FROM feature_links
               WHERE feature_id = %s
               ORDER BY created_at DESC
               LIMIT %s""",
            (feature_id, link_limit),
        )
        links = cur.fetchall()

    for row in links:
        link_type = row.get("link_type") or "artefact"
        link_id = row.get("link_id") or ""
        link_url = row.get("link_url") or ""
        title = row.get("title") or link_id
        created = str(row.get("created_at") or "")[:10]

        relevance_text = f"{title} {link_id} {link_type}"
        match_boost = _match_boost(q_tokens, relevance_text)
        if link_id and link_id.lower() in query.lower():
            match_boost = max(match_boost, 0.12)

        score = min(0.97, 0.82 + match_boost)
        chunks.append(
            {
                "content": (
                    f"[Feature linked artefact] {created}\n"
                    f"Type: {link_type}\n"
                    f"Ref: {link_id}\n"
                    f"Title: {title}"
                ),
                "url": link_url,
                "content_type": "feature_link",
                "tags": ["feature", "linked_artefact", link_type],
                "score": round(score, 3),
                "high_confidence": True,
            }
        )

    # Keep strongest feature-local chunks first.
    chunks.sort(key=lambda c: c.get("score", 0), reverse=True)
    return chunks


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_\-]+", (text or "").lower()))


def _match_boost(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = _tokenize(text)
    if not text_tokens:
        return 0.0
    overlap = len(query_tokens.intersection(text_tokens))
    if overlap == 0:
        return 0.0
    # Cap boost so feature chunks stay strong but don't fully dominate certainty.
    return min(0.15, 0.03 * overlap)


# ---------------------------------------------------------------------------
# Context builder — injected into agent system prompt for feature sessions
# ---------------------------------------------------------------------------

def build_feature_context(feature_id: str) -> str:
    feature = get_feature(feature_id)
    if not feature:
        return ""

    lines = [
        f"=== FEATURE WORKSPACE ===",
        f"Feature: {feature['name']} ({feature['id']}) — {feature['status']}",
    ]
    if feature.get("description"):
        lines.append(f"Description: {feature['description']}")
    if feature.get("jira_epic"):
        lines.append(f"Jira epic: {feature['jira_epic']}")

    sessions = get_sessions(feature_id)
    completed = [s for s in sessions if s.get("summary")]
    if completed:
        lines.append("\nPrior sessions:")
        for s in completed[-5:]:   # last 5 sessions
            date = str(s["created_at"])[:10]
            role = s.get("role") or "unknown"
            author = s.get("author") or ""
            who = f"{role}, {author}".strip(", ")
            lines.append(f"  • {date} ({who}): {s['summary']}")

    links = get_links(feature_id)
    if links:
        lines.append("\nLinked artefacts:")
        by_type: dict[str, list] = {}
        for lnk in links:
            by_type.setdefault(lnk["link_type"], []).append(lnk)
        for ltype, items in by_type.items():
            refs = ", ".join(
                (lnk.get("title") or lnk["link_id"]) for lnk in items
            )
            lines.append(f"  • {ltype.replace('_', ' ').title()}: {refs}")

    lines.append("=========================")
    return "\n".join(lines)
