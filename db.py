"""
db.py — Database connection helper for bulletin-generator (server mode only).

Provides:
  get_connection()   — open a psycopg3 connection from DATABASE_URL
  transaction()      — context manager: commit on success, rollback on exception
  health_check()     — returns {"connected": bool, "error": str|None}
  to_jsonb(obj)      — Python object → JSON string suitable for JSONB columns
  from_jsonb(s)      — JSON string / psycopg3 Jsonb → Python object

Desktop mode: DB functions raise RuntimeError immediately rather than crashing
on import, so the module is always importable.
"""

import json
import os
from contextlib import contextmanager

# ── Mode detection ────────────────────────────────────────────────────────────
# Mirror the logic in server.py so this module can be imported standalone.
_APP_MODE = os.environ.get("APP_MODE", "desktop").lower()
IS_DESKTOP = _APP_MODE == "desktop"

# ── JSONB helpers (no DB required) ────────────────────────────────────────────

def to_jsonb(obj) -> str:
    """Serialize a Python object to a JSON string for a JSONB column."""
    return json.dumps(obj, ensure_ascii=False)


def from_jsonb(value) -> object:
    """Deserialize a JSONB value (string or psycopg3 Jsonb wrapper) to Python."""
    if value is None:
        return None
    # psycopg3 may return already-decoded dicts/lists for jsonb columns
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    # Otherwise assume it's a JSON string
    return json.loads(value)


# ── Connection / transaction ──────────────────────────────────────────────────

def _require_server_mode():
    if IS_DESKTOP:
        raise RuntimeError(
            "Database operations are only available in server mode "
            "(APP_MODE=server). Set APP_MODE=server and provide DATABASE_URL."
        )


def get_connection():
    """
    Open and return a psycopg3 connection using the DATABASE_URL environment
    variable.  The caller is responsible for closing the connection.

    Raises:
        RuntimeError   — if called in desktop mode, or DATABASE_URL is unset/empty.
        psycopg.Error  — on connection failure.
    """
    _require_server_mode()

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Provide a valid PostgreSQL connection string."
        )

    import psycopg  # noqa: PLC0415  (deferred so desktop import stays clean)
    return psycopg.connect(url)


@contextmanager
def transaction():
    """
    Context manager that yields an open psycopg3 connection.

    On normal exit:   commits the transaction.
    On any exception: rolls back, then re-raises.
    The connection is always closed when the block exits.

    Usage::

        with transaction() as conn:
            conn.execute("INSERT INTO ...")
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def health_check() -> dict:
    """
    Test the database connection.

    Returns::

        {"connected": True,  "error": None}          — on success
        {"connected": False, "error": "<message>"}   — on failure
    """
    try:
        with transaction() as conn:
            conn.execute("SELECT 1")
        return {"connected": True, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": str(exc)}
