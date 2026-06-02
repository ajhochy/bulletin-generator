from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import auth  # noqa: E402


SECRET = "unit-test-secret"
USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token(claims: dict, secret: str = SECRET, header: dict | None = None) -> str:
    header = header or {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(sig)}"


def _claims(**overrides):
    base = {
        "sub": USER_ID,
        "email": "alice@example.com",
        "exp": int(time.time()) + 3600,
        "role": "authenticated",
        "aud": "authenticated",
    }
    base.update(overrides)
    return base


class TestVerifySupabaseJwt:
    def test_valid_hs256_token_returns_claims(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
        claims = auth._verify_supabase_jwt(_token(_claims()))
        assert claims["sub"] == USER_ID
        assert claims["email"] == "alice@example.com"

    def test_invalid_signature_returns_none(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
        token = _token(_claims(), secret="wrong-secret")
        assert auth._verify_supabase_jwt(token) is None

    def test_expired_token_returns_none(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
        token = _token(_claims(exp=int(time.time()) - 1))
        assert auth._verify_supabase_jwt(token) is None

    def test_missing_secret_returns_none(self, monkeypatch):
        monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
        assert auth._verify_supabase_jwt(_token(_claims())) is None

    def test_non_hs256_returns_none(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
        token = _token(_claims(), header={"alg": "none"})
        assert auth._verify_supabase_jwt(token) is None


class TestAuthenticateAuthorizationHeader:
    def test_valid_token_with_membership_returns_identity(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
        token = _token(_claims())
        membership = {
            "workspace_id": "bbbbbbbb-0000-0000-0000-000000000001",
            "role": "admin",
            "email": "profile@example.com",
            "display_name": "Profile Name",
            "avatar_url": "",
        }
        with patch("auth.resolve_workspace_membership", return_value=membership):
            status, identity = auth.authenticate_authorization_header(f"Bearer {token}")
        assert status == 200
        assert identity["id"] == USER_ID
        assert identity["workspace_id"] == membership["workspace_id"]
        assert identity["role"] == "admin"
        assert identity["claims"]["sub"] == USER_ID

    def test_valid_token_without_membership_returns_403(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
        token = _token(_claims())
        with patch("auth.resolve_workspace_membership", return_value=None):
            status, identity = auth.authenticate_authorization_header(f"Bearer {token}")
        assert status == 403
        assert identity is None

    def test_invalid_token_returns_401_without_membership_lookup(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
        with patch("auth.resolve_workspace_membership", MagicMock()) as membership:
            status, identity = auth.authenticate_authorization_header("Bearer invalid")
        assert status == 401
        assert identity is None
        membership.assert_not_called()
