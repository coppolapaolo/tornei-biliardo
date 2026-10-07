"""Le classifiche di una gara a più gironi, sul flusso vero (ADR-076).

Sette giocatori in due gironi da quattro e tre, composti per ELO, classifica a
punti; vince sempre chi ha l'ELO più alto, 3-0. Con la composizione per ELO
il girone A è (1°, 4°, 5°, 7°) e il B (2°, 3°, 6°) — l'indice è il posto
nella fila dell'ELO.

* Dentro il girone si ordina sui punti, con la X che vale una vittoria.
* Nella gara prima i primi, poi i secondi: per partita giocata, senza la X.
  Il primo di A ha 9 punti in 3 partite, il primo di B 6 in 2 più la X: pari,
  e anche la differenza per partita è pari — lo spareggio SSR li separa.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Dict, List

import pytest

from models import User
from models.base import db, utc_now
from models.classification.models import GaraClassification, RoundClassification
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.competition.spareggio_service import SpareggioService
from models.match.models import Match
from models.match.services import RackService
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(role: str, elo=None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"gc_{role}_{uid}", email=f"gc_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    user.elo_rating = elo
    db.session.add(user)
    return user


def _gara_giocata(n: int = 7) -> tuple[Gara, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value, elo=2000 - 10 * i) for i in range(n)]
    db.session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Gironi a punti",
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
        classification_system="POINTS",
    )
    gara.max_groups = 2
    gara.group_seeding = "elo"
    db.session.commit()
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)

    elo = {p.id: p.elo_rating for p in players}
    RoundService.start_first_round(gara.id, groups_count=2)
    gara = db.session.get(Gara, gara.id)
    for r in range(1, gara.rounds_count + 1):
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
    return db.session.get(Gara, gara.id), players


def _posizioni(gara: Gara) -> Dict[int, int]:
    return {
        gc.user_id: gc.position
        for gc in GaraClassification.query.filter_by(gara_id=gara.id).all()
    }


class TestClassificaDelTurno:
    def test_ogni_girone_si_ordina_per_se(self, db_session):
        gara, p = _gara_giocata()
        righe = {
            rc.user_id: rc
            for rc in RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=gara.rounds_count
            ).all()
        }
        a = [p[0].id, p[3].id, p[4].id, p[6].id]
        b = [p[1].id, p[2].id, p[5].id]
        assert [righe[i].group_index for i in a] == [0] * 4
        assert [righe[i].group_index for i in b] == [1] * 3
        assert [righe[i].group_position for i in a] == [1, 2, 3, 4]
        assert [righe[i].group_position for i in b] == [1, 2, 3]
        # La X vale una vittoria dentro il girone: 2 vinte + X = 9 punti.
        assert righe[p[1].id].points == 9

    def test_prima_i_primi_poi_i_secondi(self, db_session):
        gara, _p = _gara_giocata()
        righe = (
            RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=gara.rounds_count
            )
            .order_by(RoundClassification.position)
            .all()
        )
        assert [r.group_position for r in righe] == [1, 1, 2, 2, 3, 3, 4]


class TestClassificaDellaGara:
    def test_per_partita_giocata_senza_la_x(self, db_session):
        gara, p = _gara_giocata()
        SpareggioService.apply_final_positions(gara.id)
        db.session.commit()
        pos = _posizioni(gara)
        # I due primi sono pari per partita: condividono il primo posto.
        assert pos[p[0].id] == pos[p[1].id] == 1
        # Secondi: il 4° (6 punti in 3) davanti al 3° (3 punti in 2, senza X).
        assert (pos[p[3].id], pos[p[2].id]) == (3, 4)
        assert (pos[p[4].id], pos[p[5].id]) == (5, 6)
        assert pos[p[6].id] == 7
        gc = GaraClassification.query.filter_by(gara_id=gara.id, user_id=p[2].id).one()
        assert (gc.group_index, gc.group_position) == (1, 2)

    def test_lo_spareggio_scioglie_i_primi(self, db_session):
        gara, p = _gara_giocata()
        SpareggioService.apply_final_positions(gara.id)
        db.session.commit()
        gruppi = SpareggioService.detect_tiebreakers(gara.id)
        assert [sorted(x["user_id"] for x in g["players"]) for g in gruppi] == [
            sorted([p[0].id, p[1].id])
        ]
        ok, _msg = SpareggioService.save_ssr_scores(gara.id, {p[0].id: 1, p[1].id: 4})
        assert ok
        db.session.commit()
        SpareggioService.apply_final_positions(gara.id)
        db.session.commit()
        pos = _posizioni(gara)
        assert (pos[p[1].id], pos[p[0].id]) == (1, 2)
