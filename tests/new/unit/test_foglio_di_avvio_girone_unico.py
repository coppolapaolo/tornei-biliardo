"""Il foglio di avvio non dice «i gironi giocano in parallelo» se ci sta un girone solo.

Difetto trovato il 2026-10-11: con una gara che ammette più gironi ma pochi
iscritti — ne sta uno solo — la riga del calendario parlava di gironi in
parallelo. Con più gironi possibili la frase segue la scelta (`data-se-gironi`).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import User
from models.base import db, utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.services import GaraService
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit

PARALLELO = "i gironi giocano in parallelo"


def _utente(role: str) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"fa_{role}_{uid}", email=f"fa_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    db.session.add(user)
    return user


def _foglio(client, iscritti: int) -> str:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value) for _ in range(iscritti)]
    db.session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Foglio",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=32,
        entry_fee=0.0,
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy="round_robin",
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=False,
        max_groups=2,
    )
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for p in players:
        InscriptionService.inscribe_user(p.id, gara.id)
    client.post("/auth/login", data={"username": director.username, "password": "x"})
    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    return html[html.index('id="avviaGaraModal"') :]


def test_con_un_girone_solo_niente_gironi_in_parallelo(client):
    foglio = _foglio(client, 5)  # 5 iscritti: almeno 3 per girone, ne sta uno
    assert PARALLELO not in foglio
    assert "ognuno incontra tutti gli altri una volta" in foglio


def test_con_piu_gironi_la_frase_segue_la_scelta(client):
    foglio = _foglio(client, 12)
    assert PARALLELO in foglio and 'data-se-gironi="piu"' in foglio
    assert 'data-se-gironi="uno"' in foglio
