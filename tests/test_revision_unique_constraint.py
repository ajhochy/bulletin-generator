"""test_revision_unique_constraint.py — contract test for issue #216 (uniqueness).

Proves the project_revisions unique index
(migration 20260606000002_project_revisions_unique_revision.sql) rejects a
duplicate (project_id, revision_number) — i.e. "revision numbers are unique per
project" is enforced at the DB level, not just by application logic.

Self-contained + non-destructive: applies the migration in a transaction, seeds
a workspace + project + one revision, attempts a duplicate revision insert
(expects a unique violation), and ROLLS BACK. No persisted change. The live
`supabase db push` of this migration is a separate human-authorized step.

Run: DATABASE_URL=<pooler> APP_MODE=server pytest tests/test_revision_unique_constraint.py -m integration -v
"""

import os
import pathlib
import uuid

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="DATABASE_URL not set; unique-constraint test requires a live Supabase project",
    ),
]

_MIGRATION = (
    pathlib.Path(__file__).resolve().parent.parent
    / "supabase"
    / "migrations"
    / "20260606000002_project_revisions_unique_revision.sql"
)


@pytest.fixture
def conn():
    import psycopg

    c = psycopg.connect(DATABASE_URL)  # transactional
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def test_issue_216_c5_duplicate_revision_rejected(conn):
    """issue-216-c5: a second project_revisions row with the same
    (project_id, revision_number) raises a unique violation."""
    import psycopg

    with conn.cursor() as cur:
        cur.execute(_MIGRATION.read_text(encoding="utf-8"))

        tag = uuid.uuid4().hex
        cur.execute(
            """
            insert into auth.users (instance_id, id, aud, role, email)
            values ('00000000-0000-0000-0000-000000000000',
                    gen_random_uuid(), 'authenticated', 'authenticated', %s)
            returning id
            """,
            [f"rev_uniq_{tag}@test.invalid"],
        )
        user_id = cur.fetchone()[0]
        cur.execute(
            "insert into public.workspaces (id, name) values (gen_random_uuid(), %s) returning id",
            [f"rev_uniq_ws_{tag}"],
        )
        ws = cur.fetchone()[0]
        cur.execute(
            "insert into public.workspace_members (workspace_id, user_id, role) values (%s, %s, 'owner')",
            [ws, user_id],
        )
        proj = f"proj_revuniq_{tag}"
        cur.execute(
            "insert into public.projects (id, workspace_id, name, owner_user_id) values (%s, %s, 'seed', %s)",
            [proj, ws, user_id],
        )

        def _insert_rev(rev):
            cur.execute(
                """
                insert into public.project_revisions
                    (id, project_id, workspace_id, revision_number, state, created_by_user_id)
                values (gen_random_uuid(), %s, %s, %s, '{}'::jsonb, %s)
                """,
                [proj, ws, rev, user_id],
            )

        _insert_rev(1)  # first revision 1 — ok
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_rev(1)  # duplicate revision 1 — must be rejected
