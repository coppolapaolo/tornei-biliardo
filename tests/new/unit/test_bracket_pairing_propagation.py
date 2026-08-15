"""Propagazione delle coordinate di tabellone da ``Pairing`` a ``Match`` (Step 3).

Le coordinate viaggiano sul ``Pairing`` — che le strategie a tabellone
valorizzano e le altre lasciano a None — e devono arrivare intatte sulle righe
``Match``, su tutti e tre i rami che rappresentano un nodo del tabellone: bye,
walkover da forfait e match normale. I trio non ne ricevono: non esistono nei
tabelloni.
"""

from datetime import date, timedelta

import pytest

from models import Gara, Match, User
from models.competition.round_creation import create_matches_from_pairings
from models.matchmaking.strategies.base import Pairing
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _player(db_session, suffix: str) -> User:
    user = User(
        username=f"p_{suffix}",
        email=f"p_{suffix}@example.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("pw")
    db_session.add(user)
    db_session.flush()
    return user


def _gara(db_session, suffix: str) -> Gara:
    director = User(
        username=f"d_{suffix}",
        email=f"d_{suffix}@example.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("pw")
    db_session.add(director)
    db_session.flush()

    gara = Gara(
        director_id=director.id,
        number=1,
        name=f"Gara {suffix}",
        date=date.today() + timedelta(days=7),
        discipline="palla_8",
        distance=5,
        is_race_to=True,
        rounds_count=3,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


class TestPairingValueObject:
    def test_default_none_per_le_strategie_non_a_tabellone(self):
        """Aggiungere i campi non cambia nulla per amalfi/random/round robin."""
        pairing = Pairing(players=(1, 2), round_number=1)
        assert pairing.bracket_type is None
        assert pairing.bracket_round is None
        assert pairing.bracket_slot is None

    def test_resta_immutabile(self):
        pairing = Pairing(players=(1, 2), bracket_type="W", bracket_slot=3)
        with pytest.raises(Exception):
            pairing.bracket_slot = 4  # type: ignore[misc]


class TestPropagazioneSuMatch:
    def test_match_normale_riceve_le_coordinate(self, db_session):
        gara = _gara(db_session, "normale")
        p1, p2 = _player(db_session, "n1"), _player(db_session, "n2")

        create_matches_from_pairings(
            gara,
            [
                Pairing(
                    players=(p1.id, p2.id),
                    round_number=1,
                    bracket_type="W",
                    bracket_round=1,
                    bracket_slot=2,
                )
            ],
            round_number=1,
            round_distance=5,
        )
        db_session.flush()

        match = Match.query.filter_by(gara_id=gara.id).one()
        assert (match.bracket_type, match.bracket_round, match.bracket_slot) == (
            "W",
            1,
            2,
        )

    def test_bye_riceve_le_coordinate(self, db_session):
        """Il bye è un nodo pieno dell'albero, non un'eccezione."""
        gara = _gara(db_session, "bye")
        p1 = _player(db_session, "b1")

        create_matches_from_pairings(
            gara,
            [
                Pairing(
                    players=(p1.id,),
                    is_bye=True,
                    round_number=1,
                    bracket_type="W",
                    bracket_round=1,
                    bracket_slot=0,
                )
            ],
            round_number=1,
            round_distance=5,
        )
        db_session.flush()

        match = Match.query.filter_by(gara_id=gara.id).one()
        assert match.is_bye is True
        assert (match.bracket_type, match.bracket_round, match.bracket_slot) == (
            "W",
            1,
            0,
        )

    def test_walkover_da_forfait_riceve_le_coordinate(self, db_session):
        """Un ritirato non fa sparire il nodo: l'avversario avanza a tavolino."""
        gara = _gara(db_session, "wo")
        p1, p2 = _player(db_session, "w1"), _player(db_session, "w2")

        create_matches_from_pairings(
            gara,
            [
                Pairing(
                    players=(p1.id, p2.id),
                    round_number=1,
                    bracket_type="W",
                    bracket_round=1,
                    bracket_slot=1,
                )
            ],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p1.id},
        )
        db_session.flush()

        match = Match.query.filter_by(gara_id=gara.id).one()
        assert match.winner_id == p2.id
        assert (match.bracket_type, match.bracket_round, match.bracket_slot) == (
            "W",
            1,
            1,
        )

    def test_pairing_senza_coordinate_lascia_null(self, db_session):
        """Le strategie a girone continuano a produrre match senza tabellone."""
        gara = _gara(db_session, "null")
        p1, p2 = _player(db_session, "z1"), _player(db_session, "z2")

        create_matches_from_pairings(
            gara,
            [Pairing(players=(p1.id, p2.id), round_number=1)],
            round_number=1,
            round_distance=5,
        )
        db_session.flush()

        match = Match.query.filter_by(gara_id=gara.id).one()
        assert match.bracket_type is None
        assert match.bracket_round is None
        assert match.bracket_slot is None

    def test_trio_non_riceve_coordinate(self, db_session):
        """I trio non esistono nei tabelloni: restano senza coordinate."""
        gara = _gara(db_session, "trio")
        gara.distance = 3  # trio ammesso solo per distanze 2-7 (ADR-005)
        db_session.flush()
        p1 = _player(db_session, "t1")
        p2 = _player(db_session, "t2")
        p3 = _player(db_session, "t3")

        create_matches_from_pairings(
            gara,
            [
                Pairing(
                    players=(p1.id, p2.id, p3.id),
                    round_number=1,
                    # Anche se qualcuno le valorizzasse per errore, il ramo
                    # trio non le legge affatto.
                    bracket_type="W",
                    bracket_round=1,
                    bracket_slot=0,
                )
            ],
            round_number=1,
            round_distance=5,
        )
        db_session.flush()

        match = Match.query.filter_by(gara_id=gara.id).one()
        assert match.is_trio is True
        assert match.bracket_type is None
        assert match.bracket_slot is None
