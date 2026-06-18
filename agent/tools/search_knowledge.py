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
VECTOR_WEIGHT = 0.7
TEXT_WEIGHT = 0.3

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-mpnet-base-v2")
    return _model


def _normalize_scores(scores: list[float]) -> list[float]:
    """Min-max normalize scores to [0, 1] with stable fallback."""
    if not scores:
        return []
    lo = min(scores)
    hi = max(scores)
    if abs(hi - lo) < 1e-12:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def _fts_vector_expression() -> str:
    return (
        "setweight(to_tsvector('simple', coalesce(content, '')), 'A') || "
        "setweight(to_tsvector('simple', coalesce(summary, '')), 'B')"
    )


def search_knowledge(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Returns up to top_k chunks ordered by cosine similarity.
    Each result: {content, url, content_type, tags, score, high_confidence}
    """
    query = (query or "").strip()
    if not query:
        return []

    embedding = _get_model().encode(query, normalize_embeddings=True)

    conn = get_connection()
    register_vector(conn)
    cur = conn.cursor()

    # 1) Vector candidates
    vector_limit = max(top_k * 2, top_k)
    cur.execute(
        """
        SELECT id, content, url, content_type, tags,
               1 - (embedding <=> %s::vector) AS vector_score
        FROM chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (embedding.tolist(), embedding.tolist(), vector_limit),
    )
    vector_rows = cur.fetchall()

    # 2) Full-text candidates
    fts_expr = _fts_vector_expression()
    fts_limit = max(top_k * 2, top_k)
    cur.execute(
        f"""
        SELECT id, content, url, content_type, tags,
               ts_rank_cd({fts_expr}, plainto_tsquery('simple', %s)) AS text_score
        FROM chunks
        WHERE {fts_expr} @@ plainto_tsquery('simple', %s)
        ORDER BY text_score DESC
        LIMIT %s
        """,
        (query, query, fts_limit),
    )
    text_rows = cur.fetchall()

    conn.close()

    # 3) Fuse scores into one ranked set
    vec_scores = _normalize_scores([float(r[5]) for r in vector_rows])
    text_scores = _normalize_scores([float(r[5]) for r in text_rows])

    merged: dict[int, dict] = {}

    for i, row in enumerate(vector_rows):
        chunk_id, content, url, content_type, tags, vector_score = row
        merged[chunk_id] = {
            "id": chunk_id,
            "content": content,
            "url": url,
            "content_type": content_type,
            "tags": tags or [],
            "vector_score": max(0.0, float(vector_score)),
            "text_score": 0.0,
            "vector_norm": vec_scores[i],
            "text_norm": 0.0,
        }

    for i, row in enumerate(text_rows):
        chunk_id, content, url, content_type, tags, text_score = row
        item = merged.get(chunk_id)
        if not item:
            item = {
                "id": chunk_id,
                "content": content,
                "url": url,
                "content_type": content_type,
                "tags": tags or [],
                "vector_score": 0.0,
                "text_score": max(0.0, float(text_score)),
                "vector_norm": 0.0,
                "text_norm": text_scores[i],
            }
            merged[chunk_id] = item
        else:
            item["text_score"] = max(0.0, float(text_score))
            item["text_norm"] = text_scores[i]

    ranked = []
    for item in merged.values():
        hybrid_score = (VECTOR_WEIGHT * item["vector_norm"]) + (TEXT_WEIGHT * item["text_norm"])
        ranked.append(
            {
                "content": item["content"],
                "url": item["url"],
                "content_type": item["content_type"],
                "tags": item["tags"],
                "score": round(float(hybrid_score), 3),
                "high_confidence": float(hybrid_score) >= CONFIDENCE_THRESHOLD,
            }
        )

    ranked.sort(key=lambda x: x["score"], reverse=True)

    return ranked[:top_k]
