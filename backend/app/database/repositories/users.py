"""SQLAlchemy persistence operations for authenticated users."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.database.models import User


def ensure_user(session: Session, *, user_id: uuid.UUID, email: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        user = User(id=user_id, email=email)
        session.add(user)
    elif user.email != email:
        user.email = email
    return user
