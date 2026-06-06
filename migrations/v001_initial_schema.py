"""
migrations/v001_initial_schema.py — Collaboration v1 initial schema.

Creates all collaboration v1 tables.  Called by migrations/runner.py as the
first registered migration.  Idempotent via IF NOT EXISTS guards.
"""

SQL = """
-- Users: one row per authenticated identity
CREATE TABLE IF NOT EXISTS users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT        NOT NULL UNIQUE,
    display_name  TEXT        NOT NULL DEFAULT '',
    avatar_url    TEXT        NOT NULL DEFAULT '',
    domain        TEXT        NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sessions: short-lived auth tokens
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT        PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

-- Org-wide key/value settings (JSONB values)
CREATE TABLE IF NOT EXISTS org_settings (
    key         TEXT        PRIMARY KEY,
    value       JSONB       NOT NULL DEFAULT 'null',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-user key/value settings (JSONB values)
CREATE TABLE IF NOT EXISTS user_settings (
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key         TEXT        NOT NULL,
    value       JSONB       NOT NULL DEFAULT 'null',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, key)
);

-- Projects: the main document (bulletin)
CREATE TABLE IF NOT EXISTS projects (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT        NOT NULL DEFAULT '',
    owner_user_id       UUID        REFERENCES users(id) ON DELETE SET NULL,
    visibility          TEXT        NOT NULL DEFAULT 'workspace',
    state               JSONB       NOT NULL DEFAULT '{}',
    revision            INT         NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_email    TEXT        NOT NULL DEFAULT '',
    updated_by_email    TEXT        NOT NULL DEFAULT '',
    imported_from_json  BOOLEAN     NOT NULL DEFAULT false
);

-- Project revision history
CREATE TABLE IF NOT EXISTS project_revisions (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    revision          INT         NOT NULL,
    state             JSONB       NOT NULL DEFAULT '{}',
    saved_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    saved_by_user_id  UUID        REFERENCES users(id) ON DELETE SET NULL,
    saved_by_email    TEXT        NOT NULL DEFAULT '',
    saved_by_name     TEXT        NOT NULL DEFAULT '',
    summary           TEXT        NOT NULL DEFAULT ''
);

-- Announcements bank
CREATE TABLE IF NOT EXISTS announcements (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT        NOT NULL DEFAULT '',
    body        TEXT        NOT NULL DEFAULT '',
    url         TEXT        NOT NULL DEFAULT '',
    ordering    INT         NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Song database
CREATE TABLE IF NOT EXISTS songs (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT        NOT NULL DEFAULT '',
    author      TEXT        NOT NULL DEFAULT '',
    lyrics      TEXT        NOT NULL DEFAULT '',
    copyright   TEXT        NOT NULL DEFAULT '',
    source      TEXT        NOT NULL DEFAULT '',
    date_added  TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bulletin templates
CREATE TABLE IF NOT EXISTS templates (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL DEFAULT '',
    data        JSONB       NOT NULL DEFAULT '{}',
    built_in    BOOLEAN     NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Font registry (web fonts / uploaded fonts)
CREATE TABLE IF NOT EXISTS fonts (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug             TEXT        NOT NULL UNIQUE,
    family           TEXT        NOT NULL DEFAULT '',
    source           TEXT        NOT NULL DEFAULT '',
    css_url          TEXT        NOT NULL DEFAULT '',
    file_path        TEXT        NOT NULL DEFAULT '',
    upload_metadata  JSONB       NOT NULL DEFAULT '{}',
    cached_at        TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Applied schema migrations (bootstrap table — also created by runner bootstrap)
CREATE TABLE IF NOT EXISTS data_migrations (
    id          TEXT        PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def run(conn):
    """
    Execute the v001 initial schema DDL.

    ``conn`` is an open psycopg3 connection (not yet committed).
    The migration runner wraps this call in a transaction.
    """
    conn.execute(SQL)
