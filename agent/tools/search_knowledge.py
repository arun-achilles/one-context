"""
Vector search against the knowledge base.
Returns ranked chunks with scores and source URLs.
"""
import numpy as np
from sentence_transformers import SentenceTransformer
from pgvector.psycopg2 import register_vector
from db.connection import get_connection

CONFIDENCE_THRESHOLD = 0.45  # below this → flag as low confidence
TOP_K = 6

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-mpnet-base-v2")
    return _model


def search_knowledge(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Returns up to top_k chunks ordered by cosine similarity.
    Each result: {content, url, content_type, tags, score, high_confidence}
    """
    embedding = _get_model().encode(query, normalize_embeddings=True)

    conn = get_connection()
    register_vector(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT content, url, content_type, tags,
               1 - (embedding <=> %s::vector) AS score
        FROM chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (embedding.tolist(), embedding.tolist(), top_k),
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "content": row[0],
            "url": row[1],
            "content_type": row[2],
            "tags": row[3] or [],
            "score": round(float(row[4]), 3),
            "high_confidence": float(row[4]) >= CONFIDENCE_THRESHOLD,
        }
        for row in rows
    ]
