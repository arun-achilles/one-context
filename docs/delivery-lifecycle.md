# One Context — Delivery Lifecycle

This document describes how the co-pilot is used by each role in the delivery lifecycle, with concrete example interactions and what the system returns.

---

## Foundation: Understanding the Existing System

Before planning any new work, any team member can query what the system already does.

**Example prompts:**

> "What payment methods do we support?"

System searches: code capability index (payment module summaries), Confluence (payment docs), Jira (closed payment stories).

> "Do we have an affiliate or referral system?"

System searches: code capability index (feature existence check), git history (was one ever built and removed?), Jira (any prior epics?).

> "What external services does the checkout service depend on?"

System searches: integration map extracted from checkout service source code.

**Returned:** Business-language answer with citations linking to source files, Confluence pages, and Jira tickets. Answers are grounded in actual code — not documentation that may be out of date.

---

## PO / BA Workflow

### Step 1 — Discover what already exists

Before writing a single story, the PO queries the codebase and existing knowledge.

> "We're thinking about adding a gift card feature. What exists in the codebase that could be relevant?"

System searches code capability index for: payment flows, voucher/redemption logic, stored value patterns.

**Returned:**
```
Relevant existing capabilities:
  • Voucher redemption (payments/voucher.py) — handles single-use discount codes,
    integrated with checkout. Shipped March 2025 (PR #412, PROJ-821).
  • Loyalty points balance (accounts/loyalty.py) — stores and redeems point balances.
    Not currently exposed in checkout.
  • No gift card or stored value flow found.

Suggested starting point: voucher.py handles the redemption pattern.
Gift cards would need: stored value persistence, balance top-up, partial redemption.
```

### Step 2 — Check prior decisions and attempts

> "Has a gift card feature been attempted or discussed before?"

System searches: closed Jira epics, Confluence search, team memory.

**Returned:**
```
Found in Jira: PROJ-344 (closed, Dec 2024) — "Gift card MVP". Marked won't-do.
  Reason from comments: "Deprioritised due to payment provider not supporting
  stored value without an enterprise contract upgrade."

Found in team memory: "Gift card paused until payment provider contract renewed
  (Q1 2026 target)" — noted by Sarah M., 2025-01-14.
```

### Step 3 — Draft the epic and stories

> "Draft a gift card epic and the first 3 stories based on what you found."

System retrieves: existing voucher implementation details, PROJ-344 prior context, payment provider constraints from memory.

**Returned:** Structured epic draft + 3 stories with acceptance criteria, pre-filled with context from the existing codebase and prior decisions. PO reviews and approves.

### Step 4 — Create in Jira and Confluence

> "Create the epic and stories. Also create a Confluence spec page for the gift card feature."

System creates: Jira epic + stories, Confluence spec page. Assigns **Reference ID** `OC-089`.

**Returned:**
```
Created:
  Jira epic: PROJ-890 "Gift Card Feature"
  Jira stories: PROJ-891, PROJ-892, PROJ-893
  Confluence page: "Gift Card — Product Spec" (linked to PROJ-890)
  Reference ID: OC-089

All items linked. Use "show me OC-089" at any time to pull full context.
```

---

## Tech Lead / Feature Owner Workflow

### Step 1 — Load the Reference ID

> "Show me everything about OC-089"

**Returned:** Product spec, existing voucher code context, payment provider constraint, all linked Jira stories, prior attempt (PROJ-344).

### Step 2 — Impact and dependency analysis

> "What services and teams does OC-089 touch?"

System searches: code integration map for voucher and accounts services, Jira ownership labels.

**Returned:**
```
Services touched:
  • payments-service (owner: Payments Team) — voucher.py needs extension
  • accounts-service (owner: Platform Team) — loyalty.py for balance model
  • checkout-service (owner: Checkout Team) — checkout flow integration

External dependencies:
  • Stripe (payment provider) — stored value requires enterprise contract
  • SendGrid — gift card delivery email (new integration needed)
```

### Step 3 — Draft tech tasks and architecture

> "Draft the tech tasks for OC-089 and create a Confluence tech design page."

System drafts: tech tasks grounded in the service map, creates Confluence page with architecture diagram stub.

**Created:**
```
Jira tech tasks: PROJ-894 (payments), PROJ-895 (accounts), PROJ-896 (checkout), PROJ-897 (email)
Confluence page: "Gift Card — Technical Design" (linked to OC-089)
```

---

## Developer Workflow

### Step 1 — Understand the story context

> "Show me everything about PROJ-891"

System looks up PROJ-891 → finds Reference ID OC-089 → returns full context.

**Returned:** Product spec excerpt relevant to PROJ-891, tech design for payments service changes, existing `voucher.py` implementation, related team memories, linked ADRs.

### Step 2 — Deep dive into existing code

> "How does the existing voucher redemption work in payments-service?"

System retrieves: code capability chunk for `payments/voucher.py`, with business-language summary and relevant implementation detail.

> "Show me the actual current code for voucher.py"

System fetches live from GitHub API (targeted single-file fetch) and returns current source.

### Step 3 — Implementation

Developer implements. PR created. On PR merge:
- Webhook fires → system re-extracts changed files (`payments/voucher.py`, new `payments/giftcard.py`)
- LLM re-summarises affected modules
- Code capability index updated within minutes
- `sources` table upserted with new `last_synced` timestamp

Next PO query about gift cards will include the updated implementation.

---

## Reference ID Lifecycle

```
OC-089 created (by PO/system on epic creation)
  │
  ├── Jira: PROJ-890 (epic), PROJ-891–893 (stories), PROJ-894–897 (tech tasks)
  ├── Confluence: Product Spec page, Technical Design page
  ├── GitHub: PR #501, PR #502 (merged, linked by PR description)
  ├── Team memory: "Gift cards require Stripe enterprise contract" (from Phase 0 discovery)
  └── Code index: payments/giftcard.py, accounts/stored_value.py (after PR merge)
```

Any team member, at any point, can ask:
- "What's the status of OC-089?" → Jira story statuses
- "What was decided about OC-089?" → team memory + ADRs
- "What code was shipped for OC-089?" → PR links + updated capability index
- "Is OC-089 fully implemented?" → compare stories vs code capability index

---

## The Knowledge Flywheel

Each delivery cycle makes the system more useful for the next:

```
PO discovers capability → uses it in new story
    → story delivered → code updated → capability index updated
    → next PO question gets more accurate answer
    → team memory captures decisions → surfaces in next similar story
    → less redundant discovery work each cycle
```

The system gets more accurate and complete over time without any manual maintenance.
