"""Test per scripts/rotate_encryption_key.py (rotazione ENCRYPTION_KEY PII)."""

import base64
import uuid

import pytest
from sqlalchemy import text

from models.base import db
from models.user.models import User

# Chiave storica: quella usata finora in produzione (default del manager).
OLD_KEY = "default-development-key-change-in-production"
NEW_KEY = "test-rotazione-chiave-robusta"


def _make_user(email, phone):
    u = User(
        username=f"rot_{uuid.uuid4().hex[:8]}",
        email=email,
        phone=phone,
        role="player",
    )
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    return u


def _raw_pii(user_id):
    row = db.session.execute(
        text('SELECT email, phone FROM "user" WHERE id = :id'), {"id": user_id}
    ).one()
    return row.email, row.phone


def _decrypt_with(key, stored):
    from utils.encryption import derive_cipher

    token = base64.urlsafe_b64decode(stored.encode())
    return derive_cipher(key).decrypt(token).decode()


@pytest.mark.unit
def test_rotate_reencrypts_email_and_phone(db_session):
    """email/phone cifrati con la chiave vecchia diventano leggibili solo
    con la nuova; i plaintext sono preservati."""
    from scripts.rotate_encryption_key import rotate_user_pii

    email = f"rot_{uuid.uuid4().hex[:8]}@t.com"
    user = _make_user(email, "+39 333 1234567")
    db.session.commit()

    # Nel test env il manager globale usa la chiave di default (= OLD_KEY):
    # il valore raw deve decifrarsi con OLD_KEY prima della rotazione.
    raw_email, _ = _raw_pii(user.id)
    assert _decrypt_with(OLD_KEY, raw_email) == email

    report = rotate_user_pii(db.session, OLD_KEY, NEW_KEY, commit=True)

    assert report["rotated"] == 2  # email + phone
    assert report["undecryptable"] == []

    raw_email, raw_phone = _raw_pii(user.id)
    assert _decrypt_with(NEW_KEY, raw_email) == email
    assert _decrypt_with(NEW_KEY, raw_phone) == "+39 333 1234567"
    with pytest.raises(Exception):
        _decrypt_with(OLD_KEY, raw_email)


@pytest.mark.unit
def test_rotate_is_idempotent_and_dry_run_safe(db_session):
    """Secondo giro: tutto già ruotato, nessuna modifica. Dry-run non scrive."""
    from scripts.rotate_encryption_key import rotate_user_pii

    email = f"rot_{uuid.uuid4().hex[:8]}@t.com"
    user = _make_user(email, None)
    db.session.commit()
    raw_before, _ = _raw_pii(user.id)

    # Dry-run: nessuna scrittura.
    report = rotate_user_pii(db.session, OLD_KEY, NEW_KEY, commit=False)
    assert report["rotated"] >= 1
    assert _raw_pii(user.id)[0] == raw_before

    # Rotazione vera, poi secondo giro idempotente.
    rotate_user_pii(db.session, OLD_KEY, NEW_KEY, commit=True)
    report2 = rotate_user_pii(db.session, OLD_KEY, NEW_KEY, commit=True)
    assert report2["rotated"] == 0
    assert report2["already_rotated"] >= 1
    assert report2["undecryptable"] == []


@pytest.mark.unit
def test_rotate_reports_undecryptable_values(db_session):
    """Valori che non si decifrano con nessuna delle due chiavi: segnalati,
    non toccati."""
    from scripts.rotate_encryption_key import rotate_user_pii

    user = _make_user(f"rot_{uuid.uuid4().hex[:8]}@t.com", None)
    db.session.commit()
    garbage = base64.urlsafe_b64encode(b"non-e-un-token-fernet").decode()
    db.session.execute(
        text('UPDATE "user" SET email = :e WHERE id = :id'),
        {"e": garbage, "id": user.id},
    )
    db.session.commit()

    report = rotate_user_pii(db.session, OLD_KEY, NEW_KEY, commit=True)

    assert (user.id, "email") in report["undecryptable"]
    assert _raw_pii(user.id)[0] == garbage  # non toccato
