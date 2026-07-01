"""
Auth per §4: "all endpoints require the requesting user to be `user_id`
or role=admin. Standard JWT bearer."

This is a minimal stub wired to the MVP scope's stack recommendation
(Supabase Auth / Auth0 — §4 of the MVP doc: "don't hand-roll this").
Replace `decode_jwt` with your provider's SDK/verification call; the
shape of `require_user_or_admin` (and what it enforces) should not change.
"""
from __future__ import annotations

import os
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def require_user_or_admin(
    user_id: UUID,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Enforces: requesting user must match the path's user_id, or have role=admin.
    `user_id` is injected by FastAPI from the path parameter of the calling route.
    """
    claims = decode_jwt(credentials.credentials)
    token_user_id = claims.get("sub")
    role = claims.get("role", "user")

    if role != "admin" and str(user_id) != str(token_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this user's Trust Score",
        )
    return claims
