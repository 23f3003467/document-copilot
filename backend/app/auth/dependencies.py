"""Supabase JWT validation and current-user dependency.

This module is the auth boundary for the API. When a route depends on
`get_current_user`, the request enters this function before any business logic
runs. The function extracts the Bearer token from the Authorization header,
asks Supabase to validate it, and returns the authenticated user payload for the
rest of the request.
"""

from __future__ import annotations

import supabase
from typing import TypedDict

from fastapi import Header, HTTPException, status

from app.config import settings


class CurrentUser(TypedDict):
    id: str
    email: str | None
    last_sign_in_at: str | None


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    """Return the authenticated Supabase user for the current request.

    The frontend sends the JWT in the standard `Authorization: Bearer <token>`
    header. We validate that token with Supabase instead of trusting any client
    supplied claim.
    """
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header. Use 'Bearer <token>'.",
        )

    try:
        client = supabase.create_client(settings.supabase_url, settings.supabase_anon_key)
        auth_response = client.auth.get_user(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        ) from exc

    user = getattr(auth_response, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        )

    last_sign_in_at = getattr(user, "last_sign_in_at", None)
    return {
        "id": str(user.id),
        "email": getattr(user, "email", None),
        "last_sign_in_at": (
            str(last_sign_in_at) if last_sign_in_at is not None else None
        ),
    }
