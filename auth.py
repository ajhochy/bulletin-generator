"""
auth.py — Supabase Auth verification helpers.

Server mode trusts only Supabase access tokens supplied as
``Authorization: Bearer <token>``. The token is verified server-side before any
workspace membership lookup or RLS claims plumbing happens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _decode_json_segment(value: str) -> dict[str, Any]:
    decoded = _b64url_decode(value)
    payload = json.loads(decoded.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JWT segment is not a JSON object")
    return payload


def _verify_supabase_jwt(token: str) -> dict[str, Any] | None:
    """Return verified Supabase JWT claims, or None for invalid/expired tokens.

    Supabase project JWTs are HS256-signed with the project's JWT Secret
    (Dashboard -> Settings -> API -> JWT Secret). This secret is server-side
    only and must not be exposed to frontend or Electron code.
    """
    secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    if not secret or not token:
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, signature_b64 = parts
    try:
        header = _decode_json_segment(header_b64)
        claims = _decode_json_segment(payload_b64)
        signature = _b64url_decode(signature_b64)
    except Exception:
        return None

    if header.get("alg") != "HS256":
        return None

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None

    exp = claims.get("exp")
    if exp is None:
        return None
    try:
        if int(exp) <= int(time.time()):
            return None
    except (TypeError, ValueError):
        return None

    if not claims.get("sub"):
        return None

    return claims


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """Extract the Bearer token from an Authorization header."""
    if not authorization_header:
        return None
    scheme, _, token = authorization_header.strip().partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def resolve_workspace_membership(user_id: str) -> dict[str, str] | None:
    """Resolve the user's first active workspace membership.

    This intentionally uses ``db.admin_transaction()``. Membership resolution is
    part of the server-side trust boundary that determines which RLS claims and
    workspace scope to use; it cannot depend on user-scoped RLS yet.
    """
    from db import admin_transaction  # noqa: PLC0415

    with admin_transaction() as conn:
        row = conn.execute(
            """
            SELECT wm.workspace_id, wm.role, p.email, p.display_name, p.avatar_url
            FROM public.workspace_members wm
            LEFT JOIN public.profiles p ON p.id = wm.user_id
            WHERE wm.user_id = %s::uuid
            ORDER BY wm.created_at ASC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "workspace_id": str(row[0]),
        "role": str(row[1] or ""),
        "email": row[2] or "",
        "display_name": row[3] or "",
        "avatar_url": row[4] or "",
    }


def authenticate_authorization_header(authorization_header: str | None) -> tuple[int, dict[str, Any] | None]:
    """Verify Authorization header and resolve workspace membership.

    Returns ``(200, identity)`` on success, ``(401, None)`` for missing/invalid
    tokens, and ``(403, None)`` when the token is valid but the user has no
    workspace membership.
    """
    token = extract_bearer_token(authorization_header)
    claims = _verify_supabase_jwt(token or "")
    if claims is None:
        return 401, None

    user_id = str(claims["sub"])
    membership = resolve_workspace_membership(user_id)
    if membership is None:
        return 403, None

    identity = {
        "id": user_id,
        "user_id": user_id,
        "email": claims.get("email") or membership.get("email") or "",
        "display_name": (
            claims.get("user_metadata", {}).get("full_name")
            if isinstance(claims.get("user_metadata"), dict)
            else None
        ) or membership.get("display_name") or "",
        "avatar_url": (
            claims.get("user_metadata", {}).get("avatar_url")
            if isinstance(claims.get("user_metadata"), dict)
            else None
        ) or membership.get("avatar_url") or "",
        "workspace_id": membership["workspace_id"],
        "role": membership["role"],
        "claims": claims,
    }
    return 200, identity


def get_request_user(_cookie_header: str) -> dict[str, Any] | None:
    """Legacy collab-v1 cookie auth is disabled on this branch.

    The symbol remains so older tests can patch it, but production request auth
    no longer calls this function.
    """
    if os.environ.get("ENABLE_LEGACY_COOKIE_AUTH") == "1":
        raise RuntimeError("Legacy cookie auth is not supported on the Supabase branch.")
    return None
