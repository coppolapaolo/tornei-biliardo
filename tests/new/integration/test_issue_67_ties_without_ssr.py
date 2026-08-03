"""Regressione issue #67 — parimerito in gare concluse SENZA spareggio.

Il primo fix agiva su `finalize_classification`, che però è invocata solo
dopo il salvataggio dei punteggi SSR. Un parimerito fuori dalle posizioni
contese non genera spareggio (issue #63), quindi una gara chiusa senza SSR
conservava le posizioni progressive: due giocatori a pari punti restavano
7° e 8°. `StateService.complete` applica ora le posizioni finali.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.classification.models import RoundClassification
from models.competition.models import Gara, Inscription
from models.competition.state_service import StateService
from models.status_enum import GaraStatus
from models.user.models import User


def _uid() -> str:
    return str(uuid.uuid4())[:8]


def _make_players(db_session, count):
    players = []
    for i in range(count):
        user = User(
            username=f"p{i}_{_uid()}",
            email=f"p{i}_{_uid()}@test.com",
            role="player",
        )
        user.set_password("test123")
        db_session.add(user)
        players.append(user)
    db_session.flush()
    return players


def _make_completed_gara(db_session, director, players, racks, draw_order=None):
    """Gara RACK in PLAYING, senza match pendenti, con la classifica del
    turno finale già scritta con posizioni progressive."""
    existing = db_session.query(Gara).count()
    gara = Gara(
        name=f"Ties senza SSR {_uid()}",
        number=existing + 1,
        date=date.today(),
        distance=5,
        discipline="palla_9",
        matchmaking_strategy="random",
        classification_system="RACK",
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=1,
        is_race_to=True,
        director_id=director.id,
    )
    db_session.add(gara)
    db_session.flush()

    for index, (player, rack) in enumerate(zip(players, racks), start=1):
        db_session.add(
            Inscription(
                gara_id=gara.id,
                user_id=player.id,
                initial_order=(draw_order[index - 1] if draw_order else index),
            )
        )
        db_session.add(
            RoundClassification(
                gara_id=gara.id,
                round_number=1,
                user_id=player.id,
                position=index,
                matches_won=0,
                racks_won=rack,
                rack_difference=rack,
            )
        )
    db_session.flush()
    return gara


@pytest.mark.integration
class TestTiesWithoutSsr:

    def test_equal_racks_share_position_on_completion(
        self, db_session, isolated_director_user
    ):
        """Due giocatori a 3 rack sono entrambi 7°, senza alcuno spareggio."""
        players = _make_players(db_session, 8)
        racks = [8, 6, 5, 4, 4, 4, 3, 3]
        gara = _make_completed_gara(db_session, isolated_director_user, players, racks)
        db_session.commit()

        StateService.complete(gara)

        rows = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, round_number=1)
            .all()
        )
        by_user = {r.user_id: r.position for r in rows}
        positions = [by_user[p.id] for p in players]

        # 8, 6, 5 distinti; i tre a 4 rack condividono il 4°; i due a 3 il 7°.
        assert positions == [1, 2, 3, 4, 4, 4, 7, 7]

    def test_tied_players_are_listed_by_draw_order(
        self, db_session, isolated_director_user
    ):
        """A pari punti elenca prima chi è stato estratto prima."""
        players = _make_players(db_session, 2)
        # Stessi rack; il secondo giocatore è stato estratto per primo.
        gara = _make_completed_gara(
            db_session,
            isolated_director_user,
            players,
            racks=[3, 3],
            draw_order=[7, 4],
        )
        db_session.commit()

        StateService.complete(gara)

        rows = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, round_number=1)
            .all()
        )
        by_user = {r.user_id: r for r in rows}

        # Stessa posizione...
        assert by_user[players[0].id].position == by_user[players[1].id].position == 1
        # ...ma l'ordine di estrazione decide chi compare prima.
        ordered = sorted(rows, key=lambda r: (r.position, r.id))
        draw = {players[0].id: 7, players[1].id: 4}
        first_listed = min(rows, key=lambda r: draw[r.user_id]).user_id
        assert first_listed == players[1].id
        assert len(ordered) == 2

    def test_all_distinct_scores_keep_progressive_positions(
        self, db_session, isolated_director_user
    ):
        """Nessuna regressione quando non ci sono parimerito."""
        players = _make_players(db_session, 4)
        gara = _make_completed_gara(
            db_session, isolated_director_user, players, racks=[9, 7, 5, 2]
        )
        db_session.commit()

        StateService.complete(gara)

        rows = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, round_number=1)
            .all()
        )
        by_user = {r.user_id: r.position for r in rows}

        assert [by_user[p.id] for p in players] == [1, 2, 3, 4]
