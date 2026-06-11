# One Context — Project Plan

## Guiding Principle

Each phase must prove value before the next begins. Every phase has a hard validation gate — a measurable outcome, not a feature checklist.

---

## Phase 0 — Data Hygiene Pipeline ✅ Complete

**Goal:** Clean, classified, enriched content ready for ingestion.

| Task | Status |
|---|---|
| Jira extractor (board-based) | ✅ Done |
| Confluence extractor (space-based) | ✅ Done |
| LLM classifier + quality scorer (Claude Haiku, batched) | ✅ Done |
| Staleness checker (rule-based) | ✅ Done |
| Deduplicator (sentence-transformers embeddings) | ✅ Done |
| LLM enricher (summary, entities, tags) | ✅ Done |
| Pipeline orchestrator | ✅ Done |
| CLI review queue | ✅ Done |
| Run against real data (board 1108, space CL) — 903 items approved | ✅ Done |
| Team review of flagged items | ✅ Done |

---

## Framework Foundation ✅ Complete

Built ahead of Phase 3 to avoid bespoke code accumulation.

| Task | Status |
|---|---|
| `BaseConnector` interface + `CONNECTOR_REGISTRY` | ✅ Done — `connectors/base.py`, `connectors/__init__.py` |
| `onecontext.yaml` config parser + validation | ✅ Done — `hygiene/config.py` |
| Refactor Jira + Confluence extractors to `BaseConnector` | ✅ Done |
| `GitHubExtractor` / `CodeExtractor` — local path + `gitpython` | ✅ Done — `hygiene/extractors/github_extractor.py` |
| Code-to-business summariser (Claude Haiku per module) | ✅ Done — `hygiene/processors/code_summariser.py` |
| Git history extractor (merged commits as `shipped_feature`) | ✅ Done |
| Pipeline updated to load from `onecontext.yaml` | ✅ Done |

**Current config:** board 1108, space CL, 14 repositories (ASX + Colleqt)
**Ingested:** 1,039 sources → 1,653 chunks in pgvector

---

## Phase 1 — Grounded Assistant ✅ Mostly Complete

**Goal:** Any team member can ask a question grounded in real team data.

### 1.1 Knowledge Store ✅

| Task | Status |
|---|---|
| PostgreSQL + pgvector via Docker | ✅ Done |
| Schema: chunks, memory, sources, conversations, messages | ✅ Done |
| Ingestion: hygiene → chunk → embed → pgvector | ✅ Done — 1,653 chunks |

### 1.2 LangGraph Agent ✅

| Task | Status |
|---|---|
| Agent scaffold: route → retrieve → reason → act → respond | ✅ Done — `agent/graph.py` |
| Tool: `search_knowledge(query)` — vector + memory search | ✅ Done |
| Tool: `get_jira_issue(key)`, `search_jira(query)` | ✅ Done — `agent/tools/jira_tools.py` |
| Tool: `search_confluence(query)` | ✅ Done — `agent/tools/confluence_tools.py` |
| Citation formatting: every answer links to source | ✅ Done |
| Team memory: `search_memory()` searched on every retrieval | ✅ Done |

### 1.3 API + Infrastructure ✅

| Task | Status |
|---|---|
| FastAPI backend — `agent/api.py` | ✅ Done |
| Celery + Redis — `agent/tasks.py` | ✅ Done |
| `sync_all` task (daily pipeline run) | ✅ Done |
| Docker Compose — postgres, redis, api, worker, beat | ✅ Done |
| Dockerfile | ✅ Done |
| Webhook stubs: `/webhooks/github`, `/webhooks/jira` | ✅ Done |

### 1.4 Remaining

| Task | ID | Status |
|---|---|---|
| Next.js chat UI | b5v.11/12 | 🔲 Pending |
| Delta sync (selective re-embed on change) | b5v.10 | 🔲 Pending — Celery task exists, not selective yet |
| Phase 1 validation gate: 10 questions vs ChatGPT | b5v.14 | 🔲 Pending |

---

## Phase 2 — Write + Remember ✅ Mostly Complete

**Goal:** Assistant creates stories, updates docs, remembers decisions, and manages Feature workspaces.

| Task | Status |
|---|---|
| Tool: `create_jira_story` with confirmation step | ✅ Done |
| Tool: `update_confluence_page` (append, not overwrite) | ✅ Done |
| Tool: `create_confluence_page` | ✅ Done |
| Story drafting flow: idea → context → draft → confirm → create | ✅ Done |
| Team memory: `remember()` writes to memory table with embedding | ✅ Done |
| Memory searched on every retrieval | ✅ Done |
| **Feature workspace**: named workspaces per delivery item | ✅ Done |
| Feature CRUD: create, list, get, update | ✅ Done |
| Feature sessions: per-role visits with context injection | ✅ Done |
| Feature links: auto-link Jira stories on creation | ✅ Done |
| Agent aware of feature context in sessions | ✅ Done |

### Remaining

| Task | ID | Status |
|---|---|---|
| Phase 2 validation gate: PO story creation time < 5 min | edx.8 | 🔲 Pending |
| Memory browser UI | edx.5 | 🔲 Pending (Web UI phase) |

---

## Phase 3 — Codebase Knowledge 🔄 In Progress

**Goal:** POs and BAs discover existing capabilities from the codebase. "The codebase is the bible."

| Task | Status |
|---|---|
| Code extractor: local path + gitpython | ✅ Done |
| Code-to-business summariser per module | ✅ Done |
| Two-level index: module summaries + file-level chunks | ✅ Done |
| Git history: merged commits as `shipped_feature` chunks | ✅ Done |
| 14 repos ingested (ASX + Colleqt) | ✅ Done |
| Role-based retrieval weighting | 🔲 Pending — `one-context-5or` |
| PR merge webhook: selective re-index | 🔲 Pending — `one-context-gnp` |
| Phase 3 validation gate: 10 PO questions from code only | 🔲 Pending — `one-context-ig0` |

---

## Phase 4 — Graph + Dependencies

**Goal:** Structural queries — dependency mapping, impact analysis, feasibility checks.
**Start condition:** Phase 3 validated.

| Task | ID | Status |
|---|---|---|
| Neo4j instance + schema | efg.1 | 🔲 Future |
| Relationship extraction: LLM → graph | efg.2 | 🔲 Future |
| Tool: `query_graph(natural_language)` | efg.3 | 🔲 Future |
| Feasibility analysis flow | efg.4 | 🔲 Future |
| Graph sync on delta sync | efg.5 | 🔲 Future |

---

## Phase 5 — Multi-Project Framework

**Goal:** Any team adopts One Context without writing code — configure `onecontext.yaml`, run Docker Compose.
**Start condition:** Phases 1–3 stable on primary project.

| Task | ID | Status |
|---|---|---|
| Docker image published | — | 🔲 Future |
| Adoption guide: zero to first answer < 30 min | e5d | 🔲 Future |
| Example connector (Linear or Notion) | — | 🔲 Future |

---

## Decisions Log

| Decision | Rationale | Date |
|---|---|---|
| pgvector over Qdrant/Chroma | One less service; Postgres handles structured + vector. | 2026-06-05 |
| sentence-transformers for embeddings | Runs locally, no API cost. 768d sufficient for team knowledge. | 2026-06-05 |
| Claude Haiku for classification/enrichment/code summary | 80% cost reduction vs Sonnet; structured output tasks. | 2026-06-05 |
| Board-based Jira extraction | Boards = team's curated view. Project keys pull irrelevant cross-team work. | 2026-06-05 |
| Code not embedded raw — LLM business summary first | POs ask in business terms. Raw code embeddings answer dev questions, not PO questions. | 2026-06-11 |
| Local path + gitpython over GitHub API | No rate limits, no token needed, any git host, instant file reads. | 2026-06-11 |
| Two-level code index (module + file) | L1 for capability discovery, L2 for file-level precision. | 2026-06-11 |
| Feature workspace (not Reference ID) | "Feature" is the natural word teams use. Workspace model is active, not a passive tag. | 2026-06-11 |
| Sessions per role visit, not one long conversation | Avoids unmanageable history; each session gets prior-session summaries as context. | 2026-06-11 |
| Shared conversation threads (not per-user) | The assistant is a team resource. Shared context prevents knowledge silos. | 2026-06-05 |
| No knowledge graph until Phase 4 | Query patterns unknown until RAG is validated. | 2026-06-05 |
| Framework extraction in Phase 5 | Build for one project first; extract when stable. | 2026-06-11 |
