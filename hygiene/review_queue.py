"""
CLI review tool for items flagged as PENDING_REVIEW.

Run:
    python -m hygiene.review_queue --input hygiene_results.json
"""
import json
import argparse
from hygiene.models import ContentStatus


def run(results_path: str = "hygiene_results.json") -> None:
    with open(results_path) as f:
        items: list[dict] = json.load(f)

    pending = [i for i in items if i["status"] == ContentStatus.PENDING_REVIEW]
    if not pending:
        print("Nothing to review.")
        return

    print(f"\n{len(pending)} items need review\n")
    approved = rejected = 0

    for idx, item in enumerate(pending):
        _print_item(idx + 1, len(pending), item)
        choice = input("[a]pprove / [r]eject / [s]kip > ").strip().lower()

        if choice == "a":
            item["status"] = ContentStatus.APPROVED
            approved += 1
        elif choice == "r":
            item["status"] = ContentStatus.REJECTED
            rejected += 1
        # skip leaves status unchanged

    # Persist decisions back
    id_to_reviewed = {i["raw"]["id"]: i for i in pending}
    for item in items:
        if item["raw"]["id"] in id_to_reviewed:
            item["status"] = id_to_reviewed[item["raw"]["id"]]["status"]

    with open(results_path, "w") as f:
        json.dump(items, f, indent=2, default=str)

    print(f"\nDone — approved: {approved}, rejected: {rejected}")
    print(f"Results saved to {results_path}")


def _print_item(current: int, total: int, item: dict) -> None:
    raw = item["raw"]
    print(f"\n[{current}/{total}] {raw['source'].upper()}")
    print(f"  Title  : {raw['title']}")
    print(f"  Quality: {item.get('quality_score', '?')}/5")
    print(f"  Reason : {item.get('review_reason', '-')}")
    print(f"  URL    : {raw['url']}")
    if item.get("summary"):
        print(f"  Summary: {item['summary']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="hygiene_results.json")
    args = parser.parse_args()
    run(args.input)
