"""test_transfer_owner_rpc.py — contract tests for issue #277-B.

Verifies the ``public.transfer_project_owner`` SECURITY DEFINER RPC
(migration ``supabase/migrations/20260606000001_transfer_owner_rpc.sql``):

  * the current owner can transfer ownership to a workspace member;
  * a non-owner caller is rejected;
  * a target who is not a workspace member is rejected;
  * an unknown project id is rejected.

Self-contained + non-destructive: each test opens one transactional connection,
applies the migration SQL, seeds a workspace + members + a project, exercises the
RPC as the ``authenticated`` role (so ``auth.uid()`` resolves to the caller), and
ROLLS BACK on teardown. Nothing persists to the shared project, so the test
proves the migration SQL + RPC logic without performing a live deploy. (The live
``supabase db push`` of this migration is a separate, human-authorized step.)

Run: DATABASE_URL=<session_pooler> APP_MODE=server \
        pytest tests/test_transfer_owner_rpc.py -m integration -v
"""

import json
import os
import pathlib
import uuid

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="DATABASE_URL not set; transfer RPC test requires a live Supabase project",
    ),
]

_MIGRATION = (
    pathlib.Path(__file__).resolve().parent.parent
    / "supabase"
    / "migrations"
    / "20260606000001_transfer_owner_rpc.sql"
)


def _claims(user_id):
    return json.dumps({"sub": str(user_id), "role": "authenticated"})


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


def _setup(cur):
    """Apply the migration + seed owner A, member B, a stranger, ws, project.

    Returns (a_id, b_id, stranger_id, ws_id, project_id).
    """
    cur.execute(_MIGRATION.read_text(encoding="utf-8"))

    tag = uuid.uuid4().hex
    a = _seed_user(cur, f"rpc_a_{tag}@test.invalid")
    b = _seed_user(cur, f"rpc_b_{tag}@test.invalid")
    stranger = _seed_user(cur, f"rpc_s_{tag}@test.invalid")

    cur.execute(
        "insert into public.workspaces (id, name) values (gen_random_uuid(), %s) returning id",
        [f"rpc_ws_{tag}"],
    )
    ws = cur.fetchone()[0]
    cur.execute(
        "insert into public.workspace_members (workspace_id, user_id, role) values (%s, %s, 'owner')",
        [ws, a],
    )
    cur.execute(
        "insert into public.workspace_members (workspace_id, user_id, role) values (%s, %s, 'editor')",
        [ws, b],
    )
    proj = f"proj_rpc_{tag}"
    cur.execute(
        "insert into public.projects (id, workspace_id, name, owner_user_id) values (%s, %s, 'rpc seed', %s)",
        [proj, ws, a],
    )
    return a, b, stranger, ws, proj


def _act_as(cur, user_id):
    cur.execute("set local role authenticated")
    cur.execute("select set_config('request.jwt.claims', %s, true)", [_claims(user_id)])


@pytest.fixture
def conn():
    import psycopg  # deferred so module import is clean when skipped

    c = psycopg.connect(DATABASE_URL)  # transactional (not autocommit)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


class TestTransferOwnerRpc:
    def test_issue_277_b_c1_owner_can_transfer_to_member(self, conn):
        """issue-277-B-c1: the current owner transfers to a workspace member; the
        RPC returns the new owner id and projects.owner_user_id is updated."""
        with conn.cursor() as cur:
            a, b, _stranger, _ws, proj = _setup(cur)
            _act_as(cur, a)
            cur.execute("select public.transfer_project_owner(%s, %s)", [proj, b])
            returned = cur.fetchone()[0]
            assert str(returned) == str(b)

            cur.execute("reset role")
            cur.execute("select owner_user_id from public.projects where id = %s", [proj])
            assert str(cur.fetchone()[0]) == str(b)

    def test_issue_277_b_c2_non_owner_rejected(self, conn):
        """issue-277-B-c2: a non-owner caller (member B) cannot transfer."""
        import psycopg

        with conn.cursor() as cur:
            _a, b, _stranger, _ws, proj = _setup(cur)
            _act_as(cur, b)  # B is a member, not the owner
            with pytest.raises(psycopg.Error, match="not the project owner"):
                cur.execute("select public.transfer_project_owner(%s, %s)", [proj, b])

    def test_issue_277_b_c3_non_member_target_rejected(self, conn):
        """issue-277-B-c3: transfer to a user who is not a workspace member fails."""
        import psycopg

        with conn.cursor() as cur:
            a, _b, stranger, _ws, proj = _setup(cur)
            _act_as(cur, a)
            with pytest.raises(psycopg.Error, match="not a workspace member"):
                cur.execute("select public.transfer_project_owner(%s, %s)", [proj, stranger])

    def test_issue_277_b_c4_unknown_project_rejected(self, conn):
        """issue-277-B-c4: an unknown project id is rejected."""
        import psycopg

        with conn.cursor() as cur:
            a, b, _stranger, _ws, _proj = _setup(cur)
            _act_as(cur, a)
            with pytest.raises(psycopg.Error, match="project not found"):
                cur.execute(
                    "select public.transfer_project_owner(%s, %s)",
                    ["proj_does_not_exist", b],
                )
