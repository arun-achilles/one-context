# One Context — Connector Interface

Connectors are the pluggable data source layer. Each connector extracts raw content from a source system and returns it as a list of `RawItem` objects. Everything downstream (hygiene, chunking, embedding) is source-agnostic.

---

## BaseConnector Interface

```python
# connectors/base.py
from abc import ABC, abstractmethod
from hygiene.models import RawItem

class BaseConnector(ABC):

    @abstractmethod
    def extract(self, config: dict) -> list[RawItem]:
        """
        Pull content from the source system.

        config: the source-specific block from onecontext.yaml
        Returns: list of RawItem (one per extractable unit)
        """
        ...

    def validate_config(self, config: dict) -> None:
        """
        Raise ValueError if required config keys are missing.
        Override to add source-specific validation.
        """
        pass
```

### RawItem contract

`RawItem` is defined in `hygiene/models.py`. Every connector must populate these fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | str | Yes | Globally unique. Use `source_type:external_id` pattern (e.g. `jira:CL-123`, `github:org/repo:path/to/file`) |
| `source_type` | str | Yes | `jira`, `confluence`, `github`, or your connector name |
| `title` | str | Yes | Human-readable title |
| `content` | str | Yes | Full text content (raw, pre-hygiene) |
| `url` | str | Yes | Direct link to the source item |
| `last_updated` | datetime | Yes | Last modification timestamp from source |
| `author` | str | No | Who created/last modified |
| `metadata` | dict | No | Source-specific extras (board id, space key, repo, branch, etc.) |

---

## Built-in Connectors

### Jira (`connectors/jira/`)

Extracts issues from Jira boards (not project keys — boards represent the team's curated view of work).

Config block in `onecontext.yaml`:
```yaml
jira:
  url: https://myorg.atlassian.net
  boards: [1108, 1245]
  custom_fields:
    epic_link: customfield_10014
    acceptance_criteria: customfield_10016
  max_results: 1000           # per board, optional (default: all)
  include_statuses: []        # optional filter, empty = all statuses
```

Credentials (via environment variables, not config file):
```
JIRA_USERNAME=your@email.com
JIRA_API_TOKEN=your_token
```

Each extracted Jira issue becomes one `RawItem`. Content includes: title, description, acceptance criteria, last 3 comments, labels, status.

To find board IDs:
```bash
python -m hygiene.pipeline --list-boards
```

To find custom field IDs:
```bash
curl -u your@email.com:TOKEN \
  https://myorg.atlassian.net/rest/api/3/field \
  | python3 -m json.tool | grep -A3 -i "epic\|acceptance"
```

### Confluence (`connectors/confluence/`)

Extracts pages from Confluence spaces.

Config block:
```yaml
confluence:
  url: https://myorg.atlassian.net/wiki
  spaces: [TEAM, ARCH, ADR]
  exclude_labels: [draft, archived]  # optional
```

Credentials:
```
CONFLUENCE_USERNAME=your@email.com
CONFLUENCE_API_TOKEN=your_token        # same token as Jira
```

Each page body is extracted as HTML, converted to plain text for hygiene. Child pages are extracted independently.

### GitHub (`connectors/github/`)

Extracts codebase knowledge — not raw code, but LLM-generated business-language summaries.

Config block:
```yaml
github:
  repos:
    - org/checkout-service
    - org/payments-service
  summarize_at: module          # service | module | file
  include: ["**/*.py", "**/*.ts", "**/*.java", "**/openapi.yaml"]
  exclude: ["**/tests/**", "**/migrations/**", "**/*.lock"]
  git_history_months: 12        # 0 to disable git history extraction
  branch: main                  # optional, default: default branch
```

Credentials:
```
GITHUB_TOKEN=ghp_your_token
```

**What is extracted:**

1. **Module summaries** (`summarize_at: module`): groups related files by directory (each directory = one module). LLM reads all files in the module and generates:
   - What this module does in business terms
   - What flows/features it implements
   - What external services/APIs it calls
   - What domain entities it manages

2. **File-level capabilities** (always extracted alongside summaries): per-file capability chunks with content types `business_flow`, `api_capability`, `integration`, `domain_entity`.

3. **OpenAPI specs**: endpoint summaries — method, path, purpose, request/response in plain language.

4. **Git history**: PR merge commits from the last N months → `shipped_feature` chunks describing what was delivered and when.

**Sync behaviour**: On PR merge webhook → re-extract only files changed in the PR → re-summarise affected modules. Selective, not full repo re-scan.

---

## Writing a Custom Connector

Example: implementing a Linear connector.

```python
# connectors/linear/linear_connector.py
from connectors.base import BaseConnector
from hygiene.models import RawItem
from datetime import datetime
import requests

class LinearConnector(BaseConnector):

    def validate_config(self, config: dict) -> None:
        if "team_ids" not in config:
            raise ValueError("linear connector requires 'team_ids'")

    def extract(self, config: dict) -> list[RawItem]:
        self.validate_config(config)
        token = os.environ["LINEAR_API_TOKEN"]
        headers = {"Authorization": token}
        items = []

        for team_id in config["team_ids"]:
            issues = self._fetch_issues(team_id, headers)
            for issue in issues:
                items.append(RawItem(
                    id=f"linear:{issue['id']}",
                    source_type="linear",
                    title=issue["title"],
                    content=f"{issue['title']}\n\n{issue.get('description', '')}",
                    url=issue["url"],
                    last_updated=datetime.fromisoformat(issue["updatedAt"]),
                    author=issue.get("assignee", {}).get("name"),
                    metadata={"team_id": team_id, "state": issue["state"]["name"]},
                ))

        return items

    def _fetch_issues(self, team_id: str, headers: dict) -> list[dict]:
        # GraphQL query against Linear API
        ...
```

Register in `connectors/__init__.py`:
```python
CONNECTOR_REGISTRY = {
    "jira": JiraConnector,
    "confluence": ConfluenceConnector,
    "github": GitHubConnector,
    "linear": LinearConnector,   # ← add here
}
```

Add to `onecontext.yaml`:
```yaml
sources:
  linear:
    team_ids: [TEAM_ABC, TEAM_XYZ]
```

The hygiene pipeline, chunker, embedder and knowledge store require no changes.

---

## onecontext.yaml — Full Schema

```yaml
# ── Project identity ──────────────────────────────────────────────────────────
project: my-project                 # used as a namespace prefix in source IDs

# ── Data sources ─────────────────────────────────────────────────────────────
sources:

  jira:
    url: https://myorg.atlassian.net
    boards: [1108]
    custom_fields:
      epic_link: customfield_10014
      acceptance_criteria: customfield_10016

  confluence:
    url: https://myorg.atlassian.net/wiki
    spaces: [TEAM, ARCH]
    exclude_labels: [draft]

  github:
    repos:
      - org/service-a
      - org/service-b
    summarize_at: module            # service | module | file
    include: ["**/*.py", "**/*.ts"]
    exclude: ["**/tests/**", "**/migrations/**"]
    git_history_months: 12
    branch: main

# ── Hygiene settings ─────────────────────────────────────────────────────────
hygiene:
  staleness_months: 12              # content older than this is flagged
  min_quality_auto: 4               # score >= this → auto-included
  min_quality_review: 2             # score >= this → pending review; below → rejected

# ── Sync settings ─────────────────────────────────────────────────────────────
sync:
  schedule: "0 2 * * *"            # cron expression for daily reconciliation
  webhook_port: 8001               # port for incoming Jira/GitHub webhooks
```

---

## Environment Variables

All credentials go in `.env`, never in `onecontext.yaml`:

```
# Jira + Confluence (one token covers both)
JIRA_USERNAME=your@email.com
JIRA_API_TOKEN=your_atlassian_token

CONFLUENCE_USERNAME=your@email.com
CONFLUENCE_API_TOKEN=your_atlassian_token

# GitHub
GITHUB_TOKEN=ghp_your_token

# LLM (classification, summarisation, reasoning)
ANTHROPIC_API_KEY=sk-ant-...

# Database
DATABASE_URL=postgresql://one_context:one_context@localhost:5432/one_context
```
