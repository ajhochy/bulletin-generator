"""
test_rls_isolation.py — automated cross-tenant RLS isolation suite (issue 002 / #258).

Security-critical: workspace A must never read or write workspace B's data.

Mechanism (mirrors server.py's D2 plan and the tenancy-foundation verification):
  * Seed/teardown run on the owner (`postgres`) connection, which bypasses RLS.
  * Every isolation assertion runs as the `authenticated` role with
    `set local role authenticated` + a `request.jwt.claims` GUC carrying the
    user's uuid in `sub`, so `auth.uid()` resolves to that user and RLS applies.

Run against the staging Supabase project:
    DATABASE_URL=<session_pooler_url> APP_MODE=server pytest tests/test_rls_isolation.py -v

Without DATABASE_URL the whole module is skipped (matches
tests/test_migrations.py::TestIntegration), so CI without a DB stays green.

service_role / superuser credentials are read from the environment only —
never committed.
"""

import json
import os
import uuid
from contextlib import contextmanager

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set; RLS isolation tests require a live Supabase project",
)

# Unique per-test-data marker so seed rows are recognizable and cleanup is total,
# even if a previous run crashed before teardown.
TEST_TAG = "rls_iso_test"

# Tables that follow the workspace-member CRUD pattern (issue 001 + projects).
WORKSPACE_TABLES = [
    "projects",
    "project_revisions",
    "workspace_settings",
    "announcements",
    "songs",
    "templates",
    "fonts",
]


def _claims(user_id):
    return json.dumps({"sub": str(user_id), "role": "authenticated"})


@contextmanager
def _service_conn():
    """Owner connection (bypasses RLS) for seed + teardown. Autocommit."""
    import psycopg  # deferred so module import is clean when skipped

    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def _as_user(user_id):
    """
    Yield a connection acting as `authenticated` user `user_id`.

    Stays inside a single transaction (so SET LOCAL applies) and always rolls
    back on exit — isolation-test writes must never persist.
    """
    import psycopg

    conn = psycopg.connect(DATABASE_URL)  # not autocommit -> transactional
    try:
        with conn.cursor() as cur:
            cur.execute("set local role authenticated")
            cur.execute(
                "select set_config('request.jwt.claims', %s, true)", [_claims(user_id)]
            )
        yield conn
    finally:
        conn.rollback()
        conn.close()


# ── seed / teardown helpers (run as owner) ────────────────────────────────────

def _cleanup(cur, emails, ws_names):
    """Remove any test workspaces/users (cascades to all child data tables)."""
    cur.execute(
        "delete from public.workspaces where name = any(%s)", [list(ws_names)]
    )
    cur.execute("delete from auth.users where email = any(%s)", [list(emails)])


def _seed_user(cur, email):
    cur.execute(
        """
        insert into auth.users (instance_id, id, aud, role, email)
        values ('00000000-0000-0000-0000-000000000000',
                gen_random_uuid(), 'authenticated', 'authenticated', %s)
        returning id
        """,
        [email],
    )
    return cur.fetchone()[0]


def _seed_workspace(cur, name, user_id):
    cur.execute(
        "insert into public.workspaces (id, name) values (gen_random_uuid(), %s) returning id",
        [name],
    )
    ws_id = cur.fetchone()[0]
    cur.execute(
        "insert into public.workspace_members (workspace_id, user_id, role) values (%s, %s, 'owner')",
        [ws_id, user_id],
    )
    return ws_id


def _seed_tables(cur, ws_id, user_id):
    """Insert exactly one row per workspace table; return the project id."""
    proj_id = f"{TEST_TAG}_{uuid.uuid4().hex}"
    cur.execute(
        "insert into public.projects (id, workspace_id, name, owner_user_id) values (%s, %s, 'seed', %s)",
        [proj_id, ws_id, user_id],
    )
    cur.execute(
        """insert into public.project_revisions
           (project_id, workspace_id, revision_number, state, created_by_user_id)
           values (%s, %s, 1, '{}', %s)""",
        [proj_id, ws_id, user_id],
    )
    cur.execute(
        "insert into public.workspace_settings (workspace_id, settings) values (%s, '{}')",
        [ws_id],
    )
    cur.execute(
        "insert into public.announcements (workspace_id, title, created_by_user_id) values (%s, 'seed', %s)",
        [ws_id, user_id],
    )
    cur.execute("insert into public.songs (workspace_id, title) values (%s, 'seed')", [ws_id])
    cur.execute("insert into public.templates (workspace_id, name) values (%s, 'seed')", [ws_id])
    cur.execute("insert into public.fonts (workspace_id, name) values (%s, 'seed')", [ws_id])
    return proj_id


# A cross-tenant INSERT attempt per table: shape is valid but workspace_id (and
# membership) belong to the *other* tenant, so RLS WITH CHECK must reject it.
def _cross_insert(cur, table, ws_other, user_self, proj_other):
    new_id = f"{TEST_TAG}_cross_{uuid.uuid4().hex}"
    if table == "projects":
        cur.execute(
            "insert into public.projects (id, workspace_id, name, owner_user_id) values (%s, %s, 'x', %s)",
            [new_id, ws_other, user_self],
        )
    elif table == "project_revisions":
        cur.execute(
            """insert into public.project_revisions
               (project_id, workspace_id, revision_number, state, created_by_user_id)
               values (%s, %s, 99, '{}', %s)""",
            [proj_other, ws_other, user_self],
        )
    elif table == "workspace_settings":
        cur.execute(
            "insert into public.workspace_settings (workspace_id, settings) values (%s, '{}')",
            [ws_other],
        )
    elif table == "announcements":
        cur.execute(
            "insert into public.announcements (workspace_id, title, created_by_user_id) values (%s, 'x', %s)",
            [ws_other, user_self],
        )
    elif table == "songs":
        cur.execute("insert into public.songs (workspace_id, title) values (%s, 'x')", [ws_other])
    elif table == "templates":
        cur.execute("insert into public.templates (workspace_id, name) values (%s, 'x')", [ws_other])
    elif table == "fonts":
        cur.execute("insert into public.fonts (workspace_id, name) values (%s, 'x')", [ws_other])
    else:  # pragma: no cover - guard against typos in WORKSPACE_TABLES
        raise AssertionError(f"unhandled table {table}")


class TestRLSIsolation:
    """Cross-tenant read/write isolation across all multi-tenant data tables."""

    @pytest.fixture(scope="class", autouse=True)
    def seed(self):
        import psycopg

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
                proj_a = _seed_tables(cur, ws_a, user_a)
                proj_b = _seed_tables(cur, ws_b, user_b)
                # per-user settings: one row each
                cur.execute(
                    "insert into public.user_settings (user_id, workspace_id, settings) values (%s, %s, '{}')",
                    [user_a, ws_a],
                )
                cur.execute(
                    "insert into public.user_settings (user_id, workspace_id, settings) values (%s, %s, '{}')",
                    [user_b, ws_b],
                )

        self.__class__._ctx = dict(
            user_a=user_a, user_b=user_b, ws_a=ws_a, ws_b=ws_b,
            proj_a=proj_a, proj_b=proj_b,
        )
        yield
        # teardown: total removal (cascades child rows)
        with _service_conn() as conn:
            with conn.cursor() as cur:
                _cleanup(cur, [email_a, email_b], [ws_name_a, ws_name_b])

        # psycopg imported above keeps linters from flagging the deferred import
        _ = psycopg

    @property
    def ctx(self):
        return self.__class__._ctx

    # ── within-workspace SELECT must see the seeded row ──────────────────────
    @pytest.mark.parametrize("table", WORKSPACE_TABLES)
    def test_within_workspace_select_visible(self, table):
        c = self.ctx
        with _as_user(c["user_a"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"select count(*) from public.{table} where workspace_id = %s", [c["ws_a"]]
                )
                assert cur.fetchone()[0] >= 1, f"user_a should see own {table} rows"

    # ── cross-tenant SELECT must return zero rows (silent RLS filter) ────────
    @pytest.mark.parametrize("table", WORKSPACE_TABLES)
    def test_cross_tenant_select_blocked(self, table):
        c = self.ctx
        with _as_user(c["user_a"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"select count(*) from public.{table} where workspace_id = %s", [c["ws_b"]]
                )
                assert cur.fetchone()[0] == 0, f"user_a must not read workspace_b {table}"
        # and the reverse direction
        with _as_user(c["user_b"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"select count(*) from public.{table} where workspace_id = %s", [c["ws_a"]]
                )
                assert cur.fetchone()[0] == 0, f"user_b must not read workspace_a {table}"

    # ── cross-tenant INSERT must be rejected by WITH CHECK ───────────────────
    @pytest.mark.parametrize("table", WORKSPACE_TABLES)
    def test_cross_tenant_insert_blocked(self, table):
        import psycopg

        c = self.ctx
        with _as_user(c["user_a"]) as conn:
            with conn.cursor() as cur:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    _cross_insert(cur, table, c["ws_b"], c["user_a"], c["proj_b"])

    # ── user_settings: per-user isolation, not workspace membership ──────────
    def test_user_settings_per_user_isolation(self):
        c = self.ctx
        with _as_user(c["user_a"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from public.user_settings where user_id = %s", [c["user_b"]]
                )
                assert cur.fetchone()[0] == 0, "user_a must not read user_b's settings"
                cur.execute(
                    "select count(*) from public.user_settings where user_id = %s", [c["user_a"]]
                )
                assert cur.fetchone()[0] == 1, "user_a should read own settings"

    # ── project_revisions: cross-tenant revisions invisible ──────────────────
    def test_project_revisions_cross_tenant_blocked(self):
        c = self.ctx
        with _as_user(c["user_a"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from public.project_revisions where project_id = %s",
                    [c["proj_b"]],
                )
                assert cur.fetchone()[0] == 0, "user_a must not read workspace_b project revisions"
                cur.execute(
                    "select count(*) from public.project_revisions where project_id = %s",
                    [c["proj_a"]],
                )
                assert cur.fetchone()[0] == 1, "user_a should read own project revisions"
