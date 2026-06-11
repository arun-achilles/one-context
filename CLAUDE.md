# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

One Context is an AI Delivery Co-Pilot for software teams. It ingests Jira, Confluence, and GitHub content, runs a hygiene pipeline, embeds approved content into pgvector, and exposes a LangGraph agent that answers questions grounded in real team knowledge. The long-term goal is a shared intelligence layer across every delivery role — PO, tech lead, developer.

## Essential commands

```bash
# Start PostgreSQL (required before anything else)
docker compose up -d

# Apply schema (first time, or after schema changes)
python db/connection.py

# Run the hygiene pipeline against real data
python -m hygiene.pipeline --boards 1108 --spaces CL --output hygiene_results.json

# Find available Jira board IDs
python -m hygiene.pipeline --list-boards

# Interactive review of flagged items
python -m hygiene.review_queue --input hygiene_results.json

# Ingest approved content into pgvector
python -m ingestion.ingest --input hygiene_results.json

# Ingest all items including pending review (demo mode)
python -m ingestion.ingest --input hygiene_results.json --all

# Run the agent interactively (CLI)
python -m agent.cli

# Start API server
uvicorn agent.api:app --reload --port 8000

# Run Celery worker (background sync)
celery -A agent.tasks worker --loglevel=info
```

All Python commands require the venv active (`source venv/bin/activate`) and a populated `.env` (copy from `.env.example`).

## Architecture

Four distinct layers that must run in order:

```
connectors/ (extract)  →  hygiene/ (pipeline)  →  ingestion/ (chunk + embed)  →  agent/ (LangGraph + API)
```

### 0. Connectors (`connectors/`)

`BaseConnector` interface with a registry. All extractors implement `extract(config: dict) -> [RawContent]`. Currently: `jira`, `confluence`, `code` (local git repos via gitpython).

### 1. Hygiene pipeline (`hygiene/`)

Runs before every ingestion. Steps: extract → classify → quality score → staleness check → deduplicate → enrich → route.

- **Extractors** (`extractors/jira_extractor.py`, `extractors/confluence_extractor.py`): board-based (not project-key-based) Jira extraction; space-based Confluence extraction.
- **Processors**: `classifier.py` uses Claude Haiku (batched, prompt-cached) to assign content type and quality score 1–5. `deduplicator.py` uses local embeddings. `enricher.py` uses Claude Haiku to generate summaries, entities, and tags.
- **Routing logic** (in `pipeline.py`): quality 4–5 + not stale → auto-included; quality 2–3 or stale → pending review; quality 1 or noise → rejected.
- Output is `hygiene_results.json` — the intermediate artifact consumed by ingestion.

### 2. Ingestion (`ingestion/`)

Reads `hygiene_results.json`, processes only `auto_included` and `approved` items.

- `chunker.py`: semantic chunking by section for Confluence; one chunk per Jira issue (title + description + ACs + last 3 comments).
- `embedder.py`: local `sentence-transformers/all-mpnet-base-v2` (768 dims, no API key). Model downloads once (~420MB) and is cached.
- `loader.py`: upserts into `sources` and `chunks` tables in PostgreSQL.

### 3. Knowledge store (`db/`)

Single PostgreSQL instance with pgvector. Tables:
- `sources`: one row per ingested item (`jira:CL-123`, `confluence:12345`)
- `chunks`: embedded content with `content_type`, `tags`, `entities`, `summary`
- `memory`: explicit team decisions/agreements — never auto-deleted, always searched alongside chunks
- `conversations` + `messages`: shared threads per topic (not per-user)
- `features` + `feature_sessions` + `feature_links`: feature workspace; OC-001-style IDs

The IVFFlat vector index in `schema.sql` is intentionally commented out — create it after the initial bulk load, not before.

### 4. LangGraph agent (`agent/`)

StateGraph with four nodes: `route` → `retrieve` → `reason` → `respond`.

- **State** (`state.py`): `messages`, `intent`, `retrieved_chunks`, `answer`, `citations`, `needs_clarification`
- **Router** classifies intent: `qa`, `pipeline_query`, or `clarify`
- **Retriever** calls `search_knowledge()` — cosine similarity via pgvector. If top score < `CONFIDENCE_THRESHOLD` (0.45), sets `needs_clarification=True`
- **Reasoner** uses Claude Sonnet to synthesize retrieved chunks with the query
- **Responder** formats the final answer with citations
- **`api.py`**: FastAPI app. Key routes: `POST/GET /features`, `POST /features/{id}/sessions`, `POST /conversations/{id}/chat` (SSE streaming)
- **`tasks.py`**: Celery app with `sync_all` (daily pipeline), `sync_pr`, and `sync_issue` tasks
- **`tools/feature_tools.py`**: Feature workspace tools — `create_feature`, `create_session`, `build_feature_context`, `link_artefact`

The compiled graph is a singleton (`get_graph()`) — compiled once, reused across requests.

## LLM strategy

| Use | Model | Reason |
|---|---|---|
| Classification, enrichment, staleness | Claude Haiku 4.5 | Cheap, fast, structured output |
| Agent reasoning, story drafting | Claude Sonnet 4.6 | Best instruction following |
| Embeddings | `all-mpnet-base-v2` (local) | No API cost, runs on-device |

## Key non-obvious details

- **Jira custom field IDs are instance-specific.** `epic_link` and `acceptance_criteria` field IDs must be configured in `hygiene/extractors/jira_extractor.py` for the target Atlassian instance. See `get-started.md` for the curl command to find them.
- **Conversations are shared per topic, not per user.** This is intentional — the assistant is a team resource. `conversations.topic` is a free-form label (epic name, feature name, etc.).
- **`hygiene_results.json` is the contract between pipeline and ingestion.** Items manually approved via `review_queue.py` have status `approved`; auto-passed items have `auto_included`. Ingestion accepts both.
- **No knowledge graph until Phase 3.** Phase 3 (Neo4j, relationship extraction, dependency queries) starts only after Phase 2 is validated. Do not add Neo4j infrastructure earlier.
- **Code extractor uses local git paths (gitpython), not GitHub API.** Configured via `code.repos[].path` in `onecontext.yaml`.
- **Feature workspace is the central delivery unit.** When a conversation belongs to a feature session, the agent automatically injects feature context (prior sessions, linked artefacts) into its system prompt.
- **`--all` flag on ingest skips manual review.** For demo/dev use only — do not use in production ingestion runs.
- **`JIRA_PROJECT_KEY` and `CONFLUENCE_SPACE_KEY` env vars are needed for write operations** (e.g. creating stories or pages back into the source systems).

## Issue tracking

This project uses `bd` (beads) for all task tracking. Do not use TodoWrite, TaskCreate, or markdown TODO files.

```bash
bd ready          # available work
bd show <id>      # issue detail
bd update <id> --claim
bd close <id>
```
