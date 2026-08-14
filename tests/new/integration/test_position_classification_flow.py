"""Classifica POSITION: bande, spareggio spento, punti di campionato (Step 9).

Copre US-16 e US-17 sul flusso vero: una gara a eliminazione diretta giocata
fino in fondo e chiusa, poi la classifica finale e i punti che ne discendono.

Tre proprietà, tutte volute:

1. le posizioni vengono a **bande di pari merito** — i due semifinalisti sono
   entrambi 3°, i quattro quartifinalisti tutti 5°;
2. quei pari merito **non generano spareggi**, al contrario di quanto succede
   negli altri sistemi di classifica, dove un pareggio è un'ambiguità da
   sciogliere;
3. i punti di campionato seguono la banda: stessa posizione, stesso punteggio.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Dict, List

import pytest

from models import Gara, Match, User
from models.base import utc_now
from models.campionato.models import Campionato
from models.classification.campionato_classification import ClassificationService
from models.classification.models import Classification, GaraClassification
from models.classification.position_points import serialize_points_table
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.spareggio_service import SpareggioService
from models.competition.state_service import StateService
from models.match.services import RackService
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _uid() -> str:
    return str(uuid.uuid4())[:8]


def _make_players(db_session, count: int) -> List[User]:
    batch = _uid()
    players = []
    for index in range(count):
        player = User(
            username=f"pos_{index}_{batch}",
            email=f"pos_{index}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        players.append(player)
    db_session.add_all(players)
    db_session.commit()
    return players


def _make_director(db_session) -> User:
    batch = _uid()
    director = User(
        username=f"posdir_{batch}",
        email=f"posdir_{batch}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("director123")
    db_session.add(director)
    db_session.commit()
    return director


def _make_gara(
    db_session,
    director: User,
    players: List[User],
    *,
    campionato_id=None,
    third_place_match: bool = False,
) -> Gara:
    count = db_session.query(Gara).count()
    gara = Gara(
        director_id=director.id,
        campionato_id=campionato_id,
        number=count + 1,
        name=f"POS {_uid()}",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=2,
        is_race_to=True,
        rounds_count=3,
        min_participants=4,
        max_participants=8,
        matchmaking_strategy="direct_elimination",
        classification_system="POSITION",
        first_round_policy="random",
        third_place_match=third_place_match,
        tiebreaker_enabled=True,
    )
    db_session.add(gara)
    db_session.commit()

    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    db_session.commit()
    return gara


def _play_round(db_session, gara_id: int, round_number: int) -> None:
    """Vince sempre `player1`: l'esito conta solo per la topologia."""
    matches = Match.query.filter_by(gara_id=gara_id, round_number=round_number).all()
    for match in matches:
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=match.player1_id,
                reported_by_id=match.player1_id,
                validated_by_admin=True,
            )
    db_session.commit()


def _play_whole_gara(db_session, gara: Gara) -> None:
    RoundService.start_first_round(gara.id)
    db_session.refresh(gara)
    for round_number in range(2, gara.rounds_count + 1):
        _play_round(db_session, gara.id, round_number - 1)
        RoundService.start_next_round(gara.id, round_number)
    _play_round(db_session, gara.id, gara.rounds_count)
    # In produzione lo fanno le route a ogni match concluso: senza, le
    # RoundClassification non esistono e la classifica finale non ha da dove
    # partire.
    RoundService.update_round_progression(gara.id)
    db_session.commit()


def _final_positions(gara_id: int) -> Dict[int, int]:
    return {
        row.user_id: row.position
        for row in GaraClassification.query.filter_by(gara_id=gara_id).all()
    }


def _bracket_role(gara_id: int) -> Dict[str, List[int]]:
    """Chi è arrivato dove, letto dai match: serve per gli assert."""
    finale = Match.query.filter_by(
        gara_id=gara_id, bracket_type="W", bracket_round=3
    ).one()
    semifinali = Match.query.filter_by(
        gara_id=gara_id, bracket_type="W", bracket_round=2
    ).all()
    quarti = Match.query.filter_by(
        gara_id=gara_id, bracket_type="W", bracket_round=1
    ).all()

    def loser(match):
        return (
            match.player1_id
            if match.winner_id == match.player2_id
            else match.player2_id
        )

    return {
        "campione": [finale.winner_id],
        "finalista": [loser(finale)],
        "semifinalisti": [loser(m) for m in semifinali],
        "quartifinalisti": [loser(m) for m in quarti],
    }


class TestBandeDiPosizione:
    def test_otto_giocatori_uno_due_tre_tre_cinque(self, db_session):
        """1°, 2°, due 3° e quattro 5°: la banda vale la sua posizione più alta."""
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, _make_director(db_session), players)

        _play_whole_gara(db_session, gara)
        StateService.complete(gara)

        positions = _final_positions(gara.id)
        ruoli = _bracket_role(gara.id)

        assert positions[ruoli["campione"][0]] == 1
        assert positions[ruoli["finalista"][0]] == 2
        assert {positions[p] for p in ruoli["semifinalisti"]} == {3}
        assert {positions[p] for p in ruoli["quartifinalisti"]} == {5}
        # Nessuna posizione 4: i due terzi la occupano entrambi.
        assert sorted(positions.values()) == [1, 2, 3, 3, 5, 5, 5, 5]

    def test_con_la_finalina_il_terzo_e_uno_solo(self, db_session):
        """US-7 + US-16: la finalina scioglie la banda dei semifinalisti."""
        players = _make_players(db_session, 8)
        gara = _make_gara(
            db_session,
            _make_director(db_session),
            players,
            third_place_match=True,
        )

        _play_whole_gara(db_session, gara)
        StateService.complete(gara)

        positions = _final_positions(gara.id)
        finalina = Match.query.filter_by(gara_id=gara.id, bracket_type="3P").one()

        assert positions[finalina.winner_id] == 3
        perdente = (
            finalina.player1_id
            if finalina.winner_id == finalina.player2_id
            else finalina.player2_id
        )
        assert positions[perdente] == 4
        assert sorted(positions.values()) == [1, 2, 3, 4, 5, 5, 5, 5]


class TestSpareggioSpento:
    def test_position_non_propone_spareggi(self, db_session):
        """I pari merito del tabellone sono l'esito, non un'ambiguità."""
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, _make_director(db_session), players)

        _play_whole_gara(db_session, gara)
        StateService.complete(gara)

        assert gara.tiebreaker_enabled, "il flag della gara è acceso..."
        assert not SpareggioService.tiebreakers_apply_to(gara), "...ma POSITION no"
        assert SpareggioService.detect_tiebreakers(gara.id) == []
        assert SpareggioService.get_all_ssr_groups(gara.id) == []
        assert not SpareggioService.has_unresolved_tiebreakers(gara.id)

    def test_wins_continua_a_proporli(self, db_session):
        """Non-regressione: negli altri sistemi il pareggio va ancora sciolto."""
        from models.classification.models import RoundClassification
        from models.competition.models import Inscription

        players = _make_players(db_session, 4)
        director = _make_director(db_session)
        count = db_session.query(Gara).count()
        gara = Gara(
            director_id=director.id,
            number=count + 1,
            name=f"WINS {_uid()}",
            date=date.today(),
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            rounds_count=1,
            current_round=1,
            status=GaraStatus.PLAYING.value,
            matchmaking_strategy="random",
            classification_system="WINS",
            tiebreaker_enabled=True,
        )
        db_session.add(gara)
        db_session.flush()

        # Due giocatori a pari punti in cima: lo spareggio deve scattare.
        for index, player in enumerate(players, start=1):
            db_session.add(
                Inscription(gara_id=gara.id, user_id=player.id, initial_order=index)
            )
            db_session.add(
                RoundClassification(
                    gara_id=gara.id,
                    round_number=1,
                    user_id=player.id,
                    position=index,
                    matches_won=2 if index <= 2 else 0,
                    racks_won=10 if index <= 2 else 2,
                    rack_difference=5 if index <= 2 else -5,
                )
            )
        db_session.commit()

        assert SpareggioService.tiebreakers_apply_to(gara)
        assert SpareggioService.detect_tiebreakers(gara.id), "il pareggio va sciolto"


class TestPuntiDiCampionato:
    def _campionato(self, db_session, **kwargs) -> Campionato:
        campionato = Campionato(
            name=f"Camp {_uid()}",
            campionato_type="direct_elimination",
            default_classification_system="POSITION",
            planned_gare_count=1,
            **kwargs,
        )
        db_session.add(campionato)
        db_session.commit()
        return campionato

    def test_tabella_di_default_e_bande(self, db_session):
        """US-17: un campionato che non configura nulla usa i valori della spec."""
        campionato = self._campionato(db_session)
        players = _make_players(db_session, 8)
        gara = _make_gara(
            db_session,
            _make_director(db_session),
            players,
            campionato_id=campionato.id,
        )

        _play_whole_gara(db_session, gara)
        StateService.complete(gara)
        ClassificationService.update_campionato_classification(campionato.id)

        punti = {
            row.user_id: row.total_position_points
            for row in Classification.query.filter_by(campionato_id=campionato.id).all()
        }
        ruoli = _bracket_role(gara.id)

        assert punti[ruoli["campione"][0]] == 25
        assert punti[ruoli["finalista"][0]] == 18
        # Stessa banda, stesso punteggio: i due terzi prendono entrambi 15.
        assert {punti[p] for p in ruoli["semifinalisti"]} == {15}
        assert {punti[p] for p in ruoli["quartifinalisti"]} == {8}

    def test_tabella_configurata_sul_campionato(self, db_session):
        campionato = self._campionato(
            db_session,
            position_points=serialize_points_table({1: 100, 2: 60, 4: 30}),
        )
        players = _make_players(db_session, 8)
        gara = _make_gara(
            db_session,
            _make_director(db_session),
            players,
            campionato_id=campionato.id,
        )

        _play_whole_gara(db_session, gara)
        StateService.complete(gara)
        ClassificationService.update_campionato_classification(campionato.id)

        punti = {
            row.user_id: row.total_position_points
            for row in Classification.query.filter_by(campionato_id=campionato.id).all()
        }
        ruoli = _bracket_role(gara.id)

        assert punti[ruoli["campione"][0]] == 100
        assert punti[ruoli["finalista"][0]] == 60
        assert {punti[p] for p in ruoli["semifinalisti"]} == {30}
        # Il 5° non è coperto dalla tabella configurata: zero punti.
        assert {punti[p] for p in ruoli["quartifinalisti"]} == {0}

    def test_la_classifica_generale_ordina_per_punti(self, db_session):
        campionato = self._campionato(db_session)
        players = _make_players(db_session, 8)
        gara = _make_gara(
            db_session,
            _make_director(db_session),
            players,
            campionato_id=campionato.id,
        )

        _play_whole_gara(db_session, gara)
        StateService.complete(gara)
        ClassificationService.update_campionato_classification(campionato.id)

        rows = (
            Classification.query.filter_by(campionato_id=campionato.id)
            .order_by(Classification.position)
            .all()
        )
        ruoli = _bracket_role(gara.id)

        assert rows[0].user_id == ruoli["campione"][0]
        assert rows[0].position == 1
        assert rows[1].user_id == ruoli["finalista"][0]
        # I pari merito restano tali anche in classifica generale.
        assert sorted(row.position for row in rows) == [1, 2, 3, 3, 5, 5, 5, 5]
