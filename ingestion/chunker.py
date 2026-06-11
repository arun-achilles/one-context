"""
Splits hygiene-approved content into embeddable chunks.

Strategy:
- Jira:      title prepended to each chunk; split at paragraph breaks if body > MAX_CHARS
- Confluence: split on section headers (##) or paragraph breaks
"""
import re

MAX_CHARS = 1500   # ~375 tokens — safe for most embedding models
OVERLAP = 150      # chars of overlap between adjacent chunks


def chunk_item(item: dict) -> list[dict]:
    """
    Returns a list of chunk dicts ready for embedding.
    Each dict has: text, source_id, metadata.
    """
    raw = item["raw"]
    source_id = raw["id"]
    title = raw["title"] or ""
    body = raw["body"] or ""
    metadata = {
        "source_type": raw["source"],
        "content_type": item.get("content_type"),
        "tags": item.get("tags", []),
        "entities": item.get("entities", []),
        "summary": item.get("summary"),
        "url": raw["url"],
        "last_updated": raw["last_updated"],
        "board_name": raw.get("metadata", {}).get("board_name"),
        "sprint": raw.get("metadata", {}).get("sprint"),
        "status": raw.get("metadata", {}).get("status"),
        "issue_type": raw.get("metadata", {}).get("issue_type"),
    }

    # Items with no body — embed title only
    if not body.strip():
        return [{"text": title, "source_id": source_id, "metadata": metadata}]

    if raw["source"] == "confluence":
        segments = _split_confluence(body)
    else:
        segments = _split_paragraphs(body)

    chunks = []
    for seg in segments:
        # Prepend title so every chunk carries full context
        text = f"{title}\n\n{seg}".strip()
        if text:
            chunks.append({"text": text, "source_id": source_id, "metadata": metadata})

    return chunks or [{"text": title, "source_id": source_id, "metadata": metadata}]


def _split_confluence(text: str) -> list[str]:
    """Split on markdown-style headers that Confluence often produces."""
    sections = re.split(r"\n(?=#{1,3} )", text)
    result = []
    for section in sections:
        if len(section) <= MAX_CHARS:
            result.append(section.strip())
        else:
            result.extend(_split_paragraphs(section))
    return [s for s in result if s.strip()]


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines, then merge small paragraphs and break large ones."""
    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= MAX_CHARS:
            current = f"{current}\n\n{para}".strip() if current else para
        else:
            if current:
                chunks.append(current)
            # Para itself too long — hard split with overlap
            if len(para) > MAX_CHARS:
                chunks.extend(_hard_split(para))
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


def _hard_split(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + MAX_CHARS
        chunks.append(text[start:end])
        start = end - OVERLAP
    return chunks
