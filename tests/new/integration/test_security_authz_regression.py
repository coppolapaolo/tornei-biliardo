"""Regression sicurezza route-level (review 2026-06-09).

- routes/player/matches.py:108 — forfeit_trio IDOR: un membro del trio poteva
  forfeitare un ALTRO giocatore passando player_id nella form.
- routes/player/challenges.py:81 — per gare standalone il controllo iscrizione
  era saltato: qualunque utente loggato poteva registrare tentativi.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models.base import db
from models.user.models import User
from models.competition.models import Gara, Inscription
from models.match.models import Match, TrioMatch
from models.challenge.models import Challenge
from models.competition.gara_challenge import GaraChallenge
from models.status_enum import GaraStatus, MatchStatus


def _user(suffix, name):
    u = User(
        username=f"{name}_{suffix}", email=f"{name}_{suffix}@test.com", role="player"
    )
    u.set_password("test123")
    db.session.add(u)
    return u


def _gara(suffix, **overrides):
    base = dict(
        number=1,
        name=f"Gara {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
    )
    base.update(overrides)
    g = Gara(**base)
    db.session.add(g)
    return g


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)


@pytest.mark.integration
def test_forfeit_trio_cannot_forfeit_another_player(client):
    suffix = uuid.uuid4().hex[:8]
    a, b, c = _user(suffix, "a"), _user(suffix, "b"), _user(suffix, "c")
    gara = _gara(suffix)
    db.session.flush()
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=a.id,
        player2_id=b.id,
        is_trio=True,
        status=MatchStatus.PLAYING.value,
    )
    db.session.add(match)
    db.session.flush()
    trio = TrioMatch(
        match_id=match.id,
        player1_id=a.id,
        player2_id=b.id,
        player3_id=c.id,
    )
    db.session.add(trio)
    db.session.commit()

    _login(client, a)
    # A (membro) prova a forfeitare B → 403 (IDOR bloccato).
    resp = client.post(
        f"/player/match/{match.id}/trio/forfeit",
        data={"player_id": str(b.id)},
    )
    assert resp.status_code == 403

    # B non risulta forfeitato.
    db.session.expire_all()
    updated = db.session.get(TrioMatch, trio.id)
    assert updated.forfeit_player_id is None


@pytest.mark.integration
def test_record_challenge_attempt_standalone_requires_inscription(client):
    suffix = uuid.uuid4().hex[:8]
    director = _user(suffix, "dir")
    outsider = _user(suffix, "out")
    # Gara standalone (campionato_id=None).
    gara = _gara(suffix, campionato_id=None, director_id=None)
    db.session.flush()
    gara.director_id = director.id
    ch = Challenge(
        description="Drill",
        image_path="/x.png",
        pass_fail_only=False,
        is_active=True,
        created_by_id=director.id,
    )
    db.session.add(ch)
    db.session.flush()
    gc = GaraChallenge(
        gara_id=gara.id,
        challenge_id=ch.id,
        round_number=1,
        added_by_id=director.id,
    )
    db.session.add(gc)
    db.session.commit()

    # Outsider NON iscritto alla gara standalone → 403 (prima era saltato).
    _login(client, outsider)
    resp = client.post(
        f"/player/challenge/{gc.id}/attempt",
        json={"score": 99},
    )
    assert resp.status_code == 403

    # Un iscritto supera l'authz (non 403).
    db.session.add(
        Inscription(
            gara_id=gara.id, user_id=outsider.id, is_withdrawn=False, is_waitlist=False
        )
    )
    db.session.commit()
    resp2 = client.post(
        f"/player/challenge/{gc.id}/attempt",
        json={"score": 5},
    )
    assert resp2.status_code != 403
