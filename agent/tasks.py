"""
Celery task definitions for background sync jobs.

Worker: celery -A agent.tasks worker --loglevel=info
Beat:   celery -A agent.tasks beat   --loglevel=info

Tasks:
  sync_all      — full pipeline run for all sources in onecontext.yaml
  sync_pr       — selective re-index of files changed in a PR merge
  sync_issue    — re-extract and re-embed a single Jira/Confluence item
"""
import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

app = Celery(
    "one_context",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)

app.conf.beat_schedule = {
    "daily-sync": {
        "task": "agent.tasks.sync_all",
        "schedule": 60 * 60 * 24,   # every 24 hours
    },
}
app.conf.timezone = "UTC"


@app.task(name="agent.tasks.sync_all", bind=True, max_retries=3)
def sync_all(self):
    """
    Full pipeline run: hygiene → ingest all sources in onecontext.yaml.
    Triggered by Celery Beat (daily) or manually via: celery call agent.tasks.sync_all
    """
    try:
        from hygiene.config import load_config
        from hygiene.pipeline import run as run_hygiene
        from ingestion.ingest import run as run_ingest

        cfg = load_config("onecontext.yaml")
        print(f"[sync_all] Starting full sync for project: {cfg.project}")

        result_path = "/tmp/hygiene_results.json"
        run_hygiene(
            source_configs=cfg.sources,
            output_path=result_path,
            hygiene_config=cfg.hygiene,
        )
        run_ingest(input_path=result_path)
        print("[sync_all] Done.")

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * 5)   # retry after 5 min


@app.task(name="agent.tasks.sync_pr")
def sync_pr(repo: str, pr_number: int, changed_files: list[str]):
    """
    Selective re-index triggered by a PR merge webhook.
    Re-extracts and re-embeds only the files changed in the PR.
    Full implementation: one-context-gnp
    """
    print(f"[sync_pr] repo={repo} pr={pr_number} files={len(changed_files)}")
    # TODO: implement selective re-extraction for changed_files only


@app.task(name="agent.tasks.sync_issue")
def sync_issue(source_type: str, item_id: str):
    """
    Re-extract and re-embed a single Jira issue or Confluence page.
    Triggered by Jira/Confluence webhooks.
    """
    print(f"[sync_issue] {source_type}:{item_id}")
    # TODO: implement single-item re-sync
