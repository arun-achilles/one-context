-- One Context — Knowledge Store Schema
-- Run: psql $DATABASE_URL -f db/schema.sql

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- fast text search on title/tags

-- -----------------------------------------------------------------
-- sources: tracks each ingested data source and last sync time
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,          -- e.g. "jira:CL-123", "confluence:12345"
    source_type TEXT NOT NULL,             -- "jira" | "confluence" | "github"
    external_id TEXT NOT NULL,             -- raw ID from the source system
    url         TEXT,
    last_synced TIMESTAMPTZ DEFAULT now(),
    metadata    JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(source_type);

-- -----------------------------------------------------------------
-- chunks: embedded content — one row per searchable chunk
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    content      TEXT NOT NULL,
    embedding    vector(768),              -- all-mpnet-base-v2 (local, no API key needed)
    content_type TEXT,                     -- decision | requirement | adr | spec | etc.
    tags         TEXT[]  DEFAULT '{}',
    entities     TEXT[]  DEFAULT '{}',
    summary      TEXT,
    url          TEXT,
    last_updated TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_source    ON chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_type      ON chunks(content_type);
CREATE INDEX IF NOT EXISTS idx_chunks_tags      ON chunks USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_chunks_entities  ON chunks USING GIN(entities);

-- Vector similarity index (IVFFlat — good up to ~1M rows)
-- Create AFTER initial bulk load for speed; recreate if recall drops.
-- CREATE INDEX idx_chunks_embedding ON chunks
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- -----------------------------------------------------------------
-- memory: explicit team decisions, agreements, blockers
--         never auto-deleted; always searched alongside chunks
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory (
    id              BIGSERIAL PRIMARY KEY,
    content         TEXT NOT NULL,          -- the remembered fact
    context         TEXT,                   -- surrounding context / why it matters
    author          TEXT,                   -- who said it
    related_sources TEXT[] DEFAULT '{}',    -- source_ids this memory is linked to
    tags            TEXT[]  DEFAULT '{}',
    embedding       vector(768),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_tags    ON memory USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_memory_sources ON memory USING GIN(related_sources);

-- -----------------------------------------------------------------
-- conversations: shared threads per topic (not per user)
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id         BIGSERIAL PRIMARY KEY,
    topic      TEXT NOT NULL,              -- e.g. epic name, feature name, free-form
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,         -- "user" | "assistant"
    content         TEXT NOT NULL,
    author          TEXT,                  -- human team member name (null for assistant)
    cited_sources   TEXT[] DEFAULT '{}',   -- source_ids cited in this message
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

-- -----------------------------------------------------------------
-- features: named workspaces shared across PO, Tech Lead, Dev
--           exists before a Jira epic; creates and links one
-- -----------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS feature_seq START 1;

CREATE TABLE IF NOT EXISTS features (
    id          TEXT PRIMARY KEY DEFAULT 'OC-' || LPAD(nextval('feature_seq')::TEXT, 3, '0'),
    name        TEXT NOT NULL,
    description TEXT,
    status      TEXT DEFAULT 'planned',   -- planned | in_progress | shipped | paused
    jira_epic   TEXT,                     -- e.g. CL-890, linked after PO creates epic
    created_by  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- feature_sessions: each role visit = one conversation + summary
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feature_sessions (
    id              BIGSERIAL PRIMARY KEY,
    feature_id      TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT,        -- po | tech_lead | dev | em
    author          TEXT,        -- name of the person
    summary         TEXT,        -- auto-generated when session ends
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- -----------------------------------------------------------------
-- feature_links: artefacts created/linked during feature work
-- -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feature_links (
    id          BIGSERIAL PRIMARY KEY,
    feature_id  TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    link_type   TEXT NOT NULL,   -- jira_story | jira_task | jira_epic | confluence_page | github_pr | memory
    link_id     TEXT NOT NULL,   -- external ID or internal memory id
    link_url    TEXT,
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feature_sessions_feature ON feature_sessions(feature_id);
CREATE INDEX IF NOT EXISTS idx_feature_links_feature    ON feature_links(feature_id);
