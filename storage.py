"""
storage.py — Storage abstraction boundary.

Routes call these methods; the implementation routes to JSON files (desktop)
or Postgres (server mode).  This module never imports server.py directly —
it re-implements the minimal read/write helpers it needs.

Usage:
    from storage import get_storage
    store = get_storage()
    projects = store.list_projects()
"""

from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Minimal JSON helpers (mirrors server._read_json / _write_json)
# ---------------------------------------------------------------------------

def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    """Atomic write: write to .tmp then rename."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Base class / protocol
# ---------------------------------------------------------------------------

class StorageBackend(ABC):
    """Abstract storage interface.  All route handlers talk to this interface;
    the concrete implementation (JSON or Postgres) is chosen at startup."""

    # ── Projects ──────────────────────────────────────────────────────────────

    @abstractmethod
    def list_projects(self, user_id: str | None = None) -> list:
        """Return the full list of project dicts.

        When *user_id* is supplied (normal server-mode operation) only projects
        visible to that user are returned.  When None, all projects are returned
        (admin/migration use only).
        """
        ...

    @abstractmethod
    def get_project(self, project_id: str) -> dict | None:
        """Return a single project dict by id, or None if not found."""
        ...

    @abstractmethod
    def save_project(self, data: dict, *, updated_by_email: str = "", updated_by_user_id: str | None = None) -> dict:
        """Upsert a project.  ``data`` must contain an ``id`` key.  Returns the saved project.

        ``updated_by_email`` and ``updated_by_user_id`` are optional attribution kwargs.
        When supplied (server mode), the backend records who performed the save.
        """
        ...

    def save_project_transactional(
        self,
        data: dict,
        client_revision: int | None,
        *,
        updated_by_email: str = "",
        updated_by_user_id: str | None = None,
        updated_by_name: str = "",
    ) -> dict:
        """Save a project only when *client_revision* matches the stored revision.

        This is the conflict-safe write path for server mode.  The default
        implementation falls back to ``save_project()`` (used by the JSON
        backend where single-writer semantics are guaranteed by the file lock).

        Raises:
            ConflictError: when the stored revision does not match *client_revision*.
                           ``ConflictError.project`` holds the current server-side
                           project dict so callers can build a 409 response.
        """
        return self.save_project(
            data,
            updated_by_email=updated_by_email,
            updated_by_user_id=updated_by_user_id,
        )

    @abstractmethod
    def delete_project(self, project_id: str) -> bool:
        """Delete a project by id.  Returns True if it existed."""
        ...

    @abstractmethod
    def share_project_to_workspace(self, project_id: str) -> "dict | None":
        """Set visibility='workspace' on the project and return the updated dict.

        Returns the updated project dict, or None if the project was not found.
        """
        ...

    # ── Settings ──────────────────────────────────────────────────────────────

    @abstractmethod
    def get_settings(self) -> dict:
        """Return the settings dict."""
        ...

    @abstractmethod
    def save_settings(self, data: dict) -> dict:
        """Persist the settings dict.  Returns the saved settings."""
        ...

    # ── Announcements ─────────────────────────────────────────────────────────

    @abstractmethod
    def list_announcements(self) -> list:
        """Return the full list of announcement dicts."""
        ...

    @abstractmethod
    def save_announcements(self, data: list) -> list:
        """Persist the full announcements list.  Returns the saved list."""
        ...

    # ── Songs ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def list_songs(self) -> list:
        """Return the full song-database list."""
        ...

    @abstractmethod
    def save_songs(self, data: list) -> list:
        """Persist the full song-database list.  Returns the saved list."""
        ...

    # ── Templates ─────────────────────────────────────────────────────────────

    @abstractmethod
    def list_templates(self) -> list:
        """Return user-defined (non-built-in) template dicts."""
        ...

    @abstractmethod
    def save_templates(self, data: list) -> list:
        """Persist the full templates list.  Returns the saved list."""
        ...

    # ── Fonts ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def list_fonts(self) -> list:
        """Return a list of font metadata dicts.

        Each dict contains at minimum: slug, family, source, css_url, file_path.
        In JSON mode the list is built by scanning the font directories on disk.
        In Postgres mode the list is read from the ``fonts`` table.
        """
        ...

    @abstractmethod
    def get_font(self, slug: str) -> "dict | None":
        """Return a single font metadata dict by slug, or None if not found."""
        ...

    @abstractmethod
    def save_font(
        self,
        name: str,
        filename: str,
        data: bytes,
        mime_type: str,
    ) -> dict:
        """Upload a font binary and persist its metadata.

        Returns a dict with at minimum: ``id``, ``name``, ``url``.
        In desktop mode the binary is written to the local user-fonts directory
        and ``url`` is the local CSS helper path.  In server mode the binary is
        uploaded to Supabase Storage and ``url`` is the public Storage URL.
        """
        ...

    @abstractmethod
    def delete_font(self, font_id: str) -> bool:
        """Delete a font by id.

        In desktop mode *font_id* is treated as the slug/family-dir name and
        the directory is removed.  In server mode the Storage object and the
        ``fonts`` table row are both deleted.

        Returns True if the font existed and was removed, False otherwise.
        """
        ...

    # ── Project revisions ──────────────────────────────────────────────────────

    def get_project_revisions(self, project_id: str) -> list:
        """Return revision metadata for *project_id*, newest first.

        Each dict contains: id, project_id, revision, saved_at,
        saved_by_email, saved_by_name, summary.  The ``state`` JSONB is
        intentionally excluded — use ``get_project_revision()`` to fetch a
        specific snapshot including state.

        Returns an empty list when the project has no recorded revisions or
        when the backend does not support revision history (desktop mode).
        """
        return []

    def get_project_revision(self, project_id: str, revision: int) -> "dict | None":
        """Return the full revision snapshot for *project_id* at *revision*.

        Returns a dict with all ``project_revisions`` columns including
        ``state`` (the full JSONB snapshot), or ``None`` if not found.

        The desktop/JSON backend always returns ``None`` because it does not
        record revision snapshots.
        """
        return None


# ---------------------------------------------------------------------------
# JSON implementation (desktop mode)
# ---------------------------------------------------------------------------

class JsonStorageBackend(StorageBackend):
    """Delegates all storage to JSON files in *data_dir*.

    Thread-safety: a single ``threading.Lock`` serialises all writes,
    matching the behaviour of server.py's ``_lock``.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._lock = threading.Lock()

        self._projects_file      = self._data_dir / "projects.json"
        self._announcements_file = self._data_dir / "announcements.json"
        self._settings_file      = self._data_dir / "settings.json"
        self._songs_file         = self._data_dir / "song_database.json"
        self._templates_file     = self._data_dir / "templates.json"

    # ── Projects ──────────────────────────────────────────────────────────────

    def list_projects(self, user_id: str | None = None) -> list:
        # Desktop mode has no multi-user concept; always return all projects.
        with self._lock:
            return _read_json(self._projects_file, [])

    def get_project(self, project_id: str) -> dict | None:
        with self._lock:
            projects = _read_json(self._projects_file, [])
        for p in projects:
            if isinstance(p, dict) and p.get("id") == project_id:
                return p
        return None

    def save_project(self, data: dict, *, updated_by_email: str = "", updated_by_user_id: str | None = None) -> dict:
        if "id" not in data:
            raise ValueError("project data must contain an 'id' key")
        with self._lock:
            projects = _read_json(self._projects_file, [])
            for i, p in enumerate(projects):
                if isinstance(p, dict) and p.get("id") == data["id"]:
                    projects[i] = data
                    break
            else:
                projects.append(data)
            _write_json(self._projects_file, projects)
        return data

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            projects = _read_json(self._projects_file, [])
            new_projects = [p for p in projects if not (isinstance(p, dict) and p.get("id") == project_id)]
            existed = len(new_projects) < len(projects)
            if existed:
                _write_json(self._projects_file, new_projects)
        return existed

    def share_project_to_workspace(self, project_id: str) -> "dict | None":
        """Desktop mode no-op: workspace concept does not apply.

        Returns the project dict unchanged, or None if not found.
        """
        return self.get_project(project_id)

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        with self._lock:
            return _read_json(self._settings_file, {})

    def save_settings(self, data: dict) -> dict:
        with self._lock:
            _write_json(self._settings_file, data)
        return data

    # ── Announcements ─────────────────────────────────────────────────────────

    def list_announcements(self) -> list:
        with self._lock:
            return _read_json(self._announcements_file, [])

    def save_announcements(self, data: list) -> list:
        with self._lock:
            _write_json(self._announcements_file, data)
        return data

    # ── Songs ─────────────────────────────────────────────────────────────────

    def list_songs(self) -> list:
        with self._lock:
            return _read_json(self._songs_file, [])

    def save_songs(self, data: list) -> list:
        with self._lock:
            _write_json(self._songs_file, data)
        return data

    # ── Templates ─────────────────────────────────────────────────────────────

    def list_templates(self) -> list:
        with self._lock:
            return _read_json(self._templates_file, [])

    def save_templates(self, data: list) -> list:
        with self._lock:
            _write_json(self._templates_file, data)
        return data

    # ── Fonts ──────────────────────────────────────────────────────────────────

    def list_fonts(self) -> list:
        """Scan the user fonts directory and return font metadata dicts.

        Each subdir of ``data_dir/fonts/user/`` that contains at least one
        font file (.woff, .woff2, .ttf, .otf) is returned as a font entry.
        Missing or empty directory returns an empty list without error.
        """
        _ALLOWED = {".woff", ".woff2", ".ttf", ".otf"}
        fonts_user_dir = self._data_dir / "fonts" / "user"
        results = []
        if not fonts_user_dir.exists():
            return results
        for family_dir in sorted(p for p in fonts_user_dir.iterdir() if p.is_dir()):
            slug = family_dir.name
            font_files = [
                f for f in sorted(family_dir.iterdir())
                if f.is_file() and f.suffix.lower() in _ALLOWED
            ]
            if not font_files:
                continue
            family = " ".join(part.capitalize() for part in slug.replace("-", " ").split())
            css_url = f"/fonts/user/{slug}/font.css"
            # Use the first font file as the representative file_path.
            file_path = str(font_files[0])
            # cached_at from file mtime (isoformat string).
            import datetime as _dt
            cached_at = _dt.datetime.fromtimestamp(
                font_files[0].stat().st_mtime, tz=_dt.timezone.utc
            ).isoformat()
            results.append({
                "slug": slug,
                "family": family,
                "source": "user",
                "css_url": css_url,
                "file_path": file_path,
                "upload_metadata": {},
                "cached_at": cached_at,
            })
        return results

    def get_font(self, slug: str) -> "dict | None":
        """Return a single font's metadata dict by slug, or None if not found."""
        for font in self.list_fonts():
            if font.get("slug") == slug:
                return font
        return None

    def save_font(
        self,
        name: str,
        filename: str,
        data: bytes,
        mime_type: str,
    ) -> dict:
        """Write font binary to the local user-fonts directory.

        Desktop mode only — writes to ``<data_dir>/fonts/user/<slug>/<filename>``.
        Returns ``{id, name, url}`` where ``url`` is the local CSS helper path.
        """
        import re as _re
        slug = _re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "font"
        safe_name = _re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or f"{slug}.font"
        dest_dir = self._data_dir / "fonts" / "user" / slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / safe_name).write_bytes(data)
        css_url = f"/fonts/user/{slug}/font.css"
        return {"id": slug, "name": name, "url": css_url}

    def delete_font(self, font_id: str) -> bool:
        """Remove a local user-font directory by slug.

        Desktop mode only — removes ``<data_dir>/fonts/user/<slug>/``.
        Returns True if the directory existed.
        """
        import re as _re
        import shutil as _shutil
        slug = _re.sub(r"[^a-z0-9]+", "-", font_id.strip().lower()).strip("-") or "font"
        target = self._data_dir / "fonts" / "user" / slug
        if target.exists():
            _shutil.rmtree(target)
            return True
        return False


# ---------------------------------------------------------------------------
# ConflictError — raised by transactional save on revision mismatch
# ---------------------------------------------------------------------------

class ConflictError(Exception):
    """Raised by save_project_transactional() when the client revision is stale.

    ``self.project`` holds the current server-side project dict (as returned
    by ``get_project()``) so callers can extract the authoritative revision,
    updated_at, and updated_by_email for a 409 response.
    """

    def __init__(self, project: dict) -> None:
        super().__init__(
            f"Revision conflict: server is at revision {project.get('revision')}"
        )
        self.project = project


# ---------------------------------------------------------------------------
# Postgres stub (server mode — adapted for multi-tenant schema, issue 004 / #260)
# ---------------------------------------------------------------------------

class PostgresStorageBackend(StorageBackend):
    """Postgres-backed storage for multi-user server deployments.

    Multi-tenant aware: when *workspace_id* and *user_claims* are supplied,
    every method scopes its query to that workspace and passes the JWT claims
    to ``db.transaction(claims)`` so RLS sees ``auth.uid()``.

    Backward-compatible: both arguments default to None.  When None the
    backend behaves as before (no workspace filter, no claims → un-scoped
    plain transaction).  This preserves the no-arg ``PostgresStorageBackend()``
    call used by ``get_storage()`` and the ~87 existing tests.
    """

    def __init__(
        self,
        workspace_id: "str | None" = None,
        user_claims: "dict | None" = None,
    ) -> None:
        self.workspace_id = workspace_id
        self.user_claims = user_claims

    def _transaction(self):
        """Return ``db.transaction(claims=self.user_claims)``.

        When user_claims is None this is a plain transaction (current behaviour).
        When user_claims is set, RLS will see auth.uid() from the JWT sub.
        """
        from db import transaction  # noqa: PLC0415
        return transaction(claims=self.user_claims)

    # ── Projects ──────────────────────────────────────────────────────────────

    def list_projects(self, user_id: str | None = None) -> list:
        """Return projects visible to *user_id*, or all projects when user_id is None.

        When *user_id* is provided (normal server-mode operation) this delegates
        to ``list_projects_for_user()`` which filters by visibility/ownership.
        When *user_id* is None (admin/migration use) all projects are returned.
        """
        if user_id is not None:
            return self.list_projects_for_user(user_id)
        params: dict = {}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "WHERE p.workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id
        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                SELECT p.id, p.name, p.owner_user_id, p.visibility, p.state,
                       p.revision, p.created_at, p.updated_at,
                       p.created_by_user_id, p.updated_by_user_id,
                       pc.email AS created_by_email,
                       pu.email AS updated_by_email,
                       pc.display_name AS created_by_name,
                       pu.display_name AS updated_by_name
                FROM projects p
                LEFT JOIN public.profiles pc ON pc.id = p.created_by_user_id
                LEFT JOIN public.profiles pu ON pu.id = p.updated_by_user_id
                {ws_clause}
                ORDER BY p.updated_at DESC
                """,
                params,
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [_pg_row_to_project(dict(zip(cols, row))) for row in rows]

    def list_projects_for_user(self, user_id: str) -> list:
        """Return all projects visible to *user_id*.

        A project is visible when:
          - visibility='workspace'  (every authenticated user can see it)
          - visibility='private' AND owner_user_id = user_id  (own private project)
          - visibility='private' AND owner_user_id IS NULL  (legacy import, accessible to all)
        """
        params: dict = {"user_id": user_id}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "AND p.workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id
        with self._transaction() as conn:
            # Exclude `state` from the list query — state blobs can be many MB
            # each and are not needed for the file picker.  Full state is
            # fetched on-demand by get_project() when a project is opened.
            cursor = conn.execute(
                f"""
                SELECT p.id, p.name, p.owner_user_id, p.visibility,
                       p.revision, p.created_at, p.updated_at,
                       p.created_by_user_id, p.updated_by_user_id,
                       pc.email AS created_by_email,
                       pu.email AS updated_by_email,
                       pc.display_name AS created_by_name,
                       pu.display_name AS updated_by_name,
                       po.display_name AS owner_display_name,
                       po.email AS owner_email
                FROM projects p
                LEFT JOIN public.profiles pc ON pc.id = p.created_by_user_id
                LEFT JOIN public.profiles pu ON pu.id = p.updated_by_user_id
                LEFT JOIN public.profiles po ON po.id = p.owner_user_id
                WHERE (
                    visibility = 'workspace'
                    OR owner_user_id = %(user_id)s::uuid
                    OR (visibility = 'private' AND owner_user_id IS NULL)
                )
                {ws_clause}
                ORDER BY p.updated_at DESC
                """,
                params,
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [_pg_row_to_project(dict(zip(cols, row))) for row in rows]

    def get_project(self, project_id: str) -> dict | None:
        """Return a single project dict by id, or None if not found.

        Returns None (not raises) when RLS returns 0 rows, so the caller
        cannot distinguish 'not found' from 'forbidden' (avoids leaking
        found-vs-forbidden to the frontend).
        """
        params: dict = {"id": project_id}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "AND p.workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id
        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                SELECT p.id, p.name, p.owner_user_id, p.visibility, p.state,
                       p.revision, p.created_at, p.updated_at,
                       p.created_by_user_id, p.updated_by_user_id,
                       pc.email AS created_by_email,
                       pu.email AS updated_by_email,
                       pc.display_name AS created_by_name,
                       pu.display_name AS updated_by_name
                FROM projects p
                LEFT JOIN public.profiles pc ON pc.id = p.created_by_user_id
                LEFT JOIN public.profiles pu ON pu.id = p.updated_by_user_id
                WHERE p.id = %(id)s
                {ws_clause}
                """,
                params,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cursor.description]
        return _pg_row_to_project(dict(zip(cols, row)))

    def save_project(self, data: dict, *, updated_by_email: str = "", updated_by_user_id: str | None = None) -> dict:
        """Upsert a project and return the persisted dict.

        * On INSERT  — revision defaults to 1; owner_user_id / created_by_user_id
                       set from ``updated_by_user_id``; workspace_id from self.workspace_id
                       (required for INSERT when scoped, else None → DB constraint).
        * On UPDATE  — revision is incremented by 1; updated_by_user_id set from caller.

        ``data`` must contain an ``id`` key (text string — NOT cast to uuid).

        ``updated_by_email`` and ``updated_by_user_id`` are caller-supplied attribution
        values.  The new schema stores user IDs, not emails, so ``updated_by_email``
        is accepted for backward-compat but only used for the profiles JOIN fallback.
        """
        if "id" not in data:
            raise ValueError("project data must contain an 'id' key")

        import json as _json  # noqa: PLC0415

        project_id = data["id"]

        # Upload base64 cover/logo images to Supabase Storage (server mode only).
        # Falls back to base64 silently if the upload fails or Storage is unconfigured.
        if self.workspace_id is not None:
            from storage_assets import extract_and_upload_images  # noqa: PLC0415
            data = extract_and_upload_images(data, self.workspace_id, project_id)

        name = str(data.get("name") or "")
        state_json = _json.dumps(data, ensure_ascii=False)
        created_at = data.get("createdAt") or None

        with self._transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (
                    id, workspace_id, name, owner_user_id, visibility, state, revision,
                    created_at, updated_at, created_by_user_id, updated_by_user_id
                ) VALUES (
                    %(id)s, %(workspace_id)s::uuid, %(name)s,
                    %(owner_user_id)s::uuid,
                    'workspace', %(state)s::jsonb, 1,
                    COALESCE(%(created_at)s::timestamptz, now()),
                    now(),
                    %(created_by_user_id)s::uuid, %(updated_by_user_id)s::uuid
                )
                ON CONFLICT (id) DO UPDATE SET
                    name                = EXCLUDED.name,
                    state               = EXCLUDED.state,
                    revision            = projects.revision + 1,
                    updated_at          = now(),
                    updated_by_user_id  = EXCLUDED.updated_by_user_id
                RETURNING id, name, owner_user_id, visibility, state, revision,
                          created_at, updated_at, created_by_user_id, updated_by_user_id,
                          workspace_id
                """,
                {
                    "id": project_id,
                    "workspace_id": self.workspace_id,
                    "name": name,
                    "owner_user_id": updated_by_user_id,
                    "state": state_json,
                    "created_at": created_at,
                    "created_by_user_id": updated_by_user_id,
                    "updated_by_user_id": updated_by_user_id,
                },
            )
            row = cursor.fetchone()
            raw_cols = [d[0] for d in cursor.description]
            raw = dict(zip(raw_cols, row))
            # JOIN profiles to get attribution emails for the returned dict.
            return _pg_enrich_project_row(conn, raw)

    def save_project_transactional(
        self,
        data: dict,
        client_revision: int | None,
        *,
        updated_by_email: str = "",
        updated_by_user_id: str | None = None,
        updated_by_name: str = "",
    ) -> dict:
        """Save a project transactionally, only when *client_revision* matches.

        Uses ``UPDATE ... WHERE id=? AND revision=?`` so that two concurrent
        saves cannot both overwrite the same revision.

        On success:
          - Increments the project revision by 1.
          - Inserts a snapshot row into ``project_revisions``.
          - Returns the updated project dict.

        Raises:
            ConflictError: when rowcount == 0 (revision mismatch or project missing).
                           ``ConflictError.project`` contains the current server-side
                           project dict for building the 409 response.
            ValueError: when ``data`` has no ``id`` key.
        """
        if "id" not in data:
            raise ValueError("project data must contain an 'id' key")

        import json as _json  # noqa: PLC0415
        import uuid as _uuid  # noqa: PLC0415
        from db import from_jsonb  # noqa: PLC0415
        from revisions import generate_summary  # noqa: PLC0415

        project_id = data["id"]

        # Upload base64 cover/logo images to Supabase Storage (server mode only).
        # Falls back to base64 silently if the upload fails or Storage is unconfigured.
        if self.workspace_id is not None:
            from storage_assets import extract_and_upload_images  # noqa: PLC0415
            data = extract_and_upload_images(data, self.workspace_id, project_id)

        name = str(data.get("name") or "")
        state_json = _json.dumps(data, ensure_ascii=False)

        # Treat a missing client_revision as 0 — will conflict unless the
        # project is brand-new (revision 0 in DB, which should not occur in
        # practice because inserts start at revision 1).
        effective_client_rev = int(client_revision) if client_revision is not None else 0

        ws_clause = ""
        params_base: dict = {"id": project_id}
        if self.workspace_id is not None:
            ws_clause = "AND workspace_id = %(workspace_id)s::uuid"
            params_base["workspace_id"] = self.workspace_id

        with self._transaction() as conn:
            # Fetch the previous state BEFORE updating so we can generate a
            # meaningful summary of what changed.
            prev_cursor = conn.execute(
                f"SELECT state FROM projects WHERE id = %(id)s {ws_clause}",
                params_base,
            )
            prev_row = prev_cursor.fetchone()
            if prev_row is not None:
                prev_state = from_jsonb(prev_row[0])
                if not isinstance(prev_state, dict):
                    prev_state = None
            else:
                prev_state = None

            cursor = conn.execute(
                f"""
                UPDATE projects
                SET
                    name               = %(name)s,
                    state              = %(state)s::jsonb,
                    revision           = revision + 1,
                    updated_at         = NOW(),
                    updated_by_user_id = %(updated_by_user_id)s::uuid
                WHERE id = %(id)s
                  AND revision = %(client_revision)s
                  {ws_clause}
                RETURNING id, name, owner_user_id, visibility, state, revision,
                          created_at, updated_at, created_by_user_id, updated_by_user_id,
                          workspace_id
                """,
                {
                    **params_base,
                    "name": name,
                    "state": state_json,
                    "updated_by_user_id": updated_by_user_id,
                    "client_revision": effective_client_rev,
                },
            )
            row = cursor.fetchone()

            if row is None:
                # Either revision mismatch or project does not exist.  Fetch the
                # current server state so the caller can build a 409 body.
                cur2 = conn.execute(
                    f"""
                    SELECT p.id, p.name, p.owner_user_id, p.visibility, p.state,
                           p.revision, p.created_at, p.updated_at,
                           p.created_by_user_id, p.updated_by_user_id, p.workspace_id,
                           pc.email AS created_by_email,
                           pu.email AS updated_by_email,
                           pc.display_name AS created_by_name,
                           pu.display_name AS updated_by_name
                    FROM projects p
                    LEFT JOIN public.profiles pc ON pc.id = p.created_by_user_id
                    LEFT JOIN public.profiles pu ON pu.id = p.updated_by_user_id
                    WHERE p.id = %(id)s
                    {ws_clause}
                    """,
                    params_base,
                )
                server_row = cur2.fetchone()
                if server_row is not None:
                    cols2 = [d[0] for d in cur2.description]
                    server_project = _pg_row_to_project(dict(zip(cols2, server_row)))
                else:
                    # Project doesn't exist at all — surface a generic conflict.
                    server_project = {"id": project_id, "revision": 0}
                raise ConflictError(server_project)

            raw_cols = [d[0] for d in cursor.description]
            raw = dict(zip(raw_cols, row))
            saved_project = _pg_enrich_project_row(conn, raw)
            new_revision = saved_project["revision"]

            # Generate a human-readable summary of the changes.
            summary = generate_summary(prev_state, data)

            # Insert a revision snapshot (append-only table).
            # New schema: project_id is TEXT, workspace_id required,
            # revision_number (not revision), created_by_user_id (not saved_by_*).
            conn.execute(
                """
                INSERT INTO project_revisions (
                    id, project_id, workspace_id, revision_number, state,
                    created_at, created_by_user_id, summary
                ) VALUES (
                    %(snap_id)s::uuid,
                    %(project_id)s,
                    %(workspace_id)s::uuid,
                    %(revision_number)s,
                    %(state)s::jsonb,
                    NOW(),
                    %(created_by_user_id)s::uuid,
                    %(summary)s
                )
                """,
                {
                    "snap_id": str(_uuid.uuid4()),
                    "project_id": project_id,
                    "workspace_id": self.workspace_id,
                    "revision_number": new_revision,
                    "state": state_json,
                    "created_by_user_id": updated_by_user_id,
                    "summary": summary,
                },
            )

        return saved_project

    def delete_project(self, project_id: str) -> bool:
        """Delete a project by id; return True if it existed."""
        params: dict = {"id": project_id}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "AND workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id
        with self._transaction() as conn:
            cursor = conn.execute(
                f"DELETE FROM projects WHERE id = %(id)s {ws_clause}",
                params,
            )
        return cursor.rowcount == 1

    def share_project_to_workspace(self, project_id: str) -> "dict | None":
        """Set visibility='workspace' on the project and return the updated dict.

        Returns the updated project dict, or None if the project was not found.
        """
        params: dict = {"id": project_id}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "AND workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id
        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                UPDATE projects
                SET visibility = 'workspace', updated_at = NOW()
                WHERE id = %(id)s
                {ws_clause}
                RETURNING id, name, owner_user_id, visibility, state, revision,
                          created_at, updated_at, created_by_user_id, updated_by_user_id,
                          workspace_id
                """,
                params,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            raw_cols = [d[0] for d in cursor.description]
            raw = dict(zip(raw_cols, row))
            return _pg_enrich_project_row(conn, raw)

    def transfer_project_owner(
        self,
        project_id: str,
        from_user_id: str,
        to_user_id: str,
    ) -> "dict | None":
        """Transfer ownership of a project to another workspace member.

        Uses ``UPDATE ... WHERE id=? AND workspace_id=? AND owner_user_id=from_user_id``
        so that only the current owner may transfer.  Returns the updated project
        dict on success, or ``None`` if no matching row was updated (project not
        found, wrong workspace, or caller is not the current owner).

        ``to_user_id`` must be validated as a workspace member by the caller
        *before* calling this method.
        """
        params: dict = {
            "id": project_id,
            "from": from_user_id,
            "to": to_user_id,
        }
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "AND workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id

        # Transfer must bypass RLS: the WITH CHECK policy requires owner_user_id = auth.uid()
        # on the NEW row, but after transfer the new owner_user_id is the target user.
        # admin_transaction() uses the service role which skips RLS — ownership verification
        # (caller must be current owner) is enforced by the WHERE clause below.
        from db import admin_transaction  # noqa: PLC0415
        with admin_transaction() as conn:
            cursor = conn.execute(
                f"""
                UPDATE projects
                SET owner_user_id = %(to)s::uuid,
                    updated_at = NOW()
                WHERE id = %(id)s
                  AND owner_user_id = %(from)s::uuid
                  {ws_clause}
                RETURNING id, name, owner_user_id, visibility, state, revision,
                          created_at, updated_at, created_by_user_id, updated_by_user_id,
                          workspace_id
                """,
                params,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            raw_cols = [d[0] for d in cursor.description]
            raw = dict(zip(raw_cols, row))
            return _pg_enrich_project_row(conn, raw)

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        """Read the workspace_settings row for this workspace and return the
        settings dict.

        When workspace_id is None (un-scoped / backward-compat mode), queries
        workspace_settings without a filter — this will raise RuntimeError in
        desktop mode (preserving the existing test contract) and return all rows
        in server mode (admin use).

        The settings JSONB blob is returned as-is.  OAuth tokens and other
        flat keys that were previously stored per-row in org_settings should
        be migrated into this blob by issue 015 tooling.
        """
        from db import from_jsonb  # noqa: PLC0415

        if self.workspace_id is not None:
            params: dict = {"workspace_id": self.workspace_id}
            sql = "SELECT settings FROM workspace_settings WHERE workspace_id = %(workspace_id)s::uuid"
        else:
            params = {}
            # Un-scoped: a no-workspace-filter query; raises RuntimeError in
            # desktop mode (preserving prior contract) and returns first row in server mode.
            sql = "SELECT settings FROM workspace_settings LIMIT 1"

        with self._transaction() as conn:
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()

        if row is None:
            return {}
        return from_jsonb(row[0]) or {}

    def save_settings(self, data: dict) -> dict:
        """Persist settings dict into workspace_settings for this workspace.

        Uses INSERT ... ON CONFLICT DO UPDATE (upsert) so the row is created
        on first save.  When workspace_id is None, raises RuntimeError because
        we cannot upsert without a PK value.

        Returns the full settings dict as reconstructed by get_settings().
        """
        import json as _json  # noqa: PLC0415

        if self.workspace_id is None:
            raise RuntimeError(
                "save_settings requires a workspace_id — "
                "construct PostgresStorageBackend(workspace_id=...) first."
            )

        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO workspace_settings (workspace_id, settings)
                VALUES (%(workspace_id)s::uuid, %(settings)s::jsonb)
                ON CONFLICT (workspace_id) DO UPDATE SET
                    settings = EXCLUDED.settings
                """,
                {
                    "workspace_id": self.workspace_id,
                    "settings": _json.dumps(data, ensure_ascii=False),
                },
            )

        return self.get_settings()

    # ── Announcements ─────────────────────────────────────────────────────────

    def list_announcements(self) -> list:
        """Return all announcements for this workspace, ordered by created_at ASC.

        The new schema stores the full announcement payload in a ``state`` JSONB
        column (no separate url/ordering columns).  We reconstruct the frontend
        shape from state + DB-authoritative scalar fields.

        When workspace_id is None, returns all announcements (un-scoped admin use).
        """
        from db import from_jsonb  # noqa: PLC0415

        params: dict = {}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "WHERE workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id

        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                SELECT id, workspace_id, title, body, state, created_at, updated_at,
                       created_by_user_id
                FROM announcements
                {ws_clause}
                ORDER BY created_at ASC
                """,
                params,
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]

        result = []
        for row in rows:
            d = dict(zip(cols, row))
            state = from_jsonb(d.get("state")) or {}
            if not isinstance(state, dict):
                state = {}
            # Merge DB-authoritative fields over the state blob.
            state["id"] = str(d["id"])
            state["title"] = d.get("title") or state.get("title") or ""
            state["body"] = d.get("body") or state.get("body") or ""
            state["created_at"] = _ts(d.get("created_at"))
            state["updated_at"] = _ts(d.get("updated_at"))
            result.append(state)
        return result

    def save_announcements(self, data: list) -> list:
        """Replace all announcements for this workspace: DELETE then INSERT.

        Each item in *data* must be a dict with at least a ``title`` key.
        The full item dict is stored in the ``state`` JSONB column so no
        data is lost when the schema has fewer columns than the payload.

        When workspace_id is None, raises RuntimeError (cannot insert without
        workspace_id foreign key).

        Returns the saved list as read back from the database.
        """
        import json as _json  # noqa: PLC0415
        import uuid as _uuid  # noqa: PLC0415

        _ANN_NAMESPACE = _uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        if self.workspace_id is None:
            raise RuntimeError(
                "save_announcements requires a workspace_id — "
                "construct PostgresStorageBackend(workspace_id=...) first."
            )

        # Extract user_id from claims for created_by_user_id attribution.
        user_id: "str | None" = None
        if self.user_claims and isinstance(self.user_claims, dict):
            user_id = self.user_claims.get("sub") or None

        with self._transaction() as conn:
            conn.execute(
                "DELETE FROM announcements WHERE workspace_id = %(workspace_id)s::uuid",
                {"workspace_id": self.workspace_id},
            )
            for item in data:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "")
                body = str(item.get("body") or "")

                # Resolve id → must be a valid UUID.
                raw_id = item.get("id") or ""
                if raw_id:
                    try:
                        ann_id = str(_uuid.UUID(str(raw_id)))
                    except ValueError:
                        ann_id = str(_uuid.uuid5(_ANN_NAMESPACE, str(raw_id)))
                else:
                    fingerprint = f"{title}\x00{body}"
                    ann_id = str(_uuid.uuid5(_ANN_NAMESPACE, fingerprint))

                state_json = _json.dumps(item, ensure_ascii=False)

                conn.execute(
                    """
                    INSERT INTO announcements (
                        id, workspace_id, title, body, state, created_by_user_id
                    ) VALUES (
                        %(id)s::uuid, %(workspace_id)s::uuid,
                        %(title)s, %(body)s,
                        %(state)s::jsonb,
                        %(created_by_user_id)s::uuid
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title               = EXCLUDED.title,
                        body                = EXCLUDED.body,
                        state               = EXCLUDED.state,
                        updated_at          = now()
                    """,
                    {
                        "id": ann_id,
                        "workspace_id": self.workspace_id,
                        "title": title,
                        "body": body,
                        "state": state_json,
                        "created_by_user_id": user_id,
                    },
                )

        return self.list_announcements()

    # ── Songs ─────────────────────────────────────────────────────────────────

    def list_songs(self) -> list:
        """Return all songs for this workspace ordered by title ASC.

        The new schema stores the full song payload in a ``data`` JSONB column
        (no separate author/lyrics/copyright/source/date_added columns).
        We reconstruct the frontend shape from data + DB-authoritative fields.
        """
        from db import from_jsonb  # noqa: PLC0415

        params: dict = {}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "WHERE workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id

        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                SELECT id, workspace_id, title, data, created_at, updated_at
                FROM songs
                {ws_clause}
                ORDER BY title ASC
                """,
                params,
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]

        return [_pg_row_to_song(dict(zip(cols, row))) for row in rows]

    def save_songs(self, data: list) -> list:
        """Upsert each song in *data* individually; never deletes existing rows.

        The full song dict is stored in the ``data`` JSONB column.
        An ``id`` is required; if the raw id is not a valid UUID a stable
        UUID5 is generated from title+author+source.

        When workspace_id is None, raises RuntimeError.

        Returns the full songs list as read back from the database (title ASC).
        """
        import json as _json  # noqa: PLC0415
        import uuid as _uuid  # noqa: PLC0415

        _SONG_NAMESPACE = _uuid.UUID("c0ffee00-d400-4db0-0000-000000000000")

        if self.workspace_id is None:
            raise RuntimeError(
                "save_songs requires a workspace_id — "
                "construct PostgresStorageBackend(workspace_id=...) first."
            )

        with self._transaction() as conn:
            for item in data:
                if not isinstance(item, dict):
                    continue

                title = str(item.get("title") or "")
                author = str(item.get("author") or "")
                source = str(item.get("source") or "")

                # Resolve id → must be a valid UUID.
                raw_id = item.get("id") or ""
                if raw_id:
                    try:
                        song_id = str(_uuid.UUID(str(raw_id)))
                    except ValueError:
                        fingerprint = f"{title}\x00{author}\x00{source}"
                        song_id = str(_uuid.uuid5(_SONG_NAMESPACE, fingerprint))
                else:
                    fingerprint = f"{title}\x00{author}\x00{source}"
                    song_id = str(_uuid.uuid5(_SONG_NAMESPACE, fingerprint))

                data_json = _json.dumps(item, ensure_ascii=False)

                conn.execute(
                    """
                    INSERT INTO songs (id, workspace_id, title, data)
                    VALUES (
                        %(id)s::uuid, %(workspace_id)s::uuid,
                        %(title)s, %(data)s::jsonb
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title      = EXCLUDED.title,
                        data       = EXCLUDED.data,
                        updated_at = now()
                    """,
                    {
                        "id": song_id,
                        "workspace_id": self.workspace_id,
                        "title": title,
                        "data": data_json,
                    },
                )

        return self.list_songs()

    # ── Templates ─────────────────────────────────────────────────────────────

    def list_templates(self) -> list:
        """Return all templates for this workspace ordered by is_default DESC, name ASC.

        The new schema uses ``template_data`` (not ``data``) and ``is_default``
        (not ``built_in``).  We map these to the frontend shape via
        ``_pg_row_to_template``.
        """
        params: dict = {}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "WHERE workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id

        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                SELECT id, name, template_data, is_default
                FROM templates
                {ws_clause}
                ORDER BY is_default DESC, name ASC
                """,
                params,
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [_pg_row_to_template(dict(zip(cols, row))) for row in rows]

    def save_templates(self, data: list) -> list:
        """Upsert each custom template in *data*; default templates are never modified.

        For each item in *data*:
        * If ``is_default``/``built_in``/``builtIn`` is True → skip silently (protected).
        * Otherwise → upsert.

        The full item dict is stored in ``template_data`` JSONB.

        When workspace_id is None, raises RuntimeError.

        Returns the full templates list as read back from the database.
        """
        import json as _json  # noqa: PLC0415
        import uuid as _uuid  # noqa: PLC0415

        _TEMPLATE_NAMESPACE = _uuid.UUID("b01e7e00-7e00-4000-8000-000000000000")

        if self.workspace_id is None:
            raise RuntimeError(
                "save_templates requires a workspace_id — "
                "construct PostgresStorageBackend(workspace_id=...) first."
            )

        with self._transaction() as conn:
            for item in data:
                if not isinstance(item, dict):
                    continue

                # Default/built-in templates are protected — never update them.
                if item.get("is_default") or item.get("built_in") or item.get("builtIn"):
                    continue

                name = str(item.get("name") or "")

                # Resolve id → must be a valid UUID.
                raw_id = item.get("id") or ""
                if raw_id:
                    try:
                        template_id = str(_uuid.UUID(str(raw_id)))
                    except ValueError:
                        template_id = str(_uuid.uuid5(_TEMPLATE_NAMESPACE, str(raw_id)))
                else:
                    template_id = str(_uuid.uuid5(_TEMPLATE_NAMESPACE, name))

                data_json = _json.dumps(item, ensure_ascii=False)

                conn.execute(
                    """
                    INSERT INTO templates (id, workspace_id, name, template_data, is_default)
                    VALUES (%(id)s::uuid, %(workspace_id)s::uuid, %(name)s, %(data)s::jsonb, FALSE)
                    ON CONFLICT (id) DO UPDATE SET
                        name          = EXCLUDED.name,
                        template_data = EXCLUDED.template_data,
                        updated_at    = now()
                    WHERE NOT templates.is_default
                    """,
                    {
                        "id": template_id,
                        "workspace_id": self.workspace_id,
                        "name": name,
                        "data": data_json,
                    },
                )

        return self.list_templates()

    # ── Fonts ──────────────────────────────────────────────────────────────────

    def list_fonts(self) -> list:
        """Return all fonts for this workspace ordered by name ASC.

        The new schema has: id, workspace_id, name, storage_path, mime_type,
        created_at.  There is no slug/family/source/css_url/upload_metadata.
        We map these to a compatible dict shape.
        """
        params: dict = {}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "WHERE workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id

        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                SELECT id, workspace_id, name, storage_path, mime_type, created_at
                FROM fonts
                {ws_clause}
                ORDER BY name ASC
                """,
                params,
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [_pg_row_to_font(dict(zip(cols, row))) for row in rows]

    def get_font(self, slug: str) -> "dict | None":
        """Return a single font metadata dict by name (slug), or None if not found.

        In the new schema there is no separate slug column; we match on ``name``.
        """
        params: dict = {"name": slug}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "AND workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id

        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                SELECT id, workspace_id, name, storage_path, mime_type, created_at
                FROM fonts
                WHERE name = %(name)s
                {ws_clause}
                """,
                params,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cursor.description]
        return _pg_row_to_font(dict(zip(cols, row)))

    def save_font(
        self,
        name: str,
        filename: str,
        data: bytes,
        mime_type: str,
    ) -> dict:
        """Upload font binary to Supabase Storage and insert a ``fonts`` row.

        Storage path: ``workspace-fonts/<workspace_id>/<filename>``.
        Uses the Supabase Storage REST API with the service-role key
        (``SUPABASE_SERVICE_ROLE_KEY``) so the upload bypasses RLS.
        The ``fonts`` table INSERT runs under the user's JWT claims so RLS
        still applies to the metadata row.

        Returns ``{id, name, url}`` where ``url`` is the Storage public URL.

        Raises RuntimeError when workspace_id is None or Supabase env vars are
        missing.
        """
        if self.workspace_id is None:
            raise RuntimeError(
                "save_font requires workspace_id — use a scoped storage backend."
            )
        storage_path = f"workspace-fonts/{self.workspace_id}/{filename}"
        storage_url = _supabase_storage_upload(storage_path, data, mime_type)

        with self._transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO fonts (workspace_id, name, storage_path, mime_type)
                VALUES (%(workspace_id)s::uuid, %(name)s, %(storage_path)s, %(mime_type)s)
                RETURNING id
                """,
                {
                    "workspace_id": self.workspace_id,
                    "name": name,
                    "storage_path": storage_path,
                    "mime_type": mime_type,
                },
            )
            row = cursor.fetchone()
            font_id = str(row[0])

        return {"id": font_id, "name": name, "url": storage_url}

    def delete_font(self, font_id: str) -> bool:
        """Delete the Storage object and the ``fonts`` table row for *font_id*.

        *font_id* is the UUID primary key of the ``fonts`` row.  The Storage
        object path is fetched first; if the row is not found or belongs to a
        different workspace, returns False without deleting anything.

        Returns True if the font was found and deleted.
        """
        if self.workspace_id is None:
            raise RuntimeError(
                "delete_font requires workspace_id — use a scoped storage backend."
            )

        # Fetch storage_path while asserting workspace ownership.
        with self._transaction() as conn:
            cursor = conn.execute(
                """
                SELECT storage_path FROM fonts
                WHERE id = %(font_id)s::uuid
                  AND workspace_id = %(workspace_id)s::uuid
                """,
                {"font_id": font_id, "workspace_id": self.workspace_id},
            )
            row = cursor.fetchone()
            if row is None:
                return False
            storage_path = row[0]

            # Delete the metadata row.
            conn.execute(
                """
                DELETE FROM fonts
                WHERE id = %(font_id)s::uuid
                  AND workspace_id = %(workspace_id)s::uuid
                """,
                {"font_id": font_id, "workspace_id": self.workspace_id},
            )

        # Delete the Storage object (best-effort; log on failure).
        if storage_path:
            try:
                _supabase_storage_delete(storage_path)
            except Exception as exc:  # noqa: BLE001
                print(f"  [storage] warn: Storage delete failed for {storage_path}: {exc}")

        return True

    # ── Project revisions ──────────────────────────────────────────────────────

    def get_project_revisions(self, project_id: str) -> list:
        """Return revision metadata for *project_id*, newest first.

        New schema: revision_number (not revision), created_by_user_id (not
        saved_by_*).  We JOIN profiles to surface email/display_name and map
        them to the legacy saved_by_email / saved_by_name keys for API compat.
        """
        params: dict = {"project_id": project_id}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "AND pr.workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id

        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                SELECT pr.id, pr.project_id, pr.revision_number, pr.summary,
                       pr.created_at,
                       pr.created_by_user_id,
                       p.email     AS saved_by_email,
                       p.display_name AS saved_by_name
                FROM project_revisions pr
                LEFT JOIN public.profiles p ON p.id = pr.created_by_user_id
                WHERE pr.project_id = %(project_id)s
                {ws_clause}
                ORDER BY pr.revision_number DESC
                """,
                params,
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]

        result = []
        for row in rows:
            d = dict(zip(cols, row))
            result.append({
                "id": str(d["id"]),
                "project_id": str(d["project_id"]),
                "revision": d["revision_number"],
                "saved_at": _ts(d.get("created_at")),
                "saved_by_email": d.get("saved_by_email") or "",
                "saved_by_name": d.get("saved_by_name") or "",
                "summary": d.get("summary") or "",
            })
        return result

    def get_project_revision(self, project_id: str, revision: int) -> "dict | None":
        """Return the full revision snapshot including state for *project_id* at *revision*.

        Returns a dict with all ``project_revisions`` columns, or ``None``
        if no matching row is found.
        """
        from db import from_jsonb  # noqa: PLC0415

        params: dict = {"project_id": project_id, "revision_number": revision}
        ws_clause = ""
        if self.workspace_id is not None:
            ws_clause = "AND pr.workspace_id = %(workspace_id)s::uuid"
            params["workspace_id"] = self.workspace_id

        with self._transaction() as conn:
            cursor = conn.execute(
                f"""
                SELECT pr.id, pr.project_id, pr.revision_number, pr.state,
                       pr.created_at, pr.created_by_user_id,
                       p.email        AS saved_by_email,
                       p.display_name AS saved_by_name,
                       pr.summary
                FROM project_revisions pr
                LEFT JOIN public.profiles p ON p.id = pr.created_by_user_id
                WHERE pr.project_id = %(project_id)s
                  AND pr.revision_number = %(revision_number)s
                {ws_clause}
                """,
                params,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cursor.description]
            raw = dict(zip(cols, row))
        return {
            "id": str(raw["id"]),
            "project_id": str(raw["project_id"]),
            "revision": raw["revision_number"],
            "state": from_jsonb(raw.get("state")),
            "saved_at": _ts(raw.get("created_at")),
            "saved_by_user_id": str(raw["created_by_user_id"]) if raw.get("created_by_user_id") else None,
            "saved_by_email": raw.get("saved_by_email") or "",
            "saved_by_name": raw.get("saved_by_name") or "",
            "summary": raw.get("summary") or "",
        }


# ---------------------------------------------------------------------------
# Postgres project row enrichment helper (LEFT JOIN profiles for attribution)
# ---------------------------------------------------------------------------

def _pg_enrich_project_row(conn, raw: dict) -> dict:
    """Given a raw project row (from INSERT/UPDATE RETURNING), JOIN profiles to
    add created_by_email / updated_by_email / created_by_name / updated_by_name,
    then delegate to _pg_row_to_project.

    Used after INSERT/UPDATE RETURNING which does not include a profiles JOIN.
    """
    created_uid = raw.get("created_by_user_id")
    updated_uid = raw.get("updated_by_user_id")

    emails: dict = {}
    uids_to_fetch = {u for u in (created_uid, updated_uid) if u is not None}
    if uids_to_fetch:
        cur = conn.execute(
            "SELECT id, email, display_name FROM public.profiles WHERE id = ANY(%s)",
            [list(uids_to_fetch)],
        )
        for r in cur.fetchall():
            emails[str(r[0])] = {"email": r[1] or "", "display_name": r[2] or ""}

    raw["created_by_email"] = emails.get(str(created_uid), {}).get("email") if created_uid else None
    raw["updated_by_email"] = emails.get(str(updated_uid), {}).get("email") if updated_uid else None
    raw["created_by_name"] = emails.get(str(created_uid), {}).get("display_name") if created_uid else None
    raw["updated_by_name"] = emails.get(str(updated_uid), {}).get("display_name") if updated_uid else None
    return _pg_row_to_project(raw)


# ---------------------------------------------------------------------------
# Postgres row → project dict helper
# ---------------------------------------------------------------------------

def _pg_row_to_project(row: dict) -> dict:
    """Convert a raw Postgres row dict into the project dict shape expected by the frontend.

    The ``state`` column holds the full project payload as JSONB.  We return
    that payload merged with DB-authoritative fields so callers can trust those
    keys even if the stored state blob is missing them.

    New schema notes:
      - id is TEXT (not UUID) — stored/returned as-is, no str() cast needed.
      - No created_by_email / updated_by_email columns directly; these come from
        a LEFT JOIN to public.profiles on created_by_user_id / updated_by_user_id.
        Callers that do the JOIN pass ``created_by_email`` / ``updated_by_email``
        as row keys; callers that skip the JOIN get None (un-scoped / admin).
      - No imported_from_json column in the new schema.

    Metadata fields included (all top-level):
      - id, name, revision  (always present)
      - visibility           ("private" or "workspace")
      - owner_user_id        (UUID string or None)
      - owner_email          (created_by_email from profiles join, may be None)
      - created_at, updated_at (ISO-8601 strings)
      - created_by_email, updated_by_email  (from profiles join)
      - createdAt, updatedAt, createdBy, updatedBy  (camelCase for frontend compat)
    """
    from db import from_jsonb  # noqa: PLC0415

    state = from_jsonb(row.get("state")) or {}
    if not isinstance(state, dict):
        state = {}

    # ── DB-authoritative scalar fields ────────────────────────────────────────
    state["id"] = str(row["id"])
    state["name"] = row.get("name") or state.get("name") or ""
    state["revision"] = row.get("revision") or state.get("revision") or 1

    # ── Ownership & visibility ────────────────────────────────────────────────
    owner_uid = row.get("owner_user_id")
    state["owner_user_id"] = str(owner_uid) if owner_uid is not None else None
    # owner_display_name / owner_email from profiles JOIN on owner_user_id.
    state["owner_display_name"] = row.get("owner_display_name") or None
    state["owner_email"] = row.get("owner_email") or row.get("created_by_email") or None
    state["visibility"] = row.get("visibility") or "workspace"
    # imported_from_json is not in the new schema; preserve if present in the row
    # (backward compat with old schema rows / test fixtures) or state blob.
    if "imported_from_json" in row:
        state["imported_from_json"] = bool(row["imported_from_json"])
    else:
        state.setdefault("imported_from_json", False)

    # ── Timestamps & attribution (snake_case for API consumers) ───────────────
    state["created_at"] = _ts(row.get("created_at")) or None
    state["updated_at"] = _ts(row.get("updated_at")) or None
    # These come from the profiles JOIN; may be None when JOIN is not performed.
    state["created_by_email"] = row.get("created_by_email") or None
    state["updated_by_email"] = row.get("updated_by_email") or None

    # ── Legacy camelCase keys for frontend backward compatibility ─────────────
    if row.get("created_at"):
        state.setdefault("createdAt", _ts(row["created_at"]))
    if row.get("updated_at"):
        state["updatedAt"] = _ts(row["updated_at"])
    # createdBy / updatedBy: use email if available, fall back to display_name.
    created_label = row.get("created_by_email") or row.get("created_by_name") or None
    updated_label = row.get("updated_by_email") or row.get("updated_by_name") or None
    if created_label:
        state.setdefault("createdBy", created_label)
    if updated_label:
        state["updatedBy"] = updated_label

    return state


def _pg_row_to_template(row: dict) -> dict:
    """Convert a raw Postgres templates row dict into the shape expected by the frontend.

    New schema: column is ``template_data`` (not ``data``), ``is_default`` (not
    ``built_in``).  We map both to the frontend shape (``builtIn`` bool key).
    """
    from db import from_jsonb  # noqa: PLC0415

    # Support both old column name (data) and new (template_data) for robustness.
    raw_data = row.get("template_data") if "template_data" in row else row.get("data")
    data = from_jsonb(raw_data) or {}
    if not isinstance(data, dict):
        data = {}

    # Merge DB-authoritative fields on top of the stored data blob.
    data["id"] = str(row["id"])
    data["name"] = row.get("name") or data.get("name") or ""
    # Support both old (built_in) and new (is_default) column names.
    is_default = row.get("is_default") if "is_default" in row else row.get("built_in", False)
    data["builtIn"] = bool(is_default)

    return data


def _pg_row_to_song(row: dict) -> dict:
    """Convert a raw Postgres songs row dict into the shape expected by the frontend.

    New schema: the full song payload is stored in a ``data`` JSONB column.
    We unpack it and merge with DB-authoritative fields (id, title, created_at).
    Legacy flat-column rows (author/lyrics/copyright/source/date_added) are also
    supported so existing import tooling works unchanged.

    Returns camelCase keys that match the legacy song_database.json format.
    """
    from db import from_jsonb  # noqa: PLC0415

    # If the row has a ``data`` JSONB column (new schema), unpack it first.
    blob = from_jsonb(row.get("data")) if "data" in row else {}
    if not isinstance(blob, dict):
        blob = {}

    return {
        "id": str(row["id"]),
        "title": row.get("title") or blob.get("title") or "",
        "author": blob.get("author") or row.get("author") or "",
        "lyrics": blob.get("lyrics") or row.get("lyrics") or "",
        "copyright": blob.get("copyright") or row.get("copyright") or "",
        "source": blob.get("source") or row.get("source") or "",
        "dateAdded": blob.get("dateAdded") or blob.get("date_added") or row.get("date_added") or "",
        "createdAt": _ts(row.get("created_at")),
    }


def _supabase_storage_url(storage_path: str) -> str:
    """Return the Supabase Storage public URL for *storage_path*.

    Uses ``SUPABASE_URL`` from the environment.  Returns an empty string when
    ``SUPABASE_URL`` is unset (e.g. in desktop mode or tests).
    """
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if not supabase_url or not storage_path:
        return ""
    return f"{supabase_url}/storage/v1/object/public/{storage_path}"


def _supabase_storage_upload(storage_path: str, data: bytes, mime_type: str) -> str:
    """Upload *data* to Supabase Storage at *storage_path*.

    Requires ``SUPABASE_URL`` and ``SUPABASE_SERVICE_ROLE_KEY`` in the
    environment.  Uses the REST API with a service-role Bearer token so the
    upload is not gated by Storage RLS policies (which are enforced at the DB
    level separately).

    Returns the public URL of the uploaded object.

    Raises RuntimeError when env vars are missing or the upload fails.
    """
    import urllib.request as _urllib_request  # noqa: PLC0415

    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url:
        raise RuntimeError("SUPABASE_URL is not set — cannot upload to Storage.")
    if not service_role_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is not set — cannot upload to Storage."
        )

    # Supabase Storage REST endpoint:
    # PUT /storage/v1/object/<bucket>/<path>  with upsert=true header
    api_url = f"{supabase_url}/storage/v1/object/{storage_path}"
    req = _urllib_request.Request(
        api_url,
        data=data,
        method="POST",
    )
    req.add_header("Authorization", f"Bearer {service_role_key}")
    req.add_header("Content-Type", mime_type)
    req.add_header("x-upsert", "true")

    try:
        with _urllib_request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(
                    f"Storage upload returned HTTP {resp.status} for {storage_path}"
                )
    except Exception as exc:
        raise RuntimeError(f"Storage upload failed for {storage_path}: {exc}") from exc

    return _supabase_storage_url(storage_path)


def _supabase_storage_delete(storage_path: str) -> None:
    """Delete an object from Supabase Storage.

    Uses the REST API ``DELETE /storage/v1/object/<path>`` with a service-role
    Bearer token.  Raises RuntimeError on failure (caller decides whether to
    propagate or log-and-continue).
    """
    import json as _json  # noqa: PLC0415
    import urllib.request as _urllib_request  # noqa: PLC0415

    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for Storage delete."
        )

    # Supabase Storage bulk-delete endpoint:
    # DELETE /storage/v1/object/<bucket>  body: {"prefixes": ["<relative-path>"]}
    # storage_path is "<bucket>/<relative-path>"; split on first slash.
    parts = storage_path.split("/", 1)
    if len(parts) != 2:
        raise RuntimeError(f"Invalid storage_path for delete: {storage_path!r}")
    bucket, relative_path = parts
    api_url = f"{supabase_url}/storage/v1/object/{bucket}"
    body = _json.dumps({"prefixes": [relative_path]}).encode("utf-8")
    req = _urllib_request.Request(api_url, data=body, method="DELETE")
    req.add_header("Authorization", f"Bearer {service_role_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with _urllib_request.urlopen(req, timeout=15):
            pass
    except Exception as exc:
        raise RuntimeError(f"Storage delete failed for {storage_path}: {exc}") from exc


def _pg_row_to_font(row: dict) -> dict:
    """Convert a raw Postgres fonts row dict into a font metadata dict.

    New schema columns: id, workspace_id, name, storage_path, mime_type, created_at.
    No slug/family/source/css_url/upload_metadata/cached_at in the new schema.

    We map ``name`` → ``slug`` and ``name`` → ``family`` as best-effort for
    backward compatibility with frontend consumers that expect these keys.
    The ``storage_path`` is surfaced as ``file_path`` for the same reason.
    Adds a ``url`` key — the Supabase Storage public URL (empty string when
    ``SUPABASE_URL`` is unset or storage_path is absent).
    """
    # Support both old and new column shapes.
    name = row.get("name") or ""
    slug = row.get("slug") or name
    family = row.get("family") or name
    storage_path = row.get("storage_path") or row.get("file_path") or ""
    return {
        "id": str(row["id"]),
        "name": name,
        "slug": slug,
        "family": family,
        "source": row.get("source") or "user",
        "url": _supabase_storage_url(storage_path),
        "css_url": row.get("css_url") or "",
        "file_path": row.get("file_path") or storage_path,
        "storage_path": storage_path,
        "mime_type": row.get("mime_type") or "",
        "upload_metadata": {},
        "cached_at": _ts(row.get("cached_at")),
        "created_at": _ts(row.get("created_at")),
    }


def _ts(value) -> str:
    """Convert a datetime (or string) to ISO-8601 string."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------------------
# Project access control helpers
# ---------------------------------------------------------------------------

def can_read_project(project: dict, user_id: str) -> bool:
    """Return True if *user_id* may read *project*.

    Rules:
      - workspace projects  → visible to all authenticated users
      - private + owned     → visible to the owner only
      - private + no owner  → legacy import, accessible to all (for now)
    """
    visibility = project.get("visibility") or "private"
    owner = project.get("owner_user_id")
    if visibility == "workspace":
        return True
    # private
    if owner is None:
        return True  # legacy import — no owner assigned yet
    return str(owner) == str(user_id)


def can_write_project(project: dict, user_id: str) -> bool:
    """Return True if *user_id* may save (update) *project*.

    Write access mirrors read access: all workspace users may edit workspace
    projects; only the owner may edit their private project.
    """
    return can_read_project(project, user_id)


def can_delete_project(project: dict, user_id: str) -> bool:
    """Return True if *user_id* may delete *project*.

    Rules:
      - owner == user_id  → True
      - owner is None (legacy, no owner assigned) → False (disable until admin role exists)
      - else              → False
    """
    owner = project.get("owner_user_id")
    if owner is None:
        return False  # ownerless legacy project — disable delete
    return str(owner) == str(user_id)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_storage(
    data_dir: Path | None = None,
    *,
    workspace_id: str | None = None,
    user_claims: dict | None = None,
) -> StorageBackend:
    """Return the appropriate storage backend for the current APP_MODE.

    ``data_dir`` is required when ``APP_MODE=desktop`` (or when the default
    desktop data directory cannot be inferred).  If omitted the factory reads
    ``DATA_DIR`` from the environment / standard platform paths to match
    server.py behaviour.

    When ``APP_MODE=server`` a ``PostgresStorageBackend`` is returned. Supplying
    ``workspace_id`` and ``user_claims`` scopes queries to the authenticated
    request and lets Postgres RLS see the verified Supabase JWT claims.
    """
    app_mode = os.environ.get("APP_MODE", "desktop").strip().lower()
    is_desktop = app_mode == "desktop"

    if is_desktop:
        if data_dir is None:
            import sys
            import platform
            if getattr(sys, "frozen", False):
                if platform.system() == "Darwin":
                    data_dir = Path.home() / "Library" / "Application Support" / "BulletinGenerator"
                elif platform.system() == "Windows":
                    data_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "BulletinGenerator"
                else:
                    data_dir = Path.home() / ".bulletin-generator"
            else:
                data_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "data"
        return JsonStorageBackend(Path(data_dir))

    return PostgresStorageBackend(workspace_id=workspace_id, user_claims=user_claims)
