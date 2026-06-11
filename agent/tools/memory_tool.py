"""
Team memory tool — writes explicit decisions/agreements to the memory table.
Memory is never auto-deleted and always searched alongside knowledge chunks.
"""
from sentence_transformers import SentenceTransformer
from db.connection import cursor

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-mpnet-base-v2")
    return _model


def remember(
    fact: str,
    context: str | None = None,
    author: str | None = None,
    related_sources: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    """
    Persist a team memory (decision, agreement, blocker, key fact).
    Returns the new memory id.
    """
    embedding = _get_model().encode(fact, normalize_embeddings=True).tolist()

    with cursor() as cur:
        cur.execute(
            """INSERT INTO memory (content, context, author, related_sources, tags, embedding)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                fact,
                context,
                author,
                related_sources or [],
                tags or [],
                embedding,
            ),
        )
        row = cur.fetchone()

    return {"memory_id": row["id"], "fact": fact}


def search_memory(query: str, top_k: int = 3) -> list[dict]:
    """Search team memories by semantic similarity."""
    from pgvector.psycopg2 import register_vector
    import psycopg2
    from db.connection import get_connection

    embedding = _get_model().encode(query, normalize_embeddings=True)
    conn = get_connection()
    register_vector(conn)
    cur = conn.cursor()
    cur.execute(
        """SELECT content, context, author, related_sources, tags, created_at,
                  1 - (embedding <=> %s::vector) AS score
           FROM memory
           ORDER BY embedding <=> %s::vector
           LIMIT %s""",
        (embedding.tolist(), embedding.tolist(), top_k),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "content": r[0],
            "context": r[1],
            "author": r[2],
            "related_sources": r[3],
            "tags": r[4],
            "created_at": str(r[5]),
            "score": round(float(r[6]), 3),
        }
        for r in rows
    ]
