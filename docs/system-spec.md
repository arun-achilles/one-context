# One Context — System Specification

## Problem

Software teams lose delivery context across tools, people, and time. Each role holds only a fragment of the picture:

- The **PO** writes stories without knowing what's already built in the codebase
- The **Tech Lead** assesses feasibility without a complete view of what services and decisions exist
- The **Developer** picks up a story without understanding the "why" behind it
- The **EM** tracks risk without a single view across Jira, architecture, and team decisions

Context that should flow from discovery → planning → design → development instead gets reconstructed from scratch every sprint, scattered across Slack threads, stale Confluence pages, closed Jira tickets, and tribal knowledge.

---

## Vision

**One Context is an AI Delivery Co-Pilot** — a shared intelligence layer that continuously understands:

- Confluence knowledge (decisions, architecture docs, design specs, ADRs)
- Jira history (stories, epics, blockers, completed work)
- Source code repositories (existing flows, capabilities, integrations, domain model)
- Architecture documents (system design, service dependencies)
- Design decisions (ADRs, team agreements, what was tried and rejected)

Every team member — PO, BA, Tech Lead, Developer, EM — asks the system questions and creates artefacts through it. The system grounds every answer in real team data and cites its sources.

---

## The Ground Truth Principle

Three sources, three views of the same system:

| Source | What it represents |
|---|---|
| Jira | What was **planned** |
| Confluence | What was **documented** |
| Codebase | What was **actually built** |

These diverge. Stories get closed without all ACs implemented. Confluence pages go stale. The codebase is the ground truth. When a PO asks "do we support X?", the answer must come from the code — not from a ticket marked done 18 months ago.

---

## Delivery Lifecycle Workflow

The co-pilot serves each role in sequence, with each role's output becoming context for the next.

```
FOUNDATION
  Historic Jira + Confluence + Codebase
      → RAG + Knowledge Graph
      → "What does our system do today?"

        ↓

PO / BA  (Discover & Plan)
  Ask:   "What flows/capabilities exist in the codebase for feature X?"
  Ask:   "Has anything like this been built or attempted before?"
  Draft: Epic + Stories (grounded in existing capabilities and past decisions)
  Write: Jira epic/stories + Confluence spec page
  Gets:  Reference ID — the spine that ties all work items together

        ↓

TECH LEAD / FEATURE OWNER  (Analyse & Design)
  Ask:   "What services/components does [Reference ID] touch?"
  Ask:   "What are the dependencies and risks?"
  Draft: Tech tasks in Jira, architecture diagrams in Confluence
  Write: All linked to the same Reference ID

        ↓

DEVELOPER  (Implement)
  Ask:   "Give me everything about [Reference ID]"
  Gets:  Spec + tech design + relevant existing code + remembered decisions
  PR merged → code knowledge base updated automatically
```

### Reference ID

Each feature/epic is assigned a Reference ID (`OC-xxx` or the Jira epic key). It is stored in the system and links together:
- The Jira epic and all child stories
- The Confluence spec page and tech design page
- GitHub PRs that implement it
- Architecture decisions made during it
- Team memories recorded about it

Any team member can ask "show me everything about OC-042" and get the full picture across all sources.

---

## Feature Workspaces

### What a Feature Is

A Feature is a named, persistent workspace that spans all roles working on a piece of delivery. It exists in One Context before a Jira Epic is created — and creating a Feature triggers the creation of the corresponding Jira Epic automatically.

Features are identified by a sequential ID: `OC-001`, `OC-002`, and so on. This ID becomes the Reference ID that links all downstream artefacts (Jira epic, Confluence pages, GitHub PRs, decisions).

Scope rule: a Feature is appropriate for **multi-sprint, multi-role work** — anything that involves discovery, design, and implementation across more than one sprint. Single-sprint, well-understood work goes straight to Jira stories without a Feature Workspace.

### Why Sessions Instead of One Infinite Conversation

Each time a team member visits a Feature — regardless of role — the system starts a new **Session** rather than resuming one long conversation. This is deliberate:

- Long conversations accumulate noise, drift in focus, and become expensive to context-manage
- Different roles need different slices of the same history
- Sessions provide a clean audit trail: who engaged with this Feature, when, and in what capacity

When a new Session opens, the system injects a **session brief**: a structured summary of all prior sessions for that Feature, covering decisions made, artefacts created, open questions, and the current state of the work. The new conversation starts informed without being overwhelmed.

### What Accumulates Inside a Feature

Every artefact created during a Session is auto-linked to the Feature:

| Artefact | How it links |
|---|---|
| Jira stories and tasks | Tagged with the Feature ID at creation |
| Confluence pages | Created with the Feature ID in metadata and page title |
| GitHub PRs | Linked via PR description convention or webhook on merge |
| Team memories | Stored with Feature ID as a scoping attribute |
| Session summaries | Appended to the Feature's history on session close |

Any team member can query "show me everything about OC-042" and retrieve the complete picture across all linked artefacts and session history.

### Feature Status Lifecycle

| Status | Meaning |
|---|---|
| `planned` | Feature created; no active delivery work started |
| `in_progress` | At least one Session has been opened and work is underway |
| `shipped` | All linked stories closed; Feature marked complete |
| `paused` | Work stopped deliberately; context preserved for resumption |

---

## Roles and What Each Gets

### Product Owner / Business Analyst

| Need | What the system provides |
|---|---|
| Understand existing system before planning | Code capability search: "Do we have a voucher/discount system?" |
| Discover what's reusable | Module and flow summaries from the codebase in business language |
| Write well-formed stories | Story drafting: idea → context retrieval → draft with ACs → Jira creation |
| Know what was tried before | Git history and closed Jira epics surface prior attempts |
| Document decisions | Confluence write-back: spec pages created and linked to Reference ID |

### Tech Lead / Feature Owner

| Need | What the system provides |
|---|---|
| Assess feasibility | Query which services a feature touches and who owns them |
| Understand existing architecture | Architecture doc search + ADR retrieval |
| Create tech tasks | Tech task drafting grounded in the spec and existing design |
| Document design decisions | Confluence diagram pages created and linked to Reference ID |
| Know about past technical decisions | ADR search + team memory retrieval |

### Developer

| Need | What the system provides |
|---|---|
| Understand the "why" before picking up a story | Full Reference ID context: spec + tech design + decisions + code |
| Find relevant code context | Code search: "Show me how payments handles retries" |
| Understand domain and service boundaries | Domain entity map and integration map from codebase |
| Learn from prior implementations | Git history: how similar features were built |

### Engineering Manager

| Need | What the system provides |
|---|---|
| Track what's in flight | Pipeline view: open epics, blockers, at-risk items |
| Understand risk | Cross-reference Jira blockers with architecture dependencies |
| Onboard new team members | Full context for any epic or feature via Reference ID |

---

## Knowledge Sources

| Source | Type | Written by |
|---|---|---|
| Jira | External | Team via Jira; agent-assisted drafting |
| Confluence | External | Team via Confluence; agent-assisted drafting |
| GitHub / Source Code | External | Engineers via PRs |
| Team Memory | Internal | Explicit `remember` calls during conversations |
| Feature Workspace | Internal | Written via agent sessions, never auto-deleted |

### Jira
- Extraction: board-based (not project keys) — boards represent the team's curated view
- Content: stories, epics, acceptance criteria, comments, blockers, labels
- Sync: webhook-triggered on item update + daily reconciliation
- Content types indexed: `requirement`, `decision`, `blocker`

### Confluence
- Extraction: space-based
- Content: architecture docs, ADRs, specs, design decisions, meeting notes
- Sync: webhook-triggered on page update + daily reconciliation
- Content types indexed: `adr`, `spec`, `decision`, `reference`

### GitHub / Source Code
- Extraction: repo-based, configurable per service
- What is extracted:
  - **Module summaries**: LLM reads source files, produces business-language description of what each module does, what flows it owns, what it integrates with
  - **Capability index**: what features/flows are implemented, tagged by capability type
  - **Integration map**: external APIs, databases, queues the service calls
  - **Domain entity map**: core business objects and their relationships
  - **OpenAPI/Swagger specs**: endpoint summaries in plain language
  - **Git history**: PR titles + merge commits (last 12 months) — narrative of what shipped and when
- Sync: PR merge webhook → re-extract changed files only → re-summarise affected modules → upsert. Scheduled daily full reconciliation as fallback.
- Content types indexed: `business_flow`, `api_capability`, `integration`, `domain_entity`, `shipped_feature`

### Team Memory
- Written explicitly via the `remember` tool during conversations
- Never auto-deleted; always searched alongside other content
- Attribution: who said it, when, which conversation
- Content type: `team_memory`

---

## Multi-Project Adoption

One Context is designed as a framework — any team can adopt it without writing code.

Each project provides a `onecontext.yaml` configuration file:

```yaml
project: my-project
sources:
  jira:
    url: https://myorg.atlassian.net
    boards: [1108, 1245]
    custom_fields:
      epic_link: customfield_10014
      acceptance_criteria: customfield_10016
  confluence:
    spaces: [TEAM, ARCH]
  github:
    repos:
      - org/checkout-service
      - org/payments-service
    summarize_at: module        # service | module | file
    include: ["**/*.py", "**/*.ts", "**/openapi.yaml"]
    exclude: ["**/tests/**", "**/migrations/**"]
    git_history_months: 12
hygiene:
  staleness_months: 12
  min_quality_auto: 4           # quality >= this → auto-included
  min_quality_review: 2         # quality >= this → pending review, else rejected
```

Each source connector is a plugin implementing a standard interface. Built-in connectors: Jira, Confluence, GitHub. Community connectors can implement `BaseConnector` to add Linear, Notion, GitLab, Azure DevOps, and others.

The system is distributed as a Docker Compose stack — teams supply their `onecontext.yaml` and `.env`, run `docker compose up`, and have a running instance within minutes.

---

## Data Hygiene

All sources pass through the hygiene pipeline before indexing. This is non-negotiable — quality of retrieval depends entirely on quality of indexed content.

Pipeline stages:
1. **Extract** — pull from source APIs via connector
2. **Classify** — LLM assigns content type and quality score 1–5
3. **Staleness check** — rule-based, flags content > N months old or containing deprecation signals
4. **Deduplication** — embedding similarity, keeps most recent version
5. **Enrich** — LLM generates summary, extracts entities and tags
6. **Route** — auto-include (quality 4–5, not stale), pending review (quality 2–3 or stale), reject (quality 1 or noise)

Code content has an additional stage: **code-to-business translation** — LLM reads source files and produces business-language summaries before the standard hygiene steps.

---

## Quality and Trust

Every answer cites its source (Jira ticket, Confluence page, GitHub file, git commit) with a link. The system says "I don't know" when confidence is low rather than hallucinating. Team memory entries are attributed to who said them and when. Write operations (Jira story creation, Confluence page update) require explicit user confirmation before executing.

---

## Out of Scope (current)

- Real-time Slack/meeting ingestion
- Per-user private memory (all memory is team-scoped)
- Fine-tuned models
- Multi-org / multi-tenant SaaS
- KAG (knowledge-augmented generation) — revisit after Phase 4
