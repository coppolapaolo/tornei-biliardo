"""Le pagine della gara con due gironi (ADR-076).

Sette giocatori in due gironi da quattro e tre, composti per ELO: vince
sempre chi ha l'ELO più alto, 3-0. Mentre si gioca il direttore, l'ospite,
lo schermo in sala e la tessera di chi gioca vedono una classifica per
girone; a gara conclusa la classifica della gara, con «1º girone A» accanto
al nome. Col girone unico le pagine restano quelle di sempre.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import List, Tuple

import pytest

from models import User
from models.base import db, utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.match.models import Match
from models.match.services import RackService
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(role: str, elo=None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"tp_{role}_{uid}", email=f"tp_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    user.elo_rating = elo
    db.session.add(user)
    return user


def _gara(gironi: int, turni_da_giocare: int) -> Tuple[Gara, User, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value, elo=2000 - 10 * i) for i in range(7)]
    db.session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Gironi in pagina",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=16,
        entry_fee=0.0,
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy="round_robin",
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=False,
    )
    gara.max_groups = gironi
    gara.group_seeding = "elo"
    gara.public_token = uuid.uuid4().hex[:10]
    db.session.commit()
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)

    elo = {p.id: p.elo_rating for p in players}
    RoundService.start_first_round(gara.id, groups_count=gironi)
    for r in range(1, turni_da_giocare + 1):
        if r > 1:
            RoundService.start_next_round(gara.id, r)
        for match in Match.query.filter_by(gara_id=gara.id, round_number=r).all():
            if match.is_bye or MatchStatus.is_finished(match.status):
                continue
            vince = max((match.player1_id, match.player2_id), key=lambda p: elo[p])
            for _ in range(match.match_distance):
                RackService.add_rack_with_score_update(
                    match_id=match.id,
                    winner_id=vince,
                    reported_by_id=vince,
                    validated_by_admin=True,
                )
        db.session.commit()
        RoundService.update_round_progression(gara.id)
        db.session.commit()
    return db.session.get(Gara, gara.id), director, players


def _come(client, user: User) -> None:
    risposta = client.post(
        "/auth/login", data={"username": user.username, "password": "x"}
    )
    assert risposta.status_code in (200, 302)


def _pagina(client, gara: Gara) -> str:
    risposta = client.get(f"/admin/gara/{gara.id}")
    assert risposta.status_code == 200
    return risposta.get_data(as_text=True)


class TestMentreSiGioca:
    def test_il_direttore_vede_una_classifica_per_girone(self, client):
        gara, director, players = _gara(2, 2)
        assert gara.status == GaraStatus.PLAYING.value
        _come(client, director)
        html = _pagina(client, gara)
        sezione = html[html.index('id="classificaDirettore"') :]
        sezione = sezione[: sezione.index("</section>")]
        assert 'data-girone="A"' in sezione and 'data-girone="B"' in sezione
        # Il girone A per ELO è (1°, 4°, 5°, 7°): il più forte è primo in A.
        a = sezione[sezione.index('data-girone="A"') : sezione.index('data-girone="B"')]
        assert players[0].username in a and players[1].username not in a
        # La partita dice il suo girone.
        assert "Girone A" in html[: html.index('id="classificaDirettore"')]

    def test_l_ospite_e_lo_schermo_in_sala_vedono_i_gironi(self, client):
        gara, _director, _players = _gara(2, 2)
        html = _pagina(client, gara)
        assert html.count('data-girone="A"') >= 2  # telefono e desktop
        sala = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)
        assert 'data-girone="A"' in sala and 'data-girone="B"' in sala

    def test_la_tessera_dice_la_posizione_nel_girone(self, client):
        gara, _director, players = _gara(2, 2)
        # La tessera mostra la classifica mentre si gioca il turno dopo.
        RoundService.start_next_round(gara.id, 3)
        db.session.commit()
        _come(client, players[0])
        html = client.get("/dashboard").get_data(as_text=True)
        assert re.search(r"Sei 1° su 4 nel girone A", html)


class TestAGaraConclusa:
    def test_la_classifica_della_gara_dice_da_che_girone_viene_ognuno(self, client):
        gara, director, players = _gara(2, 3)
        GaraService.complete(gara.id)
        db.session.commit()
        gara = db.session.get(Gara, gara.id)
        assert gara.status != GaraStatus.PLAYING.value
        _come(client, director)
        html = _pagina(client, gara)
        assert 'data-girone="A"' not in html
        assert "1º girone A" in html and "1º girone B" in html


class TestGironeUnico:
    def test_la_pagina_resta_quella_di_sempre(self, client):
        gara, director, _players = _gara(1, 2)
        _come(client, director)
        html = _pagina(client, gara)
        assert "data-girone=" not in html
        assert "girone A" not in html and "Girone A" not in html
        assert 'id="classificaDirettore"' in html
