"""Test per email_hash: lookup O(1) per email su campo cifrato (issue #8).

L'email e' cifrata con Fernet (non deterministico) e non e' filtrabile in SQL.
`user.email_hash` (HMAC-SHA256 dell'email normalizzata) abilita un lookup
indicizzato senza decifrare tutti gli utenti.
"""

import uuid

import pytest

from models.user.models import User
from models.user.role_enum import UserRole
from models.user.services import UserService
from models.user.profile_service import UserProfileService
from utils.encryption import compute_email_hash


def _make_user(email):
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=email,
        role=UserRole.PLAYER.value,
    )
    user.set_password("pass123")
    return user


class TestComputeEmailHash:
    def test_deterministic(self):
        assert compute_email_hash("a@b.com") == compute_email_hash("a@b.com")

    def test_normalizes_case_and_whitespace(self):
        base = compute_email_hash("foo@bar.com")
        assert compute_email_hash("  FOO@BAR.com ") == base
        assert compute_email_hash("Foo@Bar.Com") == base

    def test_distinct_emails_differ(self):
        assert compute_email_hash("a@b.com") != compute_email_hash("c@d.com")

    def test_empty_and_none_return_none(self):
        assert compute_email_hash(None) is None
        assert compute_email_hash("") is None
        assert compute_email_hash("   ") is None

    def test_hex_sha256_length(self):
        assert len(compute_email_hash("a@b.com")) == 64


class TestUserEmailHashSync:
    def test_email_hash_set_on_creation(self, db_session):
        email = f"sync_{uuid.uuid4().hex[:8]}@test.com"
        user = _make_user(email)
        db_session.add(user)
        db_session.flush()
        assert user.email_hash == compute_email_hash(email)

    def test_email_hash_updates_on_email_change(self, db_session):
        user = _make_user(f"old_{uuid.uuid4().hex[:8]}@test.com")
        db_session.add(user)
        db_session.flush()

        new_email = f"new_{uuid.uuid4().hex[:8]}@test.com"
        user.email = new_email
        db_session.flush()
        assert user.email_hash == compute_email_hash(new_email)

    def test_anonymize_clears_email_hash(self, db_session):
        user = _make_user(f"anon_{uuid.uuid4().hex[:8]}@test.com")
        db_session.add(user)
        db_session.flush()
        assert user.email_hash is not None

        user.anonymize()
        db_session.flush()
        assert user.email is None
        assert user.email_hash is None


class TestGetUserByEmail:
    @pytest.mark.parametrize(
        "service", [UserService, UserProfileService], ids=["core", "profile"]
    )
    def test_finds_user_by_email(self, db_session, service):
        email = f"find_{uuid.uuid4().hex[:8]}@test.com"
        user = _make_user(email)
        db_session.add(user)
        db_session.flush()

        found = service.get_user_by_email(email)
        assert found is not None
        assert found.id == user.id

    @pytest.mark.parametrize(
        "service", [UserService, UserProfileService], ids=["core", "profile"]
    )
    def test_lookup_is_case_and_whitespace_insensitive(self, db_session, service):
        email = f"case_{uuid.uuid4().hex[:8]}@test.com"
        user = _make_user(email)
        db_session.add(user)
        db_session.flush()

        found = service.get_user_by_email(f"  {email.upper()} ")
        assert found is not None
        assert found.id == user.id

    @pytest.mark.parametrize(
        "service", [UserService, UserProfileService], ids=["core", "profile"]
    )
    def test_nonexistent_email_returns_none(self, db_session, service):
        assert service.get_user_by_email(f"nope_{uuid.uuid4().hex}@x.com") is None

    @pytest.mark.parametrize(
        "service", [UserService, UserProfileService], ids=["core", "profile"]
    )
    def test_empty_email_returns_none(self, db_session, service):
        assert service.get_user_by_email("") is None
