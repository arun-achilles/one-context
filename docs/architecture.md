# One Context — Architecture

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Data Sources                                │
│                                                                     │
│   Jira          Confluence          GitHub / Codebase               │
│  (planned)      (documented)        (actually built — ground truth) │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  connectors/  (pluggable per source)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Hygiene Pipeline                                │
│                                                                     │
│  Extract → Classify → Quality Score → Staleness → Dedup → Enrich   │
│                                                                     │
│  Code-only additional stage:                                        │
│  Code files → LLM: business-language summary → standard hygiene    │
│                                                                     │
│  Route: auto-include (q≥4) | review queue (q 2-3) | reject (q≤1)  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                Ingestion: Chunk → Embed → Load                      │
│                                                                     │
│  Jira/Confluence: semantic chunking by section                      │
│  Code: module-level summaries (L1) + file-level chunks (L2)         │
│  Embedder: sentence-transformers all-mpnet-base-v2 (768d, local)    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Knowledge Store (PostgreSQL + pgvector)        │
│                                                                     │
│  sources          — one row per ingested item                       │
│  chunks           — embedded content (content_type, tags, entities) │
│  memory           — explicit team decisions, never auto-deleted      │
│  conversations    — shared threads per topic (not per-user)         │
│  messages         — conversation history with cited_sources[]       │
│  features         — Feature workspaces (OC-001, OC-002...)          │
│  feature_sessions — per-role sessions linked to a feature           │
│  feature_links    — Jira stories, Confluence pages, PRs, memories   │
│                                                                     │
│  Phase 4+: Neo4j for graph relationships (alongside Postgres)       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   LangGraph Agent (FastAPI)                         │
│                                                                     │
│  State: messages, intent, feature_id, retrieved_chunks,             │
│         answer, citations, needs_clarification, pending_action      │
│                                                                     │
│  Graph: route → retrieve → reason → act → respond                  │
│  (confirm_action bypasses retrieve+reason → straight to act)        │
│                                                                     │
│  Read tools:                                                        │
│  ├── search_knowledge(query)    → pgvector + memory combined        │
│  ├── search_memory(query)       → team memory semantic search       │
│  ├── get_jira_issue(key)        → Jira API live lookup              │
│  ├── search_jira(query)         → Jira JQL search                  │
│  └── search_confluence(query)   → Confluence API search             │
│                                                                     │
│  Write tools (require yes confirmation):                            │
│  ├── create_jira_story(draft)   → Jira API + auto-link to feature  │
│  ├── update_confluence_page()   → append/prepend, never overwrite  │
│  ├── create_confluence_page()   → Confluence API                   │
│  └── remember(fact, context)    → memory table with embedding       │
│                                                                     │
│  Feature tools (no confirmation needed):                            │
│  ├── build_feature_context(id)  → primed context for sessions      │
│  ├── link_artefact(feature_id)  → adds to feature_links table      │
│  └── get_feature_for_conversation() → reverse lookup               │
│                                                                     │
│  LLM: Claude Sonnet 4.6 (reasoning, drafting, synthesis)            │
│       Claude Haiku 4.5 (classification, enrichment, code summary)   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              FastAPI (agent/api.py) + Celery (agent/tasks.py)       │
│                                                                     │
│  POST/GET  /features              — Feature workspace CRUD          │
│  POST      /features/{id}/sessions — start session, get context    │
│  GET/PATCH /features/{id}/sessions — list / update summary         │
│  POST/GET  /features/{id}/links   — link artefacts                 │
│  POST      /conversations/{id}/chat — SSE streaming chat           │
│  POST      /webhooks/github|jira  — enqueue Celery re-sync task    │
│  GET       /health                — liveness + DB check            │
│                                                                     │
│  Celery tasks: sync_all (daily), sync_pr (PR merge), sync_issue    │
│  Beat schedule: sync_all every 24h                                  │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Web Interface (Next.js) — Phase 1.5              │
│                                                                     │
│  ├── Feature list + session resume                                  │
│  ├── Chat with streamed responses and citations                     │
│  ├── Memory browser (view/edit/delete team memories)                │
│  └── Review queue (hygiene approvals)                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Codebase Knowledge Layer

Code is not embedded raw and does not use the GitHub API. It is read from **local git clones** using `pathlib.rglob()` and `gitpython`. This means no rate limits, no token required, and works with any git host (GitHub, GitLab, Bitbucket, self-hosted).

Repos are configured in `onecontext.yaml` under `code.repos[].path`. If a URL is given instead, the repo is auto-cloned to `~/.one-context/repos/`.

Code passes through a business translation step before embedding:

```
Local git repo (path configured in onecontext.yaml)
  │
  ├── Source files (*.py, *.ts, *.java, ...)
  │       → LLM reads module (directory of related files)
  │       → Generates: what does this module do in business terms?
  │                    what flows/features does it implement?
  │                    what external services does it call?
  │                    what domain entities does it manage?
  │       → Stored as content_type: business_flow | api_capability |
  │                                 integration | domain_entity
  │
  ├── OpenAPI / Swagger specs
  │       → Endpoint summaries: method, path, purpose, request/response
  │       → Stored as content_type: api_capability
  │
  └── git log (last 12 months, PR merges only)
          → "What shipped": PR title + description as feature narrative
          → Stored as content_type: shipped_feature, tagged by date
```

### Two-Level Code Index

| Level | Content | Granularity | Re-indexed when |
|---|---|---|---|
| L1 — Service/module summaries | What the whole module does; flows owned; integrations | 1 chunk per directory/module | Structural changes (new files, deleted files) |
| L2 — File-level capability chunks | Specific flows, endpoints, entities per file | 1–N chunks per source file | Any file change (PR merge webhook) |

L1 answers "does a gift card capability exist?" in one retrieval. L2 answers "show me how voucher redemption is implemented" with file-level precision.

### Live File Fetch (escape hatch)

When a developer needs precise current code (not a summary), the agent fetches the specific file live from GitHub API. This is always targeted — 1–3 files identified from L2 retrieval — never a whole-repo scan.

---

## Connector / Plugin Architecture

```
connectors/
  base.py           → BaseConnector: extract(config) -> [RawItem]
  jira/             → board-based extraction, handles pagination + auth
  confluence/       → space-based extraction, HTML → plain text
  github/           → file tree + LLM summarisation + git history
  <custom>/         → implement BaseConnector, register in CONNECTOR_REGISTRY
```

Each connector is responsible only for extraction. The `RawItem` it returns is the contract — hygiene, chunking, embedding, and loading are source-agnostic.

Project configuration lives in `onecontext.yaml`. The connector registry maps source type keys to connector classes. Adding a new source requires only a new connector class and one line in the registry.

See `docs/connectors.md` for the full interface specification and an implementation example.

---

## Feature Workspace

Features replaced the earlier "Reference ID" concept. A Feature is an active delivery workspace, not a passive tag.

### Schema

```sql
-- Auto-incremented IDs: OC-001, OC-002...
CREATE SEQUENCE feature_seq START 1;

CREATE TABLE features (
    id          TEXT PRIMARY KEY DEFAULT 'OC-' || LPAD(nextval('feature_seq')::TEXT, 3, '0'),
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT DEFAULT 'planned',   -- planned | in_progress | shipped | paused
    jira_epic   TEXT,                     -- linked after PO creates the epic
    created_by  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Each role visit = one conversation + summary injected into next session
CREATE TABLE feature_sessions (
    id              BIGSERIAL PRIMARY KEY,
    feature_id      TEXT REFERENCES features(id),
    conversation_id BIGINT REFERENCES conversations(id),
    role            TEXT,        -- po | tech_lead | dev | em
    author          TEXT,
    summary         TEXT,        -- auto-generated on session close
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Auto-linked when artefacts are created inside a session
CREATE TABLE feature_links (
    id          BIGSERIAL PRIMARY KEY,
    feature_id  TEXT REFERENCES features(id),
    link_type   TEXT NOT NULL,   -- jira_story | jira_task | confluence_page | github_pr | memory
    link_id     TEXT NOT NULL,
    link_url    TEXT,
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

### Session flow

```
POST /features/OC-001/sessions {role: "po", author: "sarah"}
    │
    ▼
1. Create conversation (topic = feature name)
2. Create feature_sessions row
3. build_feature_context(OC-001) → primed context string
   - Feature name, description, status
   - Prior session summaries (last 5)
   - Linked artefacts grouped by type
4. Return {conversation_id, feature_context}

POST /conversations/{id}/chat {message: "..."}
    │
    ▼
Feature context injected as first message pair in history
Agent knows it is working in OC-001 context throughout the session

"yes" (confirming story draft)
    │
    ▼
create_jira_story() → CL-XXX
link_artefact(OC-001, "jira_story", "CL-XXX")  ← auto
```

---

## LangGraph Agent

### State (current — `agent/state.py`)

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str | None            # qa | story_draft | remember | pipeline_query | confirm_action | clarify
    retrieved_chunks: list[dict]
    answer: str | None
    citations: list[dict]         # [{url, score}]
    needs_clarification: bool
    pending_action: dict | None   # write action awaiting user confirmation
    feature_id: str | None        # set if conversation belongs to a feature session
```

### Graph Nodes

```
route     — classify intent; fast-path confirmation regex; detect pending draft
retrieve  — pgvector search + memory search combined; confirm_action bypasses this
reason    — Claude Sonnet Q&A / story draft / memory prep; injects feature context
act       — execute confirmed write: create_jira_story (+ auto-link) | remember
respond   — format answer; strip hidden <!-- PENDING_ACTION --> marker from display
```

### Confirmation Pattern

Write actions use a hidden JSON marker in the assistant message:
```
<!-- PENDING_ACTION: {"type": "create_jira_story", "title": "...", ...} -->
```
On the next turn, `router_node` detects "yes/go ahead/create it" + marker present → `intent = confirm_action` → route straight to `act_node` which extracts and executes the action.

### Role-Based Retrieval Weighting

The `search_knowledge` tool accepts a `role_context` parameter that adjusts content-type weighting in the similarity query:

| Role | Upweighted content types | Downweighted |
|---|---|---|
| `po` | `business_flow`, `api_capability`, `requirement`, `shipped_feature` | raw technical specs |
| `tech_lead` | `adr`, `integration`, `domain_entity`, `decision` | high-level summaries |
| `dev` | `api_capability`, `domain_entity`, `integration`, `adr` | project management content |
| `em` | `requirement`, `blocker`, `shipped_feature` | implementation details |

Role is detected from conversation context or explicitly set by the user ("as a PO, ...").

---

## Delta Sync — Webhook-Triggered

```
PR merged on GitHub
    → webhook fires → POST /webhooks/github
    → extract changed files from PR diff
    → re-run code summariser on affected modules
    → upsert chunks for those files (L2) and re-generate module summary (L1) if needed
    → update sources.last_synced

Jira issue updated
    → webhook fires → POST /webhooks/jira
    → re-extract that issue
    → re-run hygiene (classify, stale check, enrich)
    → upsert source + chunks

Confluence page updated
    → webhook fires → POST /webhooks/confluence
    → same as Jira flow

Scheduled daily reconciliation (Celery Beat, 02:00)
    → full pull for all sources
    → compare last_updated vs sources.last_synced
    → re-process any items changed since last sync
    → catches any missed webhooks
```

---

## Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Agent orchestration | LangGraph | Stateful workflows, native tool use |
| LLM (reasoning) | Claude Sonnet 4.6 | Best instruction following for synthesis and drafting |
| LLM (classification, enrichment, code summary) | Claude Haiku 4.5 | 80% cost reduction; structured output tasks |
| Vector store | pgvector (PostgreSQL) | One less service; Postgres handles structured + vector in one query |
| Background jobs | Celery + Redis | Reliable task queue for sync jobs and webhook processing |
| Backend API + webhooks | FastAPI | Async, Python-native |
| Frontend | Next.js + TypeScript | |
| Jira/Confluence | atlassian-python-api | Mature, handles auth and pagination |
| Embeddings | sentence-transformers `all-mpnet-base-v2` (local, 768d) | No API cost, runs on-device |
| Graph (Phase 4) | Neo4j | Relationship queries vector search cannot answer |

---

## Data Flow: Story Drafting (PO Workflow)

```
PO: "Draft a story for improving checkout performance"
    │
    ▼
route: intent=story_draft, role_context=po
    │
    ▼
retrieve (parallel):
  - vector search (po-weighted): "checkout performance"
    → content_types: [business_flow, api_capability, requirement, shipped_feature]
    → returns: prior perf work, existing checkout flow description, prior stories
  - Jira search: open stories in checkout epic
  - memory search: any remembered constraints on checkout
    │
    ▼
reason: Claude Sonnet synthesises context, drafts story
  - Title, description, ACs grounded in what's already implemented
  - Flags: "Note: previous investigation (PROJ-421) found bottleneck in
    inventory API, not DB. checkout/inventory_client.py calls /v2/availability
    synchronously on every cart update. See Confluence: Checkout Perf Analysis"
    │
    ▼
act: present draft to user, await confirmation
    │
    ▼
create_jira_story(draft) → PROJ-XXX
update_reference(OC-078, jira_stories=[PROJ-XXX])
remember("Checkout perf story PROJ-XXX: bottleneck confirmed as inventory API sync call")
    │
    ▼
respond: "Created PROJ-XXX. Context I used: [citations with links]"
```

---

## Phase 4 Extension: Knowledge Graph

When graph relationships are needed (dependency mapping, impact analysis), Neo4j is added alongside PostgreSQL — not as a replacement.

- **Nodes**: Feature, Service, Team, Decision, Story, Developer
- **Edges**: DEPENDS_ON, OWNED_BY, DECIDED_BY, IMPLEMENTS, BLOCKS, SHIPPED_IN
- **Population**: LLM extracts relationships from enriched chunks on each sync
- **New tool**: `query_graph(natural_language)` → NL to Cypher → result
- **Sync**: graph updated on each delta sync run alongside pgvector upsert

---

## Security and Access

- All credentials in environment variables, never in `onecontext.yaml` or code
- The assistant inherits permissions of its service account — start read-only, add write permissions after Phase 1 validation
- Team memory is shared — no per-user private memory in v1
- Write operations require explicit user confirmation before execution
- No PII stored beyond what is already in Jira/Confluence
