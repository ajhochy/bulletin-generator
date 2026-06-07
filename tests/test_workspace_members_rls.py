"""test_workspace_members_rls.py — contract tests for issue #277-G.

`_handle_get_workspace_members` now reads via the caller's JWT (RLS-scoped
`db.transaction(claims)`) instead of the owner-role `admin_transaction()`.
These tests prove the exact handler query, run as the authenticated caller,
(a) returns the caller's workspace members (excluding the caller) and
(b) returns ZERO rows for a workspace the caller does not belong to — i.e. the
RLS `workspace_members_select` policy enforces isolation without the
RLS-bypassing connection.

Self-contained + non-destructive: seeds on the owner connection, asserts as the
authenticated role, rolls back. Run:
    DATABASE_URL=<pooler> APP_MODE=server pytest tests/test_workspace_members_rls.py -m integration -v
"""

import json
import os
import uuid

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="DATABASE_URL not set; members RLS test requires a live Supabase project",
    ),
]

# The exact query from server.py::_handle_get_workspace_members.
_MEMBERS_QUERY = """
    SELECT wm.user_id, wm.role, p.display_name, p.email
    FROM public.workspace_members wm
    LEFT JOIN public.profiles p ON p.id = wm.user_id
    WHERE wm.workspace_id = %(workspace_id)s::uuid
      AND wm.user_id != %(caller_id)s::uuid
    ORDER BY p.display_name NULLS LAST, p.email
"""


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


def _seed_ws(cur, name, owner_id):
    cur.execute(
        "insert into public.workspaces (id, name) values (gen_random_uuid(), %s) returning id",
        [name],
    )
    ws = cur.fetchone()[0]
    cur.execute(
        "insert into public.workspace_members (workspace_id, user_id, role) values (%s, %s, 'owner')",
        [ws, owner_id],
    )
    return ws


@pytest.fixture
def conn():
    import psycopg

    c = psycopg.connect(DATABASE_URL)  # transactional
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def _setup(cur):
    tag = uuid.uuid4().hex
    a = _seed_user(cur, f"wm_a_{tag}@test.invalid")   # owner of ws_a
    b = _seed_user(cur, f"wm_b_{tag}@test.invalid")   # member of ws_a
    c = _seed_user(cur, f"wm_c_{tag}@test.invalid")   # owner of ws_c (other)
    ws_a = _seed_ws(cur, f"wm_ws_a_{tag}", a)
    cur.execute(
        "insert into public.workspace_members (workspace_id, user_id, role) values (%s, %s, 'editor')",
        [ws_a, b],
    )
    ws_c = _seed_ws(cur, f"wm_ws_c_{tag}", c)
    return a, b, c, ws_a, ws_c


def _act_as(cur, user_id):
    cur.execute("set local role authenticated")
    cur.execute("select set_config('request.jwt.claims', %s, true)", [_claims(user_id)])


class TestWorkspaceMembersRls:
    def test_issue_277_g_c1_caller_sees_own_workspace_members(self, conn):
        """issue-277-G-c1: under the caller's JWT, the members query returns the
        other member of the caller's workspace (excluding the caller)."""
        with conn.cursor() as cur:
            a, b, _c, ws_a, _ws_c = _setup(cur)
            _act_as(cur, a)
            cur.execute(_MEMBERS_QUERY, {"workspace_id": ws_a, "caller_id": a})
            ids = {str(r[0]) for r in cur.fetchall()}
            assert str(b) in ids, "caller must see the other workspace member"
            assert str(a) not in ids, "caller must be excluded from the list"

    def test_issue_277_g_c2_caller_cannot_list_other_workspace_members(self, conn):
        """issue-277-G-c2: under the caller's JWT, querying a workspace the caller
        does NOT belong to returns ZERO rows (RLS workspace_members_select)."""
        with conn.cursor() as cur:
            a, _b, _c, _ws_a, ws_c = _setup(cur)
            _act_as(cur, a)  # user_a is NOT a member of ws_c
            cur.execute(_MEMBERS_QUERY, {"workspace_id": ws_c, "caller_id": a})
            rows = cur.fetchall()
            assert rows == [], "caller must not list members of a foreign workspace"
