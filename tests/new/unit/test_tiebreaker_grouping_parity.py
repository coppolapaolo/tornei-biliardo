"""Chi è a pari merito per lo spareggio: le vittorie non contano a rack.

C'erano due servizi che rispondevano alla stessa domanda — "quali giocatori
sono a pari merito, e serve uno spareggio?" — con criteri diversi: in una gara
RACK `TiebreakerService` includeva `matches_won` nella chiave di
raggruppamento, mentre `SpareggioService` raggruppa per i soli rack totali.
Due giocatori con gli stessi rack totali ma vittorie diverse finivano in
gruppi separati e lo spareggio non scattava.

Dal 2026-10-07 la risposta è una sola, il motore della catena (ADR-078), e
`TiebreakerService` — mai chiamato fuori dai test — è stato tolto.
"""

from __future__ import annotations

import uuid
from datetime import date, time
from typing import List

import pytest

from models import Gara, Inscription, Match, User
from models.classification.models import RoundClassification
from models.competition.spareggio_service import SpareggioService
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _setup(db_session, classification_system: str) -> Gara:
    """Gara dove due giocatori hanno gli STESSI rack totali ma vittorie diverse.

    a: vince 5-4, perde 3-5  → 8 rack totali, 1 vittoria
    b: vince 5-2, vince 3-2  → 8 rack totali, 2 vittorie

    In sistema RACK sono parimerito (contano solo i rack); in sistema WINS no.
    """
    suffix = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{suffix}",
        email=f"dir_{suffix}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("x")
    players: List[User] = []
    for i in range(4):
        u = User(
            username=f"{chr(ord('a') + i)}_{suffix}",
            email=f"{chr(ord('a') + i)}_{suffix}@test.com",
            role=UserRole.PLAYER.value,
        )
        u.set_password("x")
        players.append(u)
    db_session.add_all([director] + players)
    db_session.flush()

    gara = Gara(
        number=1,
        name=f"Parity {suffix}",
        date=date(2026, 6, 1),
        time=time(18, 0),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=director.id,
        rounds_count=2,
        current_round=2,
        min_participants=4,
        matchmaking_strategy="random",
        classification_system=classification_system,
        status=GaraStatus.PLAYING.value,
    )
    db_session.add(gara)
    db_session.flush()

    for p in players:
        db_session.add(
            Inscription(
                gara_id=gara.id,
                user_id=p.id,
                is_withdrawn=False,
                is_forfeit=False,
                is_waitlist=False,
            )
        )

    a, b, c, d = players

    def m(rnd, p1, p2, s1, s2):
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=rnd,
                player1_id=p1.id,
                player2_id=p2.id,
                player1_score=s1,
                player2_score=s2,
                winner_id=p1.id if s1 > s2 else (p2.id if s2 > s1 else None),
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )

    # a: 5 + 3 = 8 rack, 1 vittoria
    m(1, a, c, 5, 4)
    m(2, a, d, 3, 5)
    # b: 5 + 3 = 8 rack, 2 vittorie
    m(1, b, d, 5, 2)
    m(2, b, c, 3, 2)
    db_session.flush()

    RoundClassification.calculate_classification_after_round(gara.id, 2)
    db_session.flush()

    gara._a = a.id  # type: ignore[attr-defined]
    gara._b = b.id  # type: ignore[attr-defined]
    return gara


def _gruppi(gara) -> set:
    return {
        frozenset(c.user_id for c in righe)
        for _pos, righe in SpareggioService._fasce(gara, fino_allo_ssr=True)
        if len(righe) > 1
    }


@pytest.mark.unit
class TestTiebreakerGroupingParity:
    """Chi è pari per lo spareggio, secondo il sistema."""

    def test_rack_system_same_totals_is_a_tie_despite_different_wins(self, db_session):
        """Sistema RACK: stessi rack totali = parimerito, anche a vittorie diverse."""
        gara = _setup(db_session, "RACK")

        rows = {
            rc.user_id: rc
            for rc in db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, round_number=2)
            .all()
        }
        assert rows[gara._a].ranking_rack_value == rows[gara._b].ranking_rack_value
        assert rows[gara._a].matches_won != rows[gara._b].matches_won

        assert frozenset({gara._a, gara._b}) in _gruppi(gara), (
            "in una gara RACK due giocatori con gli stessi rack totali sono "
            "parimerito: le vittorie non sono un criterio di classifica"
        )
        tied = {
            p["user_id"]
            for g in SpareggioService.detect_tiebreakers(gara.id)
            for p in g["players"]
        }
        assert {gara._a, gara._b} <= tied

    def test_wins_system_different_wins_is_not_a_tie(self, db_session):
        """Sistema WINS: le vittorie contano, quindi NON è parimerito."""
        gara = _setup(db_session, "WINS")

        assert not any(
            {gara._a, gara._b} <= g for g in _gruppi(gara)
        ), "con vittorie diverse in sistema WINS non c'è parimerito"


@pytest.mark.unit
class TestSeedingRowsAreComplete:
    """Le righe di turno 0 non devono dipendere dal fallback legacy."""

    def test_seeding_rows_populate_racks_won(self, db_session):
        from models.classification.seeding_service import SeedingService

        gara = _setup(db_session, "WINS")
        ids = [
            i.user_id
            for i in db_session.query(Inscription).filter_by(gara_id=gara.id).all()
        ]

        seeding = SeedingService.ensure_seeding(gara.id, ids)
        db_session.flush()

        assert seeding
        for rc in seeding:
            assert rc.racks_won == 0, (
                "una riga appena creata deve valorizzare racks_won: NULL "
                "significa 'riga pre-separazione' e attiva il fallback"
            )
