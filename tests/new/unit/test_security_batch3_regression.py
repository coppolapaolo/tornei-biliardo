"""Regression (review 2026-06-09, batch 3): sicurezza.

- routes/i18n.py: open redirect (substring match request.host in next_page)
  → ora confronto per netloc.
- utils/encryption.py: fail-fast se ENCRYPTION_KEY manca in produzione
  (FLASK_ENV=production); salt configurabile con default retro-compatibile.
- utils/permissions.py: i decoratori di partecipazione verificano
  is_authenticated (no AttributeError 500 su anonimo se manca @login_required).
"""

import pytest


# ---------------------------------------------------------------- open redirect
@pytest.mark.unit
@pytest.mark.parametrize(
    "referrer,expected_safe",
    [
        ("http://localhost/dashboard", True),
        ("/player/history", True),  # relativo → stesso host
        ("https://evil.com/?x=localhost", False),  # host come query param
        ("https://localhost.evil.com/", False),  # host come prefisso dominio
        ("http://evil.com/localhost", False),  # host nel path
        (None, False),
        ("", False),
    ],
)
def test_set_language_redirect_is_same_host(app, referrer, expected_safe):
    from routes.i18n import _is_safe_redirect_target

    with app.test_request_context(
        "/set_language/it",
        headers={"Referer": referrer} if referrer else {},
        base_url="http://localhost",
    ):
        assert _is_safe_redirect_target(referrer) is expected_safe


# --------------------------------------------------------------- encryption
@pytest.mark.unit
def test_encryption_fail_fast_in_production(monkeypatch):
    """Senza ENCRYPTION_KEY e FLASK_ENV=production → RuntimeError."""
    from utils.encryption import EncryptionManager

    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

    mgr = EncryptionManager.__new__(EncryptionManager)
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        mgr._initialize_cipher()


@pytest.mark.unit
def test_encryption_default_salt_roundtrip(monkeypatch):
    """Senza ENCRYPTION_SALT il roundtrip usa il salt storico (retro-compat)."""
    from utils.encryption import EncryptionManager

    monkeypatch.setenv("ENCRYPTION_KEY", "test-key")
    monkeypatch.delenv("ENCRYPTION_SALT", raising=False)

    mgr = EncryptionManager.__new__(EncryptionManager)
    mgr._initialize_cipher()
    token = mgr.encrypt("mario@example.com")
    assert mgr.decrypt(token) == "mario@example.com"


# --------------------------------------------------------------- decorators
@pytest.mark.unit
def test_participation_decorators_check_authentication(app):
    """Con utente anonimo i decoratori reindirizzano al login, niente 500.

    Chiamati direttamente in un request context senza sessione: current_user
    è AnonymousUserMixin (is_authenticated=False). Prima della fix accedevano
    a current_user.id → AttributeError → 500.
    """
    from utils.permissions import (
        player_required,
        match_player_required,
        inscription_owner_required,
        challenge_attempt_player_required,
        individual_match_player_required,
        trio_player_required,
    )

    decorators = [
        (player_required, {"gara_id": 123}),
        (match_player_required, {"match_id": 123}),
        (inscription_owner_required, {"inscription_id": 123}),
        (challenge_attempt_player_required, {"attempt_id": 123}),
        (individual_match_player_required, {"match_id": 123}),
        (trio_player_required, {"match_id": 123}),
    ]

    for deco, kwargs in decorators:

        @deco
        def _view(**kw):
            return "ok"

        with app.test_request_context("/x"):
            resp = _view(**kwargs)
            status = getattr(resp, "status_code", None)
            assert status in (301, 302), f"{deco.__name__} non reindirizza"
            assert "/login" in resp.headers.get("Location", "")
