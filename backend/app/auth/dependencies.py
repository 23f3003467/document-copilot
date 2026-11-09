"""Supabase JWT validation and current-user dependency.

This module is the auth boundary for the API. When a route depends on
`get_current_user`, the request enters this function before any business logic
runs. The function extracts the Bearer token from the Authorization header,
asks Supabase to validate it, and returns the authenticated user payload for the
rest of the request.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from fastapi import Header, HTTPException, status

from app.config import settings


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
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
        create_client = import_module("supabase").create_client
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        auth_response = client.auth.get_user(token)
    except Exception as exc:  # pragma: no cover - boundary validation layer
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

    return user
