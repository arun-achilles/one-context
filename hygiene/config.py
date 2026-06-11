"""
Loads and validates onecontext.yaml project configuration.

Usage:
    from hygiene.config import load_config
    config = load_config("onecontext.yaml")
    # config.project, config.sources, config.hygiene, config.sync
"""
import yaml
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class HygieneConfig:
    staleness_months: int = 12
    min_quality_auto: int = 4      # score >= this → auto-included
    min_quality_review: int = 2    # score >= this → pending review; below → rejected


@dataclass
class SyncConfig:
    schedule: str = "0 2 * * *"   # daily at 02:00
    webhook_port: int = 8001


@dataclass
class ProjectConfig:
    project: str
    sources: dict[str, dict]       # {source_type: source-specific config block}
    hygiene: HygieneConfig = field(default_factory=HygieneConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)


def load_config(path: str | Path) -> ProjectConfig:
    """
    Load and validate onecontext.yaml. Raises ValueError for missing required fields.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p.absolute()}")

    with open(p) as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError(f"{path} is empty")

    if "project" not in raw:
        raise ValueError("onecontext.yaml must specify 'project'")

    if "sources" not in raw or not raw["sources"]:
        raise ValueError("onecontext.yaml must specify at least one source under 'sources'")

    hygiene_raw = raw.get("hygiene", {})
    hygiene = HygieneConfig(
        staleness_months=hygiene_raw.get("staleness_months", 12),
        min_quality_auto=hygiene_raw.get("min_quality_auto", 4),
        min_quality_review=hygiene_raw.get("min_quality_review", 2),
    )

    sync_raw = raw.get("sync", {})
    sync = SyncConfig(
        schedule=sync_raw.get("schedule", "0 2 * * *"),
        webhook_port=sync_raw.get("webhook_port", 8001),
    )

    return ProjectConfig(
        project=raw["project"],
        sources=raw["sources"],
        hygiene=hygiene,
        sync=sync,
    )
