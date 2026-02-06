"""
Module: models/user/tokens.py
Purpose: User token management for email verification and password reset
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional

from ..base import db, BaseModel, utc_now


class UserToken(BaseModel):
    """Token for user verification and password reset."""

    __tablename__ = "user_token"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    token = db.Column(db.String(100), unique=True, nullable=False, index=True)
    token_type = db.Column(db.String(20), nullable=False)  # 'verification', 'password_reset'
    created_at = db.Column(db.DateTime, default=utc_now)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

    # Relationship
    user = db.relationship("User", backref=db.backref("tokens", lazy=True))

    @classmethod
    def create_token(
        cls, user_id: int, token_type: str, expires_in_hours: int = 24
    ) -> UserToken:
        """Create a new token for a user.

        Args:
            user_id: ID of the user
            token_type: Type of token ('verification' or 'password_reset')
            expires_in_hours: Token expiration time in hours (default: 24)

        Returns:
            UserToken: The created token
        """
        token_str = secrets.token_urlsafe(32)
        expires_at = utc_now() + timedelta(hours=expires_in_hours)

        token = cls(
            user_id=user_id,
            token=token_str,
            token_type=token_type,
            expires_at=expires_at,
        )
        db.session.add(token)
        return token

    def is_valid(self) -> bool:
        """Check if token is valid and not expired."""
        if self.is_used:
            return False
        if utc_now() > self.expires_at:
            return False
        return True

    def mark_as_used(self) -> None:
        """Mark token as used."""
        self.is_used = True
