"""
Embeds text chunks using sentence-transformers (local, no API key needed).
Model: all-mpnet-base-v2 — 768 dims, good quality, already a dependency.
"""
from sentence_transformers import SentenceTransformer

EMBED_MODEL = "all-mpnet-base-v2"  # 768 dims, matches schema
BATCH_SIZE = 64

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print(f"  Loading embedding model ({EMBED_MODEL})...")
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Adds an 'embedding' key (list[float]) to each chunk dict in place.
    Returns the same list with embeddings populated.
    """
    texts = [c["text"] for c in chunks]
    embeddings = _get_model().encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,   # unit vectors → cosine sim = dot product
    )
    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding.tolist()
    return chunks
