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


def _encrypt_with(key, plaintext):
    from utils.encryption import derive_cipher

    return base64.urlsafe_b64encode(
        derive_cipher(key).encrypt(plaintext.encode())
    ).decode()


def _set_raw_pii(user_id, email_raw, phone_raw):
    """Scrive i valori raw direttamente, bypassando EncryptedString: rende il
    test indipendente dalla chiave del manager globale (che potrebbe non
    essere OLD_KEY se l'ambiente imposta ENCRYPTION_KEY)."""
    db.session.execute(
        text('UPDATE "user" SET email = :e, phone = :p WHERE id = :id'),
        {"e": email_raw, "p": phone_raw, "id": user_id},
    )
    db.session.commit()


@pytest.mark.unit
def test_rotate_reencrypts_email_and_phone(db_session):
    """email/phone cifrati con la chiave vecchia diventano leggibili solo
    con la nuova; i plaintext sono preservati."""
    from scripts.rotate_encryption_key import rotate_user_pii

    from cryptography.fernet import InvalidToken

    email = f"rot_{uuid.uuid4().hex[:8]}@t.com"
    phone = "+39 333 1234567"
    user = _make_user(email, phone)
    db.session.commit()
    # Cifra esplicitamente con OLD_KEY per rendere il test deterministico.
    _set_raw_pii(user.id, _encrypt_with(OLD_KEY, email), _encrypt_with(OLD_KEY, phone))

    report = rotate_user_pii(db.session, OLD_KEY, NEW_KEY, commit=True)

    assert report["rotated"] == 2  # email + phone
    assert report["undecryptable"] == []

    raw_email, raw_phone = _raw_pii(user.id)
    assert _decrypt_with(NEW_KEY, raw_email) == email
    assert _decrypt_with(NEW_KEY, raw_phone) == phone
    with pytest.raises(InvalidToken):
        _decrypt_with(OLD_KEY, raw_email)


@pytest.mark.unit
def test_rotate_is_idempotent_and_dry_run_safe(db_session):
    """Secondo giro: tutto già ruotato, nessuna modifica. Dry-run non scrive."""
    from scripts.rotate_encryption_key import rotate_user_pii

    email = f"rot_{uuid.uuid4().hex[:8]}@t.com"
    user = _make_user(email, None)
    db.session.commit()
    _set_raw_pii(user.id, _encrypt_with(OLD_KEY, email), None)
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
