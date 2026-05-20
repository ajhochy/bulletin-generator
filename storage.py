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
    def list_projects(self) -> list:
        """Return the full list of project dicts."""
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

    @abstractmethod
    def delete_project(self, project_id: str) -> bool:
        """Delete a project by id.  Returns True if it existed."""
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

    def list_projects(self) -> list:
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


# ---------------------------------------------------------------------------
# Postgres stub (server mode — filled in by issues #196-#201)
# ---------------------------------------------------------------------------

class PostgresStorageBackend(StorageBackend):
    """Postgres-backed storage for multi-user server deployments.

    Project methods are fully implemented.  All other methods raise
    ``NotImplementedError`` until the remaining issues (#197-#201) land.
    """

    # ── Projects ──────────────────────────────────────────────────────────────

    def list_projects(self) -> list:
        """Return all projects ordered by updated_at DESC."""
        from db import transaction, from_jsonb  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, name, owner_user_id, visibility, state, revision,
                       created_at, updated_at, created_by_email, updated_by_email,
                       imported_from_json
                FROM projects
                ORDER BY updated_at DESC
                """
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [_pg_row_to_project(dict(zip(cols, row))) for row in rows]

    def get_project(self, project_id: str) -> dict | None:
        """Return a single project dict by id, or None if not found."""
        from db import transaction  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, name, owner_user_id, visibility, state, revision,
                       created_at, updated_at, created_by_email, updated_by_email,
                       imported_from_json
                FROM projects
                WHERE id = %s::uuid
                """,
                (project_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cursor.description]
        return _pg_row_to_project(dict(zip(cols, row)))

    def save_project(self, data: dict, *, updated_by_email: str = "", updated_by_user_id: str | None = None) -> dict:
        """Upsert a project and return the persisted dict.

        * On INSERT  — revision defaults to 1; owner_user_id set from ``updated_by_user_id``.
        * On UPDATE  — revision is incremented by 1; updated_by_email set from caller.
        ``data`` must contain an ``id`` key (UUID string).

        ``updated_by_email`` and ``updated_by_user_id`` are caller-supplied attribution
        values that override any values embedded in ``data``.
        """
        if "id" not in data:
            raise ValueError("project data must contain an 'id' key")

        import json as _json  # noqa: PLC0415
        from db import transaction  # noqa: PLC0415

        project_id = data["id"]
        name = str(data.get("name") or "")
        state_json = _json.dumps(data, ensure_ascii=False)
        created_by_email = str(data.get("createdBy") or "")
        # Caller-supplied attribution takes precedence over data payload.
        resolved_updated_by_email = updated_by_email or str(data.get("updatedBy") or "")
        created_at = data.get("createdAt") or None
        updated_at = data.get("updatedAt") or None

        with transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (
                    id, name, owner_user_id, visibility, state, revision,
                    created_at, updated_at, created_by_email, updated_by_email,
                    imported_from_json
                ) VALUES (
                    %(id)s::uuid, %(name)s,
                    %(owner_user_id)s::uuid,
                    'private', %(state)s::jsonb, 1,
                    COALESCE(%(created_at)s::timestamptz, now()),
                    now(),
                    %(created_by_email)s, %(updated_by_email)s, FALSE
                )
                ON CONFLICT (id) DO UPDATE SET
                    name             = EXCLUDED.name,
                    state            = EXCLUDED.state,
                    revision         = projects.revision + 1,
                    updated_at       = now(),
                    updated_by_email = EXCLUDED.updated_by_email
                RETURNING id, name, owner_user_id, visibility, state, revision,
                          created_at, updated_at, created_by_email, updated_by_email,
                          imported_from_json
                """,
                {
                    "id": project_id,
                    "name": name,
                    "owner_user_id": updated_by_user_id,
                    "state": state_json,
                    "created_at": created_at,
                    "updated_by_email": resolved_updated_by_email,
                    "created_by_email": created_by_email or resolved_updated_by_email,
                },
            )
            row = cursor.fetchone()
            cols = [d[0] for d in cursor.description]
        return _pg_row_to_project(dict(zip(cols, row)))

    def delete_project(self, project_id: str) -> bool:
        """Delete a project by id; return True if it existed."""
        from db import transaction  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM projects WHERE id = %s::uuid",
                (project_id,),
            )
        return cursor.rowcount == 1

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        """Read all org_settings rows and reconstruct a flat settings dict.

        OAuth tokens stored under the ``"oauth_tokens"`` key are unpacked back
        into top-level keys (pcoAccessToken, pcoRefreshToken, etc.) so callers
        receive the same flat shape as the legacy settings.json.

        User-level keys (e.g. editorDisplayName) are not yet included because
        the user_settings table requires a known user_id — those will be added
        once per-user identity is wired in.
        """
        from db import transaction, from_jsonb  # noqa: PLC0415

        with transaction() as conn:
            cursor = conn.execute("SELECT key, value FROM org_settings")
            rows = cursor.fetchall()

        result: dict = {}
        for key, value in rows:
            parsed = from_jsonb(value)
            if key == "oauth_tokens" and isinstance(parsed, dict):
                # Unpack OAuth bundle back to top-level keys for backward compat.
                result.update(parsed)
            else:
                result[key] = parsed

        return result

    def save_settings(self, data: dict) -> dict:
        """Persist recognised settings keys into org_settings (and user_settings
        for user-level keys in a future release).

        Each org key is upserted individually.  OAuth tokens are re-bundled
        under the ``"oauth_tokens"`` key.  Unknown keys are ignored.

        Returns the full flat settings dict as reconstructed by get_settings().
        """
        from db import transaction  # noqa: PLC0415
        from migrations.import_settings import ORG_KEYS, OAUTH_KEYS  # noqa: PLC0415

        with transaction() as conn:
            # Upsert individual org keys.
            for key in ORG_KEYS:
                if key in data:
                    _pg_upsert_org_setting(conn, key, data[key])

            # Bundle OAuth tokens under a single row.
            oauth_bundle = {k: data[k] for k in OAUTH_KEYS if k in data}
            if oauth_bundle:
                # Merge with any existing oauth_tokens to preserve tokens not
                # present in the incoming payload.
                cursor = conn.execute(
                    "SELECT value FROM org_settings WHERE key = 'oauth_tokens'"
                )
                row = cursor.fetchone()
                from db import from_jsonb  # noqa: PLC0415
                existing: dict = from_jsonb(row[0]) if row else {}
                if not isinstance(existing, dict):
                    existing = {}
                existing.update(oauth_bundle)
                _pg_upsert_org_setting(conn, "oauth_tokens", existing)

        return self.get_settings()

    # ── Announcements ─────────────────────────────────────────────────────────

    def list_announcements(self) -> list:
        """Return all announcements ordered by ordering ASC."""
        from db import transaction  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, title, body, url, ordering
                FROM announcements
                ORDER BY ordering ASC
                """
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in rows]

    def save_announcements(self, data: list) -> list:
        """Replace all announcements: DELETE then INSERT in a single transaction.

        Each item in *data* must be a dict with at least a ``title`` key.
        An ``id`` (UUID string) is required; callers should ensure items
        carry valid UUIDs before persisting.  ``url`` and ``ordering`` are
        optional and default to ``''`` / list-index respectively.

        Returns the saved list as read back from the database.
        """
        import json as _json  # noqa: PLC0415
        import uuid as _uuid  # noqa: PLC0415
        from db import transaction  # noqa: PLC0415

        _ANN_NAMESPACE = _uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

        with transaction() as conn:
            conn.execute("DELETE FROM announcements")
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "")
                body = str(item.get("body") or "")
                url = str(item.get("url") or "")
                ordering = int(
                    item.get("ordering") if item.get("ordering") is not None else idx
                )
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

                conn.execute(
                    """
                    INSERT INTO announcements (id, title, body, url, ordering)
                    VALUES (%(id)s::uuid, %(title)s, %(body)s, %(url)s, %(ordering)s)
                    ON CONFLICT (id) DO UPDATE SET
                        title    = EXCLUDED.title,
                        body     = EXCLUDED.body,
                        url      = EXCLUDED.url,
                        ordering = EXCLUDED.ordering,
                        updated_at = now()
                    """,
                    {
                        "id": ann_id,
                        "title": title,
                        "body": body,
                        "url": url,
                        "ordering": ordering,
                    },
                )

        return self.list_announcements()

    # ── Songs ─────────────────────────────────────────────────────────────────

    def list_songs(self) -> list:
        """Return all songs ordered by title ASC."""
        from db import transaction  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, title, author, lyrics, copyright, source, date_added, created_at
                FROM songs
                ORDER BY title ASC
                """
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [_pg_row_to_song(dict(zip(cols, row))) for row in rows]

    def save_songs(self, data: list) -> list:
        """Upsert each song in *data* individually; never deletes existing rows.

        Each item must be a dict.  An ``id`` is required; if the raw id is not a
        valid UUID a stable UUID5 is generated from title+author+source.

        Returns the full songs list as read back from the database (title ASC).
        """
        import uuid as _uuid  # noqa: PLC0415
        from db import transaction  # noqa: PLC0415

        _SONG_NAMESPACE = _uuid.UUID("c0ffee00-d400-4db0-0000-000000000000")

        with transaction() as conn:
            for item in data:
                if not isinstance(item, dict):
                    continue

                title = str(item.get("title") or "")
                author = str(item.get("author") or "")
                lyrics = str(item.get("lyrics") or "")
                copyright_ = str(item.get("copyright") or "")
                source = str(item.get("source") or "")
                date_added = str(
                    item.get("dateAdded") or item.get("date_added") or ""
                )

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

                conn.execute(
                    """
                    INSERT INTO songs (
                        id, title, author, lyrics, copyright, source, date_added
                    ) VALUES (
                        %(id)s::uuid, %(title)s, %(author)s, %(lyrics)s,
                        %(copyright)s, %(source)s, %(date_added)s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        title      = EXCLUDED.title,
                        author     = EXCLUDED.author,
                        lyrics     = EXCLUDED.lyrics,
                        copyright  = EXCLUDED.copyright,
                        source     = EXCLUDED.source,
                        date_added = EXCLUDED.date_added,
                        updated_at = now()
                    """,
                    {
                        "id": song_id,
                        "title": title,
                        "author": author,
                        "lyrics": lyrics,
                        "copyright": copyright_,
                        "source": source,
                        "date_added": date_added,
                    },
                )

        return self.list_songs()

    # ── Templates ─────────────────────────────────────────────────────────────

    def list_templates(self) -> list:
        """Return all templates ordered by built_in DESC, name ASC.

        Each returned dict has keys: id, name, data, built_in.
        The ``data`` column holds the full template JSONB object.
        """
        from db import transaction, from_jsonb  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, name, data, built_in
                FROM templates
                ORDER BY built_in DESC, name ASC
                """
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [_pg_row_to_template(dict(zip(cols, row))) for row in rows]

    def save_templates(self, data: list) -> list:
        """Upsert each custom template in *data*; built-in templates are never modified.

        For each item in *data*:
        * If ``built_in`` is True → skip silently (protected).
        * Otherwise → upsert (INSERT ... ON CONFLICT (id) DO UPDATE SET name, data).

        An ``id`` is required on each item; if the raw id is not a valid UUID
        a stable UUID5 is generated from the template name.

        Returns the full templates list as read back from the database
        (built_in DESC, name ASC).
        """
        import json as _json  # noqa: PLC0415
        import uuid as _uuid  # noqa: PLC0415
        from db import transaction  # noqa: PLC0415

        _TEMPLATE_NAMESPACE = _uuid.UUID("b01e7e00-7e00-4000-8000-000000000000")

        with transaction() as conn:
            for item in data:
                if not isinstance(item, dict):
                    continue

                # Built-in templates are protected — never update them.
                if item.get("built_in") or item.get("builtIn"):
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
                    INSERT INTO templates (id, name, data, built_in)
                    VALUES (%(id)s::uuid, %(name)s, %(data)s::jsonb, FALSE)
                    ON CONFLICT (id) DO UPDATE SET
                        name       = EXCLUDED.name,
                        data       = EXCLUDED.data,
                        updated_at = now()
                    WHERE NOT templates.built_in
                    """,
                    {
                        "id": template_id,
                        "name": name,
                        "data": data_json,
                    },
                )

        return self.list_templates()

    # ── Fonts ──────────────────────────────────────────────────────────────────

    def list_fonts(self) -> list:
        """Return all fonts ordered by family ASC."""
        from db import transaction, from_jsonb  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, slug, family, source, css_url, file_path,
                       upload_metadata, cached_at, created_at
                FROM fonts
                ORDER BY family ASC
                """
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
        return [_pg_row_to_font(dict(zip(cols, row))) for row in rows]

    def get_font(self, slug: str) -> "dict | None":
        """Return a single font metadata dict by slug, or None if not found."""
        from db import transaction  # noqa: PLC0415
        with transaction() as conn:
            cursor = conn.execute(
                """
                SELECT id, slug, family, source, css_url, file_path,
                       upload_metadata, cached_at, created_at
                FROM fonts
                WHERE slug = %s
                """,
                (slug,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cursor.description]
        return _pg_row_to_font(dict(zip(cols, row)))


# ---------------------------------------------------------------------------
# Postgres settings helper
# ---------------------------------------------------------------------------

def _pg_upsert_org_setting(conn, key: str, value) -> None:
    """Upsert a single org_settings row (INSERT ... ON CONFLICT DO UPDATE)."""
    import json as _json  # noqa: PLC0415

    conn.execute(
        """
        INSERT INTO org_settings (key, value, updated_at)
        VALUES (%(key)s, %(value)s::jsonb, now())
        ON CONFLICT (key) DO UPDATE SET
            value      = EXCLUDED.value,
            updated_at = now()
        """,
        {"key": key, "value": _json.dumps(value, ensure_ascii=False)},
    )


# ---------------------------------------------------------------------------
# Postgres row → project dict helper
# ---------------------------------------------------------------------------

def _pg_row_to_project(row: dict) -> dict:
    """Convert a raw Postgres row dict into the project dict shape expected by the frontend.

    The ``state`` column holds the full project payload as JSONB.  We return
    that payload merged with DB-authoritative fields so callers can trust those
    keys even if the stored state blob is missing them.

    Metadata fields included (all top-level):
      - id, name, revision  (always present)
      - visibility           ("private" or "workspace")
      - owner_user_id        (UUID string or None)
      - owner_email          (created_by_email, may be None for legacy imports)
      - created_at, updated_at (ISO-8601 strings)
      - created_by_email, updated_by_email
      - imported_from_json   (bool)
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
    state["owner_email"] = row.get("created_by_email") or None
    state["visibility"] = row.get("visibility") or "workspace"
    state["imported_from_json"] = bool(row.get("imported_from_json"))

    # ── Timestamps & attribution (snake_case for API consumers) ───────────────
    state["created_at"] = _ts(row.get("created_at")) or None
    state["updated_at"] = _ts(row.get("updated_at")) or None
    state["created_by_email"] = row.get("created_by_email") or None
    state["updated_by_email"] = row.get("updated_by_email") or None

    # ── Legacy camelCase keys for frontend backward compatibility ─────────────
    if row.get("created_at"):
        state.setdefault("createdAt", _ts(row["created_at"]))
    if row.get("updated_at"):
        state["updatedAt"] = _ts(row["updated_at"])
    if row.get("created_by_email"):
        state.setdefault("createdBy", row["created_by_email"])
    if row.get("updated_by_email"):
        state["updatedBy"] = row["updated_by_email"]

    return state


def _pg_row_to_template(row: dict) -> dict:
    """Convert a raw Postgres templates row dict into the shape expected by the frontend.

    The ``data`` column holds the full template payload as JSONB.  We return
    that payload merged with the DB-authoritative fields (id, name, built_in)
    so callers can trust those keys even if the stored data blob differs.
    """
    from db import from_jsonb  # noqa: PLC0415

    data = from_jsonb(row.get("data")) or {}
    if not isinstance(data, dict):
        data = {}

    # Merge DB-authoritative fields on top of the stored data blob.
    data["id"] = str(row["id"])
    data["name"] = row.get("name") or data.get("name") or ""
    data["builtIn"] = bool(row.get("built_in"))

    return data


def _pg_row_to_song(row: dict) -> dict:
    """Convert a raw Postgres songs row dict into the shape expected by the frontend.

    Returns camelCase keys that match the legacy song_database.json format.
    """
    return {
        "id": str(row["id"]),
        "title": row.get("title") or "",
        "author": row.get("author") or "",
        "lyrics": row.get("lyrics") or "",
        "copyright": row.get("copyright") or "",
        "source": row.get("source") or "",
        "dateAdded": row.get("date_added") or "",
        "createdAt": _ts(row.get("created_at")),
    }


def _pg_row_to_font(row: dict) -> dict:
    """Convert a raw Postgres fonts row dict into a font metadata dict.

    Returns snake_case keys that match the fonts table columns and the
    dict shape used by ``scan_font_directory`` in ``migrations/import_fonts.py``.
    """
    from db import from_jsonb  # noqa: PLC0415

    return {
        "id": str(row["id"]),
        "slug": row.get("slug") or "",
        "family": row.get("family") or "",
        "source": row.get("source") or "",
        "css_url": row.get("css_url") or "",
        "file_path": row.get("file_path") or "",
        "upload_metadata": from_jsonb(row.get("upload_metadata")) or {},
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
# Factory
# ---------------------------------------------------------------------------

def get_storage(data_dir: Path | None = None) -> StorageBackend:
    """Return the appropriate storage backend for the current APP_MODE.

    ``data_dir`` is required when ``APP_MODE=desktop`` (or when the default
    desktop data directory cannot be inferred).  If omitted the factory reads
    ``DATA_DIR`` from the environment / standard platform paths to match
    server.py behaviour.

    When ``APP_MODE=server`` a ``PostgresStorageBackend`` is returned.
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

    return PostgresStorageBackend()
