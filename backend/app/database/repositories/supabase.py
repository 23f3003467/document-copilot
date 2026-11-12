"""Supabase client helpers for authenticated and service-role requests.

The database layer needs two different client styles:
- a user-scoped client whose JWT is supplied on each request; and
- a service-role client used for trusted backend operations.
This separation prevents the API from using elevated permissions by accident.
"""

from supabase import AsyncClient, create_async_client

from app.config import settings


async def create_user_scoped_client(access_token: str) -> AsyncClient:
    """Create a client that is explicitly scoped to one user session."""
    client = await create_async_client(
        settings.supabase_url,
        settings.supabase_anon_key,
    )
    client.postgrest.auth(access_token)
    return client


async def get_service_role_client() -> AsyncClient:
    """Create a privileged client for internal backend tasks only."""
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
