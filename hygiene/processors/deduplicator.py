import numpy as np
from sentence_transformers import SentenceTransformer
from hygiene.models import RawContent

_model = None
SIMILARITY_THRESHOLD = 0.92
ENCODE_BATCH_SIZE = 32


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # Small, fast model — good enough for near-duplicate detection
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def find_duplicates(items: list[RawContent]) -> dict[str, str]:
    """Returns {duplicate_id: original_id}. Keeps the more recently updated item."""
    if len(items) < 2:
        return {}

    texts = [f"{item.title} {item.body[:500]}" for item in items]
    embeddings = _get_model().encode(
        texts, batch_size=ENCODE_BATCH_SIZE, show_progress_bar=True
    )

    # Normalize for cosine similarity via dot product
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.where(norms == 0, 1, norms)
    similarity = embeddings @ embeddings.T

    duplicates: dict[str, str] = {}
    seen: set[str] = set()

    for i in range(len(items)):
        if items[i].id in seen:
            continue
        for j in range(i + 1, len(items)):
            if items[j].id in seen:
                continue
            if similarity[i][j] >= SIMILARITY_THRESHOLD:
                # Keep the more recently updated one as the canonical item
                if items[i].last_updated >= items[j].last_updated:
                    duplicates[items[j].id] = items[i].id
                    seen.add(items[j].id)
                else:
                    duplicates[items[i].id] = items[j].id
                    seen.add(items[i].id)
                    break  # i is now a duplicate, stop checking its pairs

    return duplicates
