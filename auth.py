"""
auth.py — Google app-login OAuth (identity only, separate from Calendar/Drive).

Provides a distinct Google OpenID Connect flow for authenticating users into
the app itself.  This is completely separate from the Calendar/Drive integration
OAuth stored in settings.json.

Routes (added in server.py):
    GET /auth/google/login    → redirect to Google's consent page
    GET /auth/google/callback → exchange code, upsert user, set session cookie

Environment variables (separate from GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
used by the Calendar/Drive flow — may point to the same OAuth client if desired):
    AUTH_GOOGLE_CLIENT_ID      — OAuth 2.0 client ID
    AUTH_GOOGLE_CLIENT_SECRET  — OAuth 2.0 client secret
    AUTH_GOOGLE_REDIRECT_URI   — e.g. http://localhost:8080/auth/google/callback
"""

import base64
import json
import os
import urllib.parse
import urllib.request

# ── Constants ─────────────────────────────────────────────────────────────────

AUTH_GOOGLE_LOGIN_SCOPES = ["openid", "email", "profile"]

ALLOWED_DOMAIN = os.environ.get("GOOGLE_WORKSPACE_DOMAIN", "visaliacrc.com")

_GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


# ── Domain validation ─────────────────────────────────────────────────────────

def validate_domain(email: str) -> bool:
    """
    Return True if the email's domain matches ALLOWED_DOMAIN.

    The check is case-insensitive and strips leading/trailing whitespace from
    the email before splitting.

    Args:
        email: An email address string (whitespace is stripped before checking).

    Returns:
        True if the domain part equals ALLOWED_DOMAIN (case-insensitive),
        False otherwise.
    """
    normalized = email.strip().lower()
    if "@" not in normalized:
        return False
    domain = normalized.split("@", 1)[1]
    return domain == ALLOWED_DOMAIN.lower()


# ── Authorization URL ─────────────────────────────────────────────────────────

def build_auth_login_url(state: str) -> str:
    """
    Build the Google OAuth authorization URL for app login.

    Uses AUTH_GOOGLE_CLIENT_ID and AUTH_GOOGLE_REDIRECT_URI env vars.
    Requests identity scopes only: openid, email, profile.

    Args:
        state: An opaque CSRF token that Google will echo back in the callback.

    Returns:
        The full URL to redirect the browser to.
    """
    client_id    = os.environ.get("AUTH_GOOGLE_CLIENT_ID", "").strip()
    redirect_uri = os.environ.get("AUTH_GOOGLE_REDIRECT_URI", "").strip()

    params = urllib.parse.urlencode({
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         " ".join(AUTH_GOOGLE_LOGIN_SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    })
    return f"{_GOOGLE_AUTH_URL}?{params}"


# ── Code exchange ─────────────────────────────────────────────────────────────

def exchange_auth_code(code: str) -> dict:
    """
    Exchange an authorization code for tokens and return the ID token claims.

    POSTs to Google's token endpoint using AUTH_GOOGLE_CLIENT_ID,
    AUTH_GOOGLE_CLIENT_SECRET, and AUTH_GOOGLE_REDIRECT_URI env vars.

    The ID token is a JWT; we decode the payload without signature verification
    because the token was received directly from Google's token endpoint over
    HTTPS, which provides the required trust.

    Args:
        code: The authorization code from the OAuth callback.

    Returns:
        A dict of ID token claims: {sub, email, name, picture, hd, ...}.

    Raises:
        ValueError: If the token exchange fails or the ID token is missing/malformed.
    """
    client_id     = os.environ.get("AUTH_GOOGLE_CLIENT_ID",     "").strip()
    client_secret = os.environ.get("AUTH_GOOGLE_CLIENT_SECRET", "").strip()
    redirect_uri  = os.environ.get("AUTH_GOOGLE_REDIRECT_URI",  "").strip()

    token_data = urllib.parse.urlencode({
        "grant_type":    "authorization_code",
        "code":          code,
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  redirect_uri,
    }).encode()

    req = urllib.request.Request(
        _GOOGLE_TOKEN_URL,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_resp = json.loads(resp.read())
    except Exception as exc:
        raise ValueError(f"Google token exchange request failed: {exc}") from exc

    id_token = token_resp.get("id_token", "").strip()
    if not id_token:
        raise ValueError("No id_token in Google token response.")

    claims = _decode_id_token_payload(id_token)
    return claims


def _decode_id_token_payload(id_token: str) -> dict:
    """
    Decode the payload segment of a JWT without verifying the signature.

    Safe to use here because the token was received directly from Google's
    token endpoint over a server-to-server HTTPS request.

    Args:
        id_token: A JWT string in the form header.payload.signature.

    Returns:
        The decoded claims dict.

    Raises:
        ValueError: If the JWT is malformed.
    """
    parts = id_token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed id_token: expected 3 JWT segments.")

    payload_b64 = parts[1]
    # Add padding required by base64 decoder
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding

    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception as exc:
        raise ValueError(f"Failed to decode id_token payload: {exc}") from exc


# ── User upsert ───────────────────────────────────────────────────────────────

def upsert_user(claims: dict) -> dict:
    """
    Create or update a user row from Google ID token claims.

    Extracts email, display_name (from 'name'), avatar_url (from 'picture'),
    and domain (the part after '@' in the email address).

    Uses INSERT ... ON CONFLICT (email) DO UPDATE to handle both new and
    returning users atomically.

    Args:
        claims: ID token claims dict as returned by exchange_auth_code().

    Returns:
        A dict with keys: id, email, display_name, avatar_url, domain.

    Raises:
        ValueError: If the claims dict is missing the required 'email' field.
        RuntimeError: If called in desktop mode (propagated from db.transaction).
    """
    email = (claims.get("email") or "").strip()
    if not email:
        raise ValueError("Google ID token claims are missing the 'email' field.")

    if not validate_domain(email):
        raise ValueError(f"Login restricted to @{ALLOWED_DOMAIN} accounts")

    display_name = (claims.get("name") or "").strip()
    avatar_url   = (claims.get("picture") or "").strip()
    domain       = email.split("@", 1)[1] if "@" in email else ""

    from db import transaction  # noqa: PLC0415  (deferred — db not available in desktop)

    with transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO users (email, display_name, avatar_url, domain)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    avatar_url   = EXCLUDED.avatar_url,
                    updated_at   = now()
            RETURNING id, email, display_name, avatar_url, domain
            """,
            (email, display_name, avatar_url, domain),
        ).fetchone()

    return {
        "id":           str(row[0]),
        "email":        row[1],
        "display_name": row[2],
        "avatar_url":   row[3],
        "domain":       row[4],
    }
