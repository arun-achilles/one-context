"""
Entry point for the data hygiene pipeline.

Preferred usage (config file):
    python -m hygiene.pipeline --config onecontext.yaml

Legacy usage (direct flags, still supported):
    python -m hygiene.pipeline --boards 123,456 --spaces TEAM,ARCH

To find your board IDs:
    python -m hygiene.pipeline --list-boards
"""
import json
import argparse
from dotenv import load_dotenv
load_dotenv()

from hygiene.models import ProcessedContent, ContentStatus
from hygiene.config import load_config
from hygiene.extractors.jira_extractor import JiraExtractor
from hygiene.extractors.confluence_extractor import ConfluenceExtractor
from hygiene.processors.classifier import classify_batch
from hygiene.processors.staleness import check_staleness
from hygiene.processors.deduplicator import find_duplicates
from hygiene.processors.enricher import enrich_batch


def list_boards() -> None:
    boards = JiraExtractor().list_boards()
    if not boards:
        print("No boards found — check your credentials and permissions.")
        return
    print(f"\n{'ID':<8} {'Type':<12} {'Name'}")
    print("-" * 50)
    for b in boards:
        print(f"{b['id']:<8} {b.get('type', ''):<12} {b['name']}")


def run(
    source_configs: dict[str, dict],
    output_path: str = "hygiene_results.json",
    hygiene_config=None,
) -> list[ProcessedContent]:
    """
    source_configs: {source_type: config_dict} — e.g.
        {"jira": {"boards": [1108]}, "confluence": {"spaces": ["CL"]}}
    """
    from connectors import get_connector

    # 1. Extract from all configured sources
    print("Extracting from configured sources...")
    raw_items = []
    for source_type, config in source_configs.items():
        connector = get_connector(source_type)
        print(f"  [{source_type}] extracting...")
        items = connector.extract(config)
        print(f"  [{source_type}] {len(items)} items")
        raw_items.extend(items)
    print(f"  Total: {len(raw_items)} items extracted")

    # 2. Classify + quality score (LLM, batched)
    print("Classifying and scoring...")
    classifications = classify_batch(raw_items)

    # 3. Staleness (rule-based, free)
    staleness_months = hygiene_config.staleness_months if hygiene_config else 12
    print("Checking staleness...")
    staleness = [check_staleness(item, max_age_months=staleness_months) for item in raw_items]

    # 4. Deduplication (embeddings)
    print("Finding duplicates...")
    duplicates = find_duplicates(raw_items)

    # 5. Enrich only items worth keeping
    min_quality_review = hygiene_config.min_quality_review if hygiene_config else 2
    min_quality_auto = hygiene_config.min_quality_auto if hygiene_config else 4
    print("Enriching high-quality items...")
    enrichable = [
        item
        for item, clf in zip(raw_items, classifications)
        if clf.quality_score >= min_quality_review and item.id not in duplicates
    ]
    enrichments = enrich_batch(enrichable)
    enrichment_map = {item.id: e for item, e in zip(enrichable, enrichments)}

    # 6. Assemble and route
    print("Routing items...")
    processed: list[ProcessedContent] = []
    for item, clf, (is_stale, stale_reason) in zip(raw_items, classifications, staleness):
        enrichment = enrichment_map.get(item.id, {})
        p = ProcessedContent(
            raw=item,
            content_type=clf.content_type,
            quality_score=clf.quality_score,
            is_stale=is_stale,
            staleness_reason=stale_reason,
            duplicate_of=duplicates.get(item.id),
            summary=enrichment.get("summary"),
            entities=enrichment.get("entities", []),
            tags=enrichment.get("tags", []),
        )

        if p.duplicate_of:
            p.status = ContentStatus.REJECTED
            p.review_reason = f"Duplicate of {p.duplicate_of}"
        elif clf.content_type == "noise" or clf.quality_score <= 1:
            p.status = ContentStatus.REJECTED
            p.review_reason = clf.quality_reason
        elif clf.quality_score >= min_quality_auto and not is_stale:
            p.status = ContentStatus.AUTO_INCLUDED
        else:
            p.status = ContentStatus.PENDING_REVIEW
            reasons = []
            if clf.quality_score < min_quality_auto:
                reasons.append(f"Incomplete: {clf.quality_reason}")
            if is_stale:
                reasons.append(f"Stale: {stale_reason}")
            p.review_reason = " | ".join(reasons)

        processed.append(p)

    _print_summary(processed)
    _save(processed, output_path)
    return processed


def _print_summary(processed: list[ProcessedContent]) -> None:
    counts = {s: 0 for s in ContentStatus}
    for p in processed:
        counts[p.status] += 1
    print("\nSummary:")
    print(f"  Auto-included : {counts[ContentStatus.AUTO_INCLUDED]}")
    print(f"  Pending review: {counts[ContentStatus.PENDING_REVIEW]}")
    print(f"  Rejected      : {counts[ContentStatus.REJECTED]}")


def _save(processed: list[ProcessedContent], path: str) -> None:
    with open(path, "w") as f:
        json.dump([p.model_dump() for p in processed], f, indent=2, default=str)
    print(f"\nResults saved to {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default=None,
        help="Path to onecontext.yaml (preferred)",
    )
    parser.add_argument(
        "--boards", default="",
        help="Legacy: comma-separated Jira board IDs (e.g. 123,456)",
    )
    parser.add_argument(
        "--spaces", default="",
        help="Legacy: comma-separated Confluence space keys (e.g. TEAM,ARCH)",
    )
    parser.add_argument("--output", default="hygiene_results.json")
    parser.add_argument(
        "--list-boards", action="store_true",
        help="Print all visible Jira boards with their IDs and exit",
    )
    args = parser.parse_args()

    if args.list_boards:
        list_boards()
    elif args.config:
        cfg = load_config(args.config)
        run(
            source_configs=cfg.sources,
            output_path=args.output,
            hygiene_config=cfg.hygiene,
        )
    else:
        # Legacy: build source_configs from CLI flags
        source_configs = {}
        if args.boards:
            source_configs["jira"] = {
                "boards": [int(b) for b in args.boards.split(",") if b]
            }
        if args.spaces:
            source_configs["confluence"] = {
                "spaces": [s for s in args.spaces.split(",") if s]
            }
        if not source_configs:
            parser.error("Provide --config or at least one of --boards / --spaces")
        run(source_configs=source_configs, output_path=args.output)
