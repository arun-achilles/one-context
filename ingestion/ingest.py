"""
Loads hygiene-approved content into the knowledge store.

Run:
    python -m ingestion.ingest --input hygiene_results.json
"""
import json
import argparse
from dotenv import load_dotenv

load_dotenv()

from ingestion.chunker import chunk_item
from ingestion.embedder import embed_chunks
from ingestion.loader import upsert

INCLUDE_STATUSES = {"auto_included", "approved"}
INCLUDE_STATUSES_ALL = {"auto_included", "approved", "pending_review"}
PROGRESS_EVERY = 100


def run(input_path: str = "hygiene_results.json", include_all: bool = False) -> None:
    with open(input_path) as f:
        all_items = json.load(f)

    statuses = INCLUDE_STATUSES_ALL if include_all else INCLUDE_STATUSES
    items = [i for i in all_items if i["status"] in statuses]
    print(f"Ingesting {len(items)} items from {input_path} (statuses: {', '.join(sorted(statuses))})")

    # 1. Chunk
    print("\nStep 1/3 — Chunking...")
    all_chunks = []
    for item in items:
        all_chunks.extend(chunk_item(item))
    print(f"  {len(items)} items → {len(all_chunks)} chunks")

    # 2. Embed
    print("\nStep 2/3 — Embedding...")
    embed_chunks(all_chunks)
    print(f"  {len(all_chunks)} chunks embedded")

    # 3. Load
    print("\nStep 3/3 — Loading into PostgreSQL...")
    # Process in batches to avoid holding everything in memory
    batch_size = 200
    for i in range(0, len(items), batch_size):
        item_batch = items[i : i + batch_size]
        # Collect the chunks that belong to this batch of items
        item_ids = {item["raw"]["id"] for item in item_batch}
        chunk_batch = [c for c in all_chunks if c["source_id"] in item_ids]
        upsert(item_batch, chunk_batch)
        loaded = min(i + batch_size, len(items))
        print(f"  {loaded}/{len(items)} items loaded...")

    print(f"\nDone. {len(items)} sources, {len(all_chunks)} chunks in the knowledge base.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="hygiene_results.json")
    parser.add_argument("--all", action="store_true",
                        help="Include pending_review items (skips manual review — demo/dev only)")
    args = parser.parse_args()
    run(args.input, include_all=args.all)
