"""
Supabase JWT authentication for the FOBE explorer server.

Validates access tokens issued by Supabase Auth using the JWKS endpoint.
Provides FastAPI dependencies for protecting endpoints.
"""

import json
import os
from typing import Optional
from urllib.request import urlopen

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import PyJWK

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")

_bearer_scheme = HTTPBearer(auto_error=False)

# Cache the JWKS keys at module load time
_jwk_keys: dict = {}  # kid -> PyJWK object


def _load_jwks():
    """Fetch JWKS public keys from Supabase Auth."""
    global _jwk_keys
    if _jwk_keys or not SUPABASE_URL:
        return
    try:
        url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        for key_data in data.get("keys", []):
            kid = key_data.get("kid")
            if kid:
                _jwk_keys[kid] = PyJWK(key_data)
    except Exception:
        pass  # will fail on decode instead


class AuthUser:
    """Authenticated user extracted from a Supabase JWT."""
    __slots__ = ("id", "email", "role")

    def __init__(self, id: str, email: str, role: str = "authenticated"):
        self.id = id
        self.email = email
        self.role = role


def _decode_token(token: str) -> dict:
    """Decode and validate a Supabase access token using JWKS."""
    _load_jwks()
    if not _jwk_keys:
        raise HTTPException(status_code=500, detail="JWKS not available — check SUPABASE_URL")

    # Extract kid from unverified header
    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token header: {e}")

    kid = header.get("kid")
    jwk_key = _jwk_keys.get(kid)
    if not jwk_key:
        raise HTTPException(status_code=401, detail=f"Unknown signing key: {kid}")

    try:
        payload = jwt.decode(
            token,
            jwk_key,
            algorithms=[header.get("alg", "ES256")],
            audience="authenticated",
        )
        return payload
    except jwt.exceptions.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthUser:
    """FastAPI dependency: require a valid Supabase JWT. Returns AuthUser."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = _decode_token(credentials.credentials)
    user_id = payload.get("sub")
    email = payload.get("email", "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")
    return AuthUser(id=user_id, email=email, role=payload.get("role", "authenticated"))


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[AuthUser]:
    """FastAPI dependency: extract user if token present, None otherwise."""
    if not credentials:
        return None
    try:
        payload = _decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            return None
        return AuthUser(id=user_id, email=payload.get("email", ""), role=payload.get("role", "authenticated"))
    except HTTPException:
        return None
