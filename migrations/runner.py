"""
migrations/runner.py — Postgres schema migration runner (server mode only).

Public entry point
------------------
    run_schema_migrations()

Behaviour
---------
1. Opens a connection and bootstraps ``data_migrations`` (CREATE TABLE IF NOT
   EXISTS) outside of any application-level migration so the table always
   exists before migrations are checked.
2. Reads the list of already-applied migration IDs from ``data_migrations``.
3. Iterates over MIGRATIONS (ordered list of (id, module) pairs), skipping any
   whose ID is already recorded.
4. Each pending migration is run inside a transaction:
   - calls ``module.run(conn)``
   - on success: records the ID in ``data_migrations`` and commits
   - on failure: rolls back and raises RuntimeError (stopping server startup)
5. Idempotent: a second startup with no pending migrations does nothing.

Desktop mode
------------
``run_schema_migrations()`` is a no-op in desktop mode (IS_DESKTOP=True).
"""

import os

# Mirror mode detection from db.py — importable without a live DB.
_APP_MODE = os.environ.get("APP_MODE", "desktop").lower()
IS_DESKTOP = _APP_MODE == "desktop"

# ── DB import (server mode only) ──────────────────────────────────────────────
# Import get_connection at module level so tests can patch it via
# ``patch("migrations.runner.get_connection")``.  In desktop mode db.py
# is importable (it just raises at call time), so this is safe everywhere.
from db import get_connection  # noqa: E402

# ── Migration registry ────────────────────────────────────────────────────────
# Add new migrations HERE, in order.  Never remove or reorder existing entries.

from migrations import v001_initial_schema  # noqa: E402

MIGRATIONS = [
    ("v001_initial_schema", v001_initial_schema),
]

# ── Bootstrap DDL ─────────────────────────────────────────────────────────────

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS data_migrations (
    id          TEXT        PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# ── Internal helpers ──────────────────────────────────────────────────────────


def _bootstrap(conn):
    """Create data_migrations table if it doesn't exist."""
    conn.execute(_BOOTSTRAP_SQL)
    conn.commit()


def _applied_ids(conn) -> set:
    """Return the set of migration IDs already in data_migrations."""
    rows = conn.execute("SELECT id FROM data_migrations").fetchall()
    return {row[0] for row in rows}


def _record_applied(conn, migration_id: str):
    """Insert a migration ID into data_migrations (within an open transaction)."""
    conn.execute(
        "INSERT INTO data_migrations (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
        (migration_id,),
    )


# ── Public entry point ────────────────────────────────────────────────────────


def run_schema_migrations():
    """
    Run all pending Postgres schema migrations at server startup.

    Safe to call on every startup — already-applied migrations are skipped.
    On migration failure the error is re-raised, stopping server startup.
    No-op in desktop mode.
    """
    if IS_DESKTOP:
        return

    # Step 1: bootstrap the tracking table
    conn = get_connection()
    try:
        _bootstrap(conn)
    finally:
        conn.close()

    # Step 2: determine which migrations are already applied
    conn = get_connection()
    try:
        applied = _applied_ids(conn)
    finally:
        conn.close()

    # Step 3: run pending migrations
    for migration_id, module in MIGRATIONS:
        if migration_id in applied:
            print(f"  [schema] Already applied: {migration_id}")
            continue

        print(f"  [schema] Applying migration: {migration_id} ...")
        conn = get_connection()
        try:
            module.run(conn)
            _record_applied(conn, migration_id)
            conn.commit()
            print(f"  [schema] Applied: {migration_id}")
        except Exception as exc:
            conn.rollback()
            conn.close()
            raise RuntimeError(
                f"Schema migration '{migration_id}' failed: {exc}"
            ) from exc
        finally:
            conn.close()
