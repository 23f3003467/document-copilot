"""Supabase client helpers for authenticated and service-role requests.

The database layer needs two different client styles:
- a user-scoped client whose JWT is supplied on each request; and
- a service-role client used for trusted backend operations.
This separation prevents the API from using elevated permissions by accident.
"""

from supabase import Client, create_client

from app.config import settings


def create_user_scoped_client(access_token: str) -> Client:
    """Create a client that is explicitly scoped to one user session."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


def create_service_role_client() -> Client:
    """Create a privileged client for internal backend tasks only."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


