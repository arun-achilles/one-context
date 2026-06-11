"""
Upserts sources and chunks into PostgreSQL + pgvector.
Re-ingesting a source replaces its chunks cleanly.
"""
import json
import numpy as np
from datetime import datetime, timezone

import psycopg2.extras
from pgvector.psycopg2 import register_vector

from db.connection import get_connection


def upsert(items: list[dict], chunks: list[dict]) -> None:
    conn = get_connection()
    register_vector(conn)
    try:
        with conn:
            cur = conn.cursor()
            _upsert_sources(cur, items)
            _replace_chunks(cur, chunks)
            cur.close()
    finally:
        conn.close()


def _upsert_sources(cur, items: list[dict]) -> None:
    rows = [
        (
            raw["id"],
            raw["source"],
            raw["id"].split(":", 1)[-1],
            raw["url"],
            datetime.now(timezone.utc),
            json.dumps(raw.get("metadata", {}), default=str),
        )
        for item in items
        for raw in [item["raw"]]
    ]
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO sources (id, source_type, external_id, url, last_synced, metadata)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            last_synced = EXCLUDED.last_synced,
            metadata    = EXCLUDED.metadata
        """,
        rows,
    )


def _replace_chunks(cur, chunks: list[dict]) -> None:
    if not chunks:
        return

    # Delete existing chunks for all sources in this batch at once
    source_ids = list({c["source_id"] for c in chunks})
    cur.execute(
        "DELETE FROM chunks WHERE source_id = ANY(%s)",
        (source_ids,),
    )

    rows = [
        (
            c["source_id"],
            c["text"],
            # pgvector adapter expects a numpy array
            np.array(c["embedding"], dtype=np.float32),
            c["metadata"].get("content_type"),
            c["metadata"].get("tags") or [],
            c["metadata"].get("entities") or [],
            c["metadata"].get("summary"),
            c["metadata"].get("url"),
            c["metadata"].get("last_updated"),
        )
        for c in chunks
    ]

    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO chunks
            (source_id, content, embedding, content_type, tags, entities, summary, url, last_updated)
        VALUES %s
        """,
        rows,
        template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
    )
