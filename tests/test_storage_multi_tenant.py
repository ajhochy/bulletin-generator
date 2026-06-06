"""
tests/test_storage_multi_tenant.py — Multi-tenant storage tests (issue 004 / #260).

Verifies that PostgresStorageBackend correctly scopes reads/writes to the
supplied workspace_id and passes user_claims to db.transaction() so RLS
sees auth.uid().

Tests that require a live database are skipped when DATABASE_URL is absent
(CI-safe, matches the pattern in test_rls_isolation.py and test_db.py).

Two required tests per the issue spec:
  - test_get_project_wrong_workspace_returns_none
  - test_save_project_scoped_to_workspace

Plus additional constructor / backward-compat tests that run without a DB.
"""

import json
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage import PostgresStorageBackend

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

_DB_SKIP = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set; multi-tenant DB tests require a live Supabase project",
)

TEST_TAG = "mt_storage_test"


# ---------------------------------------------------------------------------
# Backward-compatibility / constructor tests (no DB required)
# ---------------------------------------------------------------------------

class TestPostgresStorageBackendConstructor:
    """PostgresStorageBackend() must be constructable with zero args."""

    def test_no_args_creates_instance(self):
        pg = PostgresStorageBackend()
        assert isinstance(pg, PostgresStorageBackend)

    def test_no_args_workspace_id_is_none(self):
        pg = PostgresStorageBackend()
        assert pg.workspace_id is None

    def test_no_args_user_claims_is_none(self):
        pg = PostgresStorageBackend()
        assert pg.user_claims is None

    def test_workspace_id_stored(self):
        ws_id = str(uuid.uuid4())
        pg = PostgresStorageBackend(workspace_id=ws_id)
        assert pg.workspace_id == ws_id

    def test_user_claims_stored(self):
        claims = {"sub": str(uuid.uuid4()), "role": "authenticated"}
        pg = PostgresStorageBackend(user_claims=claims)
        assert pg.user_claims == claims

    def test_both_args_stored(self):
        ws_id = str(uuid.uuid4())
        claims = {"sub": str(uuid.uuid4())}
        pg = PostgresStorageBackend(workspace_id=ws_id, user_claims=claims)
        assert pg.workspace_id == ws_id
        assert pg.user_claims == claims

    def test_transaction_passes_none_claims(self, monkeypatch):
        """When user_claims is None, _transaction() calls transaction(claims=None)."""
        captured = {}

        @contextmanager
        def fake_transaction(claims=None):
            captured["claims"] = claims
            yield MagicMock()

        pg = PostgresStorageBackend()
        monkeypatch.setattr("db.transaction", fake_transaction)
        # _transaction() is a context manager; enter it
        with pg._transaction() as _conn:
            pass
        assert captured["claims"] is None

    def test_transaction_passes_user_claims(self, monkeypatch):
        """When user_claims is set, _transaction() calls transaction(claims=user_claims)."""
        captured = {}
        claims = {"sub": str(uuid.uuid4()), "role": "authenticated"}

        @contextmanager
        def fake_transaction(claims=None):
            captured["claims"] = claims
            yield MagicMock()

        pg = PostgresStorageBackend(user_claims=claims)
        monkeypatch.setattr("db.transaction", fake_transaction)
        with pg._transaction() as _conn:
            pass
        assert captured["claims"] == claims


# ---------------------------------------------------------------------------
# Seeding helpers (owner-level connection, autocommit, bypass RLS)
# ---------------------------------------------------------------------------

@contextmanager
def _service_conn():
    """Owner connection (bypasses RLS) for seed + teardown. Autocommit."""
    import psycopg

    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def _cleanup(cur, emails, ws_names):
    cur.execute("DELETE FROM public.workspaces WHERE name = ANY(%s)", [list(ws_names)])
    cur.execute("DELETE FROM auth.users WHERE email = ANY(%s)", [list(emails)])


def _seed_user(cur, email):
    cur.execute(
        """
        INSERT INTO auth.users (instance_id, id, aud, role, email)
        VALUES ('00000000-0000-0000-0000-000000000000',
                gen_random_uuid(), 'authenticated', 'authenticated', %s)
        RETURNING id
        """,
        [email],
    )
    return cur.fetchone()[0]


def _seed_workspace(cur, name, user_id):
    cur.execute(
        "INSERT INTO public.workspaces (id, name) VALUES (gen_random_uuid(), %s) RETURNING id",
        [name],
    )
    ws_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO public.workspace_members (workspace_id, user_id, role) VALUES (%s, %s, 'owner')",
        [ws_id, user_id],
    )
    return ws_id


def _seed_project(cur, ws_id, user_id):
    proj_id = f"{TEST_TAG}_{uuid.uuid4().hex}"
    cur.execute(
        """
        INSERT INTO public.projects (id, workspace_id, name, owner_user_id, state)
        VALUES (%s, %s, 'test-project', %s, '{}')
        """,
        [proj_id, ws_id, user_id],
    )
    return proj_id


def _user_claims(user_id):
    return {"sub": str(user_id), "role": "authenticated"}


# ---------------------------------------------------------------------------
# Live DB tests
# ---------------------------------------------------------------------------

@_DB_SKIP
class TestGetProjectWrongWorkspace:
    """test_get_project_wrong_workspace_returns_none (required by spec)."""

    @pytest.fixture(autouse=True)
    def seed(self):
        email_a = f"{TEST_TAG}_a@example.test"
        email_b = f"{TEST_TAG}_b@example.test"
        ws_name_a = f"{TEST_TAG}_ws_a"
        ws_name_b = f"{TEST_TAG}_ws_b"

        with _service_conn() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, [email_a, email_b], [ws_name_a, ws_name_b])
                user_a = _seed_user(cur, email_a)
                user_b = _seed_user(cur, email_b)
                ws_a = _seed_workspace(cur, ws_name_a, user_a)
                ws_b = _seed_workspace(cur, ws_name_b, user_b)
                proj_a = _seed_project(cur, ws_a, user_a)

        self.__class__._ctx = dict(
            user_a=user_a, user_b=user_b,
            ws_a=ws_a, ws_b=ws_b,
            proj_a=proj_a,
        )
        yield
        with _service_conn() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, [email_a, email_b], [ws_name_a, ws_name_b])

    @property
    def ctx(self):
        return self.__class__._ctx

    def test_get_project_wrong_workspace_returns_none(self):
        """get_project must return None when scoped to a workspace that doesn't own
        the project (RLS returns 0 rows; do not leak found-vs-forbidden).
        """
        c = self.ctx
        # Workspace B's storage backend tries to read workspace A's project.
        backend_b = PostgresStorageBackend(
            workspace_id=str(c["ws_b"]),
            user_claims=_user_claims(c["user_b"]),
        )
        result = backend_b.get_project(c["proj_a"])
        assert result is None, (
            f"get_project should return None for a project in a different workspace, "
            f"got: {result}"
        )

    def test_get_project_own_workspace_returns_project(self):
        """get_project must return the project dict when scoped to the owning workspace."""
        c = self.ctx
        backend_a = PostgresStorageBackend(
            workspace_id=str(c["ws_a"]),
            user_claims=_user_claims(c["user_a"]),
        )
        result = backend_a.get_project(c["proj_a"])
        assert result is not None, "get_project should return the project for the owning workspace"
        assert result["id"] == c["proj_a"]


@_DB_SKIP
class TestSaveProjectScopedToWorkspace:
    """test_save_project_scoped_to_workspace (required by spec)."""

    @pytest.fixture(autouse=True)
    def seed(self):
        email_a = f"{TEST_TAG}_sp_a@example.test"
        ws_name_a = f"{TEST_TAG}_sp_ws_a"

        with _service_conn() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, [email_a], [ws_name_a])
                user_a = _seed_user(cur, email_a)
                ws_a = _seed_workspace(cur, ws_name_a, user_a)

        self.__class__._ctx = dict(user_a=user_a, ws_a=ws_a)
        yield
        with _service_conn() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, [email_a], [ws_name_a])

    @property
    def ctx(self):
        return self.__class__._ctx

    def test_save_project_scoped_to_workspace(self):
        """save_project must insert a project scoped to self.workspace_id."""
        c = self.ctx
        ws_id = str(c["ws_a"])
        user_id = str(c["user_a"])
        proj_id = f"{TEST_TAG}_save_{uuid.uuid4().hex}"

        backend = PostgresStorageBackend(
            workspace_id=ws_id,
            user_claims=_user_claims(c["user_a"]),
        )
        result = backend.save_project(
            {"id": proj_id, "name": "Multi-tenant Save Test"},
            updated_by_user_id=user_id,
        )
        assert result is not None
        assert result["id"] == proj_id
        assert result["name"] == "Multi-tenant Save Test"

        # Read it back from the same workspace — should be visible.
        fetched = backend.get_project(proj_id)
        assert fetched is not None
        assert fetched["id"] == proj_id

    def test_save_project_cross_workspace_not_visible(self):
        """A project saved in workspace A must not be readable from workspace B."""
        c = self.ctx

        # Seed a second workspace.
        email_b = f"{TEST_TAG}_sp_b@example.test"
        ws_name_b = f"{TEST_TAG}_sp_ws_b"
        with _service_conn() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, [email_b], [ws_name_b])
                user_b = _seed_user(cur, email_b)
                ws_b = _seed_workspace(cur, ws_name_b, user_b)

        try:
            ws_id_a = str(c["ws_a"])
            user_id_a = str(c["user_a"])
            proj_id = f"{TEST_TAG}_cross_{uuid.uuid4().hex}"

            backend_a = PostgresStorageBackend(
                workspace_id=ws_id_a,
                user_claims=_user_claims(c["user_a"]),
            )
            backend_a.save_project(
                {"id": proj_id, "name": "Workspace A Project"},
                updated_by_user_id=user_id_a,
            )

            backend_b = PostgresStorageBackend(
                workspace_id=str(ws_b),
                user_claims=_user_claims(user_b),
            )
            result = backend_b.get_project(proj_id)
            assert result is None, (
                "Project saved in workspace A must not be readable from workspace B"
            )
        finally:
            with _service_conn() as conn:
                with conn.cursor() as cur:
                    _cleanup(cur, [email_b], [ws_name_b])
