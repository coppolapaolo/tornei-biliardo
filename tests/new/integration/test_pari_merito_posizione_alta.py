"""Due giocatori separati solo dal sorteggio: primi a pari merito (2026-10-11).

Regola dell'utente: «Il pari merito va sempre sulla posizione più alta. Se uno
è pari merito col primo allora è primo pari merito, non secondo. La tessera
deve dire che è n-esimo pari merito.»

Quattro giocatori, girone all'italiana, catena di turno «differenza triangoli
→ sorteggio»: al primo turno i due vincitori fanno entrambi 3-0, quindi sono
pari su tutto tranne il sorteggio. La classifica di turno li mette 1° e 2° —
gli abbinamenti ne hanno bisogno — ma la tessera di entrambi dice «Sei 1° pari
merito su 4», e la pagina della gara mostra «1» a tutti e due.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta
from typing import List, Tuple

import pytest

from models import User
from models.base import db, utc_now
from models.classification.models import RoundClassification
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.match.models import Match
from models.match.services import RackService
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(role: str) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"pm_{role}_{uid}", email=f"pm_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    db.session.add(user)
    return user


def _gara_al_secondo_turno(secondo_turno: bool = True) -> Tuple[Gara, User, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value) for _ in range(4)]
    db.session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Pari merito",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=3,
        min_participants=2,
        max_participants=16,
        entry_fee=0.0,
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy="round_robin",
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=False,
    )
    # A pari vittorie e differenza decide solo il sorteggio.
    gara.catena_turno = json.dumps(["differenza_rack", "sorteggio"])
    gara.public_token = uuid.uuid4().hex[:10]
    db.session.commit()
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    RoundService.start_first_round(gara.id)
    for match in Match.query.filter_by(gara_id=gara.id, round_number=1).all():
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=match.player1_id,
                reported_by_id=match.player1_id,
                validated_by_admin=True,
            )
    db.session.commit()
    RoundService.update_round_progression(gara.id)
    db.session.commit()
    if secondo_turno:
        RoundService.start_next_round(gara.id, 2)
        db.session.commit()
    return db.session.get(Gara, gara.id), director, players


def _come(client, user: User) -> None:
    risposta = client.post(
        "/auth/login", data={"username": user.username, "password": "x"}
    )
    assert risposta.status_code in (200, 302)


def _righe_turno_1(gara: Gara) -> List[RoundClassification]:
    return (
        RoundClassification.query.filter_by(gara_id=gara.id, round_number=1)
        .order_by(RoundClassification.position)
        .all()
    )


def test_la_classifica_decide_e_mostra(client):
    gara, _director, _players = _gara_al_secondo_turno()
    assert gara.status == GaraStatus.PLAYING.value
    righe = _righe_turno_1(gara)
    # Decide il sorteggio: posizioni distinte per gli abbinamenti.
    assert [r.position for r in righe] == [1, 2, 3, 4]
    # Si mostra il pari merito sulla posizione più alta.
    assert [r.posizione_mostrata for r in righe] == [1, 1, 3, 3]


def test_la_tessera_di_entrambi_dice_primo_pari_merito(client):
    gara, _director, _players = _gara_al_secondo_turno()
    primo, secondo = (r.user for r in _righe_turno_1(gara)[:2])
    for giocatore in (primo, secondo):
        client.get("/auth/logout")
        _come(client, giocatore)
        html = client.get("/dashboard").get_data(as_text=True)
        assert "Sei 1° pari merito su 4" in html, giocatore.username
        assert "Sei 2°" not in html


def test_la_pagina_della_gara_mostra_uno_a_entrambi(client):
    gara, director, _players = _gara_al_secondo_turno()
    primo, secondo = (r.user for r in _righe_turno_1(gara)[:2])
    _come(client, director)
    html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    sezione = html[html.index('id="classificaDirettore"') :]
    sezione = sezione[: sezione.index("</section>")]
    posizioni = re.findall(r'c7-classifica__pos[^"]*">(\d+)</span>', sezione)
    assert posizioni[:4] == ["1", "1", "3", "3"]
    assert sezione.index(primo.username) < sezione.index(secondo.username)


def test_lo_schermo_in_sala_mostra_uno_a_entrambi(client):
    gara, _director, _players = _gara_al_secondo_turno()
    sala = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)
    posizioni = re.findall(r'c7-pos c7-pos--lg[^"]*">(\d+)</span>', sala)
    assert posizioni[:4] == ["1", "1", "3", "3"]


def test_nella_classifica_di_gara_col_sorteggio_decide_ma_non_si_mostra(client):
    """La catena di gara che finisce col sorteggio: posizioni distinte (i punti
    del piazzamento e i premi le leggono), posizione mostrata condivisa."""
    from models.classification.models import GaraClassification
    from models.competition.spareggio_service import SpareggioService

    gara, _director, _players = _gara_al_secondo_turno(secondo_turno=False)
    gara.catena_gara = json.dumps(["differenza_rack", "sorteggio"])
    db.session.commit()
    SpareggioService.apply_final_positions(gara.id)
    db.session.commit()
    righe = (
        GaraClassification.query.filter_by(gara_id=gara.id)
        .order_by(GaraClassification.position)
        .all()
    )
    assert [r.position for r in righe] == [1, 2, 3, 4]
    assert [r.posizione_mostrata for r in righe] == [1, 1, 3, 3]
    turno = _righe_turno_1(gara)
    assert [r.posizione_mostrata for r in turno] == [1, 1, 3, 3]


def test_senza_sorteggio_i_pari_condividono_la_posizione_come_sempre(client):
    """La catena di gara di default lascia i pari a pari: 1, 1, 3, 3 anche nella
    posizione che decide, e i punti del piazzamento vanno a entrambi."""
    from models.classification.models import GaraClassification
    from models.competition.spareggio_service import SpareggioService

    gara, _director, _players = _gara_al_secondo_turno(secondo_turno=False)
    gara.catena_gara = json.dumps(["differenza_rack"])
    db.session.commit()
    SpareggioService.apply_final_positions(gara.id)
    db.session.commit()
    righe = GaraClassification.query.filter_by(gara_id=gara.id).all()
    assert sorted(r.position for r in righe) == [1, 1, 3, 3]
    assert sorted(r.posizione_mostrata for r in righe) == [1, 1, 3, 3]
