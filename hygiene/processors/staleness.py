from datetime import datetime, timezone
from hygiene.models import RawContent

STALE_THRESHOLD_DAYS = 365

DEPRECATED_SIGNALS = [
    "deprecated",
    "legacy system",
    "will be replaced",
    "no longer used",
    "sunset",
    "decommissioned",
    "do not use",
    "moved to",
    "replaced by",
]


def check_staleness(item: RawContent, max_age_months: int = 12) -> tuple[bool, str | None]:
    now = datetime.now(timezone.utc)
    last_updated = item.last_updated
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    age_days = (now - last_updated).days
    threshold_days = max_age_months * 30
    if age_days > threshold_days:
        return True, f"Not updated in {age_days} days ({max_age_months}mo threshold)"

    combined = f"{item.title} {item.body}".lower()
    for signal in DEPRECATED_SIGNALS:
        if signal in combined:
            return True, f"Contains stale signal: '{signal}'"

    return False, None
