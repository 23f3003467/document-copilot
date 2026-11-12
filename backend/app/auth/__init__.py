"""Authentication helpers for the backend API.

The request pipeline is intentionally simple: every protected route accepts a
Bearer token in the Authorization header and then verifies that token with
Supabase before any application logic can run. This keeps the auth boundary in
one place and prevents individual routes from re-implementing validation.
"""

from app.auth.dependencies import get_current_user

__all__ = ["get_current_user"]
