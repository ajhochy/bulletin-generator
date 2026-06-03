"""
db.py — Database connection helper for bulletin-generator (server mode only).

Provides:
  get_connection()      — open a psycopg3 connection from DATABASE_URL
  transaction(claims)   — context manager; with claims, runs as the RLS
                          `authenticated` role with request.jwt.claims set so
                          auth.uid()/auth.jwt() resolve (Supabase RLS, D2)
  admin_transaction()   — service_role/owner connection that BYPASSES RLS;
                          seed/migration only, never from a request handler
  health_check()        — returns {"connected": bool, "error": str|None}
  to_jsonb(obj)         — Python object → JSON string suitable for JSONB columns
  from_jsonb(s)         — JSON string / psycopg3 Jsonb → Python object

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
    # prepare_threshold=None disables psycopg3 server-side prepared statements.
    # The Supabase session pooler (5432) can hand the same backend to different
    # logical sessions; a lingering prepared statement then triggers
    # "prepared statement already exists". Disabling them avoids that edge case.
    return psycopg.connect(url, prepare_threshold=None)


@contextmanager
def transaction(claims=None):
    """
    Context manager that yields an open psycopg3 connection.

    When ``claims`` is provided (a dict of Supabase JWT claims, at minimum
    ``{"sub": "<user_uuid>"}``), the transaction first runs::

        SET LOCAL role authenticated
        SELECT set_config('request.jwt.claims', '<json>', true)

    so Postgres RLS policies see ``auth.uid()`` / ``auth.jwt()`` for that user
    (decision D2). The full claims dict passes through so ``auth.jwt()``-based
    policies keep working. When ``claims`` is None the connection behaves as a
    plain transaction (used by existing callers in auth.py / storage.py and by
    health_check) and runs as whatever role DATABASE_URL authenticates as.

    On normal exit:   commits the transaction.
    On any exception: rolls back, then re-raises.
    The connection is always closed when the block exits.

    Usage::

        with transaction({"sub": user_id}) as conn:   # RLS-scoped to the user
            conn.execute("INSERT INTO ...")
        with transaction() as conn:                    # plain transaction
            conn.execute("SELECT 1")
    """
    conn = get_connection()
    try:
        if claims is not None:
            # Role name cannot be parameterized; the value is a fixed literal.
            conn.execute("SET LOCAL role authenticated")
            conn.execute(
                "SELECT set_config('request.jwt.claims', %s, true)",
                (json.dumps(claims),),
            )
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _admin_url() -> str:
    """
    Connection string for the RLS-bypassing admin path.

    Prefers SUPABASE_SERVICE_ROLE_URL (a service_role connection string); falls
    back to DATABASE_URL, which on this project authenticates as the database
    owner and therefore also bypasses RLS. Server-side only — never bundle the
    service_role string into the Electron app or log it.
    """
    url = os.environ.get("SUPABASE_SERVICE_ROLE_URL", "").strip()
    if url:
        return url
    return os.environ.get("DATABASE_URL", "").strip()


@contextmanager
def admin_transaction():
    """
    Context manager yielding a connection that BYPASSES row-level security.

    No JWT claims and no ``SET LOCAL role authenticated`` are issued, so the
    connection acts as service_role / the DB owner and sees every row. Use ONLY
    from seed / migration / admin tooling — never from a request handler in
    server.py, or you defeat tenant isolation.

    Commit/rollback/close semantics match ``transaction()``.
    """
    _require_server_mode()

    url = _admin_url()
    if not url:
        raise RuntimeError(
            "No admin connection string: set SUPABASE_SERVICE_ROLE_URL "
            "(preferred) or DATABASE_URL."
        )

    import psycopg  # noqa: PLC0415  (deferred so desktop import stays clean)
    conn = psycopg.connect(url, prepare_threshold=None)
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
