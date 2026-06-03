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
import urllib.request
from typing import Any

# Cached EC public keys keyed by kid, populated lazily from the JWKS endpoint.
_ec_key_cache: dict[str, Any] = {}


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _decode_json_segment(value: str) -> dict[str, Any]:
    decoded = _b64url_decode(value)
    payload = json.loads(decoded.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JWT segment is not a JSON object")
    return payload


def _b64url_to_int(value: str) -> int:
    return int.from_bytes(_b64url_decode(value), "big")


def _load_ec_keys() -> None:
    """Fetch JWKS from Supabase and populate _ec_key_cache."""
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if not supabase_url:
        return
    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        with urllib.request.urlopen(jwks_url, timeout=5) as resp:
            jwks = json.loads(resp.read().decode("utf-8"))
        for key in jwks.get("keys", []):
            if key.get("kty") == "EC" and key.get("alg") == "ES256":
                kid = key.get("kid", "default")
                _ec_key_cache[kid] = key
    except Exception:
        pass


def _get_ec_public_key(kid: str) -> Any:
    """Return a cryptography EC public key object for the given kid."""
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePublicNumbers,
        SECP256R1,
    )

    if not _ec_key_cache:
        _load_ec_keys()

    # Try exact kid match, then fall back to first available key.
    jwk = _ec_key_cache.get(kid) or (next(iter(_ec_key_cache.values())) if _ec_key_cache else None)
    if jwk is None:
        return None

    x = _b64url_to_int(jwk["x"])
    y = _b64url_to_int(jwk["y"])
    return EllipticCurvePublicNumbers(x, y, SECP256R1()).public_key()


def _verify_es256(header_b64: str, payload_b64: str, signature: bytes, kid: str) -> bool:
    """Verify an ES256 JWT signature using the Supabase JWKS public key."""
    from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidSignature

    public_key = _get_ec_public_key(kid)
    if public_key is None:
        return False

    # JWT ES256 signatures are P1363 format (r||s, 32 bytes each).
    # cryptography.verify() expects DER.
    if len(signature) != 64:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    der_sig = encode_dss_signature(r, s)

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    try:
        public_key.verify(der_sig, signing_input, ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def _verify_supabase_jwt(token: str) -> dict[str, Any] | None:
    """Return verified Supabase JWT claims, or None for invalid/expired tokens.

    Supports HS256 (legacy/self-hosted) and ES256 (new Supabase projects).
    HS256: verified with SUPABASE_JWT_SECRET.
    ES256: verified via JWKS public key fetched from SUPABASE_URL.
    """
    if not token:
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

    alg = header.get("alg")
    kid = header.get("kid", "default")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    if alg == "HS256":
        secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
        if not secret:
            return None
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
    elif alg == "ES256":
        if not _verify_es256(header_b64, payload_b64, signature, kid):
            return None
    else:
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
