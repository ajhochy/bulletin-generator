"""
storage_assets.py — Supabase Storage upload helpers for cover/logo images.

Extracts base64-encoded cover/logo images from a project dict, uploads them
to the ``project-assets`` Supabase Storage bucket, and returns the public
Storage URLs.

Usage (server mode only):
    from storage_assets import extract_and_upload_images
    project = extract_and_upload_images(project, workspace_id, project_id)

Desktop mode (no SUPABASE_SERVICE_ROLE_KEY configured):
    extract_and_upload_images is a no-op and returns the project unchanged.

Failure behaviour:
    If any upload fails (network error, auth, etc.) the original base64 value is
    preserved in the project dict.  We never lose an image because of a failed
    upload.

Bucket:         project-assets
Object path:    <workspace_id>/<project_id>-cover.<ext>
                <workspace_id>/<project_id>-logo.<ext>
Public URL:     <SUPABASE_URL>/storage/v1/object/public/project-assets/<path>
Auth:           Bearer <SUPABASE_SERVICE_ROLE_KEY>  (service role bypasses Storage RLS)
"""

from __future__ import annotations

import base64
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

_BUCKET = "project-assets"

# Image keys inside the project dict that hold base64 data URIs.
_IMAGE_KEYS = (
    ("coverImageUrl", "cover"),
    ("staffLogoUrl",  "logo"),
)


def _supabase_url() -> str:
    """Return the base Supabase REST URL, or '' if unset."""
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def _service_role_key() -> str:
    """Return the Supabase service role JWT (HTTP key), or '' if unset."""
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def is_base64_data_uri(value: object) -> bool:
    """Return True when *value* is a data URI with a base64 payload."""
    if not isinstance(value, str):
        return False
    return value.startswith("data:") and ";base64," in value


def _parse_data_uri(data_uri: str) -> tuple[bytes, str, str]:
    """Parse a data URI and return (binary_data, mime_type, file_extension).

    Raises ValueError for malformed URIs.
    """
    try:
        header, b64 = data_uri.split(";base64,", 1)
        mime = header.split("data:", 1)[1]
        data = base64.b64decode(b64)
    except Exception as exc:
        raise ValueError(f"malformed data URI: {exc}") from exc

    # Derive a file extension from the MIME type.
    _EXT_MAP = {
        "image/jpeg":   "jpg",
        "image/jpg":    "jpg",
        "image/png":    "png",
        "image/gif":    "gif",
        "image/webp":   "webp",
        "image/svg+xml": "svg",
        "image/bmp":    "bmp",
    }
    ext = _EXT_MAP.get(mime.lower(), "bin")
    return data, mime, ext


def upload_image(
    data: bytes,
    mime: str,
    object_path: str,
    *,
    supabase_url: Optional[str] = None,
    service_role_key: Optional[str] = None,
) -> str:
    """Upload *data* to Supabase Storage at *object_path* in the project-assets bucket.

    Returns the public URL of the uploaded object.

    Raises:
        RuntimeError       — if SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY are unset.
        urllib.error.URLError — on network failure (caller should catch and fallback).
    """
    url = supabase_url or _supabase_url()
    key = service_role_key or _service_role_key()

    if not url:
        raise RuntimeError("SUPABASE_URL is not configured; cannot upload to Storage.")
    if not key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is not configured; cannot upload to Storage."
        )

    upload_url = f"{url}/storage/v1/object/{_BUCKET}/{object_path}"
    req = urllib.request.Request(
        upload_url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": mime,
            "x-upsert": "true",          # replace if the object already exists
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()  # consume response body

    public_url = f"{url}/storage/v1/object/public/{_BUCKET}/{object_path}"
    return public_url


def extract_and_upload_images(
    project: dict,
    workspace_id: str,
    project_id: str,
    *,
    supabase_url: Optional[str] = None,
    service_role_key: Optional[str] = None,
) -> dict:
    """Replace base64 data URIs in *project* with Supabase Storage URLs.

    For each image key (coverImageUrl, staffLogoUrl):
      - If the value is a base64 data URI → upload to Storage, replace with URL.
      - If the upload fails → keep the original base64 (fallback; log a warning).
      - If the value is already a URL or None → leave unchanged.

    Desktop mode (SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set):
        Returns the project dict unchanged — no uploads attempted.

    Mutates and returns the *project* dict.
    """
    url = supabase_url or _supabase_url()
    key = service_role_key or _service_role_key()

    # Desktop mode or Storage not configured: bypass entirely.
    if not url or not key:
        return project

    for field_key, asset_name in _IMAGE_KEYS:
        value = project.get(field_key)
        if not is_base64_data_uri(value):
            continue  # already a URL, None, or empty — nothing to do

        try:
            data, mime, ext = _parse_data_uri(value)
        except ValueError as exc:
            logger.warning(
                "storage_assets: could not parse data URI for %s: %s", field_key, exc
            )
            continue  # keep base64

        object_path = f"{workspace_id}/{project_id}-{asset_name}.{ext}"

        try:
            public_url = upload_image(
                data, mime, object_path,
                supabase_url=url,
                service_role_key=key,
            )
            project[field_key] = public_url
            logger.info(
                "storage_assets: uploaded %s for project %s → %s",
                field_key, project_id, public_url,
            )
        except Exception as exc:
            # Upload failed — keep the base64 so the image is not lost.
            logger.warning(
                "storage_assets: upload failed for %s (project %s); keeping base64. Error: %s",
                field_key, project_id, exc,
            )

    return project
