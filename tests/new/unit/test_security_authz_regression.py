"""Regression sicurezza (review 2026-06-09): authz/IDOR/XSS.

Bug coperti:
- models/challenge/services.py:303 — create_x_replacement_attempt non
  verificava che l'utente avesse davvero un bye → bye fabbricabile.
- models/shared/email_service.py:88 — username raw in HTML email → XSS.

(I bug route-level forfeit_trio IDOR e authz challenge standalone sono in
tests/new/integration/test_security_authz_regression.py.)
"""

from __future__ import annotations

import uuid
from datetime import date, time
from unittest.mock import patch

import pytest

from models.base import db
from models.user.models import User
from models.competition.models import Gara
from models.match.models import Match
from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.exceptions import PermissionDeniedError
from models.status_enum import GaraStatus, MatchStatus


def _user(suffix, name):
    u = User(
        username=f"{name}_{suffix}", email=f"{name}_{suffix}@test.com", role="player"
    )
    u.set_password("test123")
    return u


def _gara(suffix):
    return Gara(
        number=1,
        name=f"Gara {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="palla_8",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
    )


@pytest.mark.unit
def test_x_replacement_without_bye_is_denied(db_session):
    suffix = uuid.uuid4().hex[:8]
    attacker = _user(suffix, "atk")
    db.session.add(attacker)
    gara = _gara(suffix)
    db.session.add(gara)
    db.session.flush()

    # L'attaccante NON ha alcun bye in (gara, round 1): deve essere respinto.
    with pytest.raises(PermissionDeniedError):
        ChallengeService.create_x_replacement_attempt(
            user_id=attacker.id, gara_id=gara.id, round_number=1
        )


@pytest.mark.unit
def test_x_replacement_with_real_bye_is_allowed(db_session):
    suffix = uuid.uuid4().hex[:8]
    player = _user(suffix, "bye")
    db.session.add(player)
    gara = _gara(suffix)
    db.session.add(gara)
    db.session.flush()
    # Challenge numerica disponibile per la X-replacement.
    ch = Challenge(
        description="Spot Shot",
        image_path="/x.png",
        pass_fail_only=False,
        is_active=True,
        created_by_id=player.id,
    )
    db.session.add(ch)
    # Bye reale materializzato da round-creation.
    db.session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=player.id,
            player2_id=None,
            is_bye=True,
            status=MatchStatus.COMPLETED.value,
            winner_id=player.id,
            player1_score=5,
        )
    )
    db.session.flush()

    attempt = ChallengeService.create_x_replacement_attempt(
        user_id=player.id, gara_id=gara.id, round_number=1, challenge_id=ch.id
    )
    assert attempt.user_id == player.id


@pytest.mark.unit
def test_verification_email_escapes_username(db_session):
    # Username con markup: deve essere escapato nel corpo HTML dell'email.
    suffix = uuid.uuid4().hex[:8]
    evil = "<img src=x onerror=alert(1)>"
    user = User(username=f"{evil}_{suffix}", email="evil@test.com", role="player")
    user.set_password("test123")
    db.session.add(user)
    db.session.flush()

    from models.shared.email_service import EmailService
    from models.user.tokens import UserToken

    # Token in memoria: il metodo email legge solo token.token.
    token = UserToken(user_id=user.id, token="tok123", token_type="verification")

    with patch.object(EmailService, "send_email", return_value=True) as mock_send:
        EmailService.send_verification_email(user, token, "https://x.it")

    html = mock_send.call_args[0][2]  # (to, subject, html_content)
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img" in html  # escaped


@pytest.mark.unit
def test_password_reset_email_escapes_username(db_session):
    suffix = uuid.uuid4().hex[:8]
    evil = "<script>steal()</script>"
    user = User(username=f"{evil}_{suffix}", email="evil2@test.com", role="player")
    user.set_password("test123")
    db.session.add(user)
    db.session.flush()

    from models.shared.email_service import EmailService
    from models.user.tokens import UserToken

    token = UserToken(user_id=user.id, token="tok456", token_type="password_reset")

    with patch.object(EmailService, "send_email", return_value=True) as mock_send:
        EmailService.send_password_reset_email(user, token, "https://x.it")

    html = mock_send.call_args[0][2]
    assert "<script>steal()</script>" not in html
    assert "&lt;script&gt;" in html
