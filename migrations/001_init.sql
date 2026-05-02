-- 001_init.sql
-- Shared DB schema for linebot agents + k8scc MCP memory server.
-- Run once against the target PostgreSQL database.

CREATE TABLE IF NOT EXISTS episodes (
    id           SERIAL PRIMARY KEY,
    agent_id     TEXT NOT NULL,
    situation    TEXT NOT NULL,
    action       TEXT NOT NULL,
    result       TEXT NOT NULL,
    quality      FLOAT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS episodes_agent_time_idx ON episodes (agent_id, created_at DESC);

-- ALTER TABLE episodes ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE TABLE IF NOT EXISTS knowledge (
    id           SERIAL PRIMARY KEY,
    agent_id     TEXT NOT NULL,
    fact         TEXT NOT NULL,
    confidence   FLOAT NOT NULL DEFAULT 0.5,
    source_count INTEGER NOT NULL DEFAULT 1,
    updated_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, fact)
);

CREATE TABLE IF NOT EXISTS working_memory (
    id           SERIAL PRIMARY KEY,
    agent_id     TEXT NOT NULL,
    thread_id    TEXT NOT NULL,
    messages     JSONB NOT NULL,
    updated_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (agent_id, thread_id)
);
CREATE INDEX IF NOT EXISTS working_memory_lookup_idx ON working_memory (agent_id, thread_id);
