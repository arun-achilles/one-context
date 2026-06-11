# Get Started — One Context

One Context is an AI Delivery Co-Pilot. It ingests Jira, Confluence, and codebase knowledge, and gives every team member — PO, Tech Lead, Developer — a single place to ask questions, create stories, and track delivery features.

---

## Current Status

| Component | Status |
|---|---|
| Phase 0 — Data Hygiene Pipeline | ✅ Complete |
| Phase 1 — Knowledge Store (pgvector, 1,653 chunks) | ✅ Complete |
| Phase 1 — LangGraph Agent (Q&A, live Jira/Confluence) | ✅ Complete |
| Phase 1 — FastAPI + Celery + Docker Compose | ✅ Complete |
| Phase 2 — Write Tools (story draft, Confluence update, memory) | ✅ Complete |
| Phase 2 — Feature Workspace (sessions, links, context injection) | ✅ Complete |
| Phase 3 — Code Extraction (14 repos ingested) | ✅ Complete |
| Phase 1 — Web UI (Next.js chat interface) | 🔲 Next |
| Phase 3 — Role-based retrieval, PR webhook | 🔲 Pending |
| Phase 4 — Knowledge Graph (Neo4j) | 🔲 Future |

**Ingested:** 1,278 Jira issues + 83 Confluence pages + 14 repos → 1,039 sources, 1,653 chunks

---

## Prerequisites

- Python 3.11+ with venv
- Docker Desktop
- Anthropic API key
- Atlassian API token (covers Jira + Confluence)
- Local clones of your repos (for code extraction)

---

## Setup

```bash
git clone <repo>
cd one-context
python3 -m venv venv
source venv/bin/activate
pip install -r hygiene/requirements.txt

cp .env.example .env
# Fill in: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN,
#           CONFLUENCE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN,
#           ANTHROPIC_API_KEY, JIRA_PROJECT_KEY, CONFLUENCE_SPACE_KEY
```

---

## Start the stack

```bash
docker-compose up -d postgres redis
python db/connection.py          # apply schema (first time only)
```

---

## Run the pipeline (first ingest or re-sync)

Copy the template and configure your sources:
```bash
cp onecontext.yaml.example onecontext.yaml
# Edit onecontext.yaml with your board IDs, space keys, and repo paths
```
Then:

```bash
# Run hygiene pipeline (Jira + Confluence + code repos)
python -m hygiene.pipeline --config onecontext.yaml

# Review flagged items (optional — skip with --all for demo)
python -m hygiene.review_queue --input hygiene_results.json

# Ingest into pgvector
python -m ingestion.ingest --input hygiene_results.json
# or skip review queue (demo mode):
python -m ingestion.ingest --input hygiene_results.json --all
```

---

## Use the agent

### CLI (developer / testing)

```bash
source venv/bin/activate && python -m agent.cli
```

Example interactions:
- *"What does the QR manager service do?"*
- *"Draft a story for improving scan reliability in low-light conditions"* → reply `yes` to create in Jira
- *"Remember: we decided to defer gift card support until Q3 2026"* → reply `yes` to save to team memory

### API

```bash
uvicorn agent.api:app --reload --port 8000
# Docs at http://localhost:8000/docs
```

---

## Feature Workspaces

Features are shared delivery workspaces — one per significant initiative. Each role (PO, Tech Lead, Dev) opens a session; the agent carries full context of all prior sessions.

```bash
# Create a feature
curl -X POST http://localhost:8000/features \
  -H "Content-Type: application/json" \
  -d '{"name": "Gift Cards", "description": "Purchase and redemption", "created_by": "you"}'
# → {"id": "OC-001", "status": "planned", ...}

# List all features
curl http://localhost:8000/features

# Start a PO session (agent primed with feature context + prior sessions)
curl -X POST http://localhost:8000/features/OC-001/sessions \
  -H "Content-Type: application/json" \
  -d '{"role": "po", "author": "your name"}'
# → {"conversation_id": 5, "feature_context": "..."}

# Chat in that session
curl -X POST http://localhost:8000/conversations/5/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What existing capabilities can we reuse for gift cards?"}'
```

When a story is created inside a feature session it is automatically linked to that feature.

---

## Re-running the pipeline

```bash
python -m hygiene.pipeline --config onecontext.yaml
python -m ingestion.ingest --input hygiene_results.json --all
```

Find Jira board IDs: `python -m hygiene.pipeline --list-boards`

---

## Jira custom field IDs

Jira field IDs are instance-specific. Find yours:

```bash
curl -u your@email.com:YOUR_API_TOKEN \
  https://yourorg.atlassian.net/rest/api/3/field \
  | python3 -m json.tool | grep -A3 -i "epic\|acceptance"
```

Update `onecontext.yaml` under `jira.custom_fields`.

---

## Troubleshooting

**`ModuleNotFoundError`** — activate venv: `source venv/bin/activate`

**Auth error** — `JIRA_USERNAME` must be your email address, not display name.

**`0 items extracted`** — verify board ID with `--list-boards`. Confluence space keys are case-sensitive.

**`expected N dimensions, not 768`** — drop and recreate tables:
```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from db.connection import get_connection
from pathlib import Path
conn = get_connection(); cur = conn.cursor()
cur.execute('DROP TABLE IF EXISTS messages, conversations, memory, chunks, sources, feature_links, feature_sessions, features CASCADE')
conn.commit()
cur.execute(Path('db/schema.sql').read_text())
conn.commit(); conn.close(); print('Done')
"
```
