"""La classifica di partenza (turno 0) risolve i parimerito di turno.

Prima di questo fix il terzo criterio di `calculate_classification_after_round`
era `user_id`, cioè l'ordine di registrazione sulla piattaforma: a parità di
match vinti e differenza rack vinceva chi si era iscritto prima al sito, il che
in una gara di prova con utenti creati in ordine alfabetico sembra — ed è stato
segnalato come — un ordinamento alfabetico.

L'ordine corretto è quello del metodo scelto per il primo accoppiamento
(sorteggio, rating, classifica campionato, ordine di iscrizione): quel metodo
definisce una classifica di partenza che va salvata come turno 0 e propagata
di turno in turno via `previous_position`.
"""

from __future__ import annotations

import uuid
from datetime import date, time
from typing import List

import pytest

from models import Gara, Inscription, Match, User
from models.classification.models import RoundClassification
from models.classification.seeding_service import SEEDING_ROUND, SeedingService
from models.matchmaking.strategies.amalfi import AmalfiStrategy
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _make_players(db_session, count: int, ratings: List[int] | None = None):
    """Crea `count` player. Gli username crescono con l'id (a_, b_, ...)."""
    suffix = str(uuid.uuid4())[:8]
    players = []
    for i in range(count):
        player = User(
            username=f"{chr(ord('a') + i)}_{suffix}",
            email=f"{chr(ord('a') + i)}_{suffix}@test.com",
            role=UserRole.PLAYER.value,
            fargo_rating=ratings[i] if ratings else None,
        )
        player.set_password("x")
        players.append(player)
    db_session.add_all(players)
    db_session.flush()
    return players


def _make_gara(
    db_session,
    players,
    classification_system: str = "WINS",
    first_round_policy: str = "random",
    matchmaking_strategy: str = "amalfi",
) -> Gara:
    suffix = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{suffix}",
        email=f"dir_{suffix}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("x")
    db_session.add(director)
    db_session.flush()

    gara = Gara(
        number=1,
        name=f"Seeding {suffix}",
        date=date(2026, 3, 1),
        time=time(18, 0),
        discipline="palla_9",
        distance=5,
        is_race_to=True,
        director_id=director.id,
        rounds_count=3,
        current_round=1,
        min_participants=len(players),
        matchmaking_strategy=matchmaking_strategy,
        classification_system=classification_system,
        first_round_policy=first_round_policy,
        status=GaraStatus.PLAYING.value,
    )
    db_session.add(gara)
    db_session.flush()

    for player in players:
        db_session.add(
            Inscription(
                gara_id=gara.id,
                user_id=player.id,
                is_withdrawn=False,
                is_forfeit=False,
                is_waitlist=False,
            )
        )
    db_session.flush()
    return gara


def _add_match(db_session, gara, round_number, winner, loser, score=(5, 3)):
    match = Match(
        gara_id=gara.id,
        round_number=round_number,
        player1_id=winner.id,
        player2_id=loser.id,
        player1_score=score[0],
        player2_score=score[1],
        winner_id=winner.id,
        status=MatchStatus.COMPLETED.value,
    )
    db_session.add(match)
    db_session.flush()
    return match


def _positions(db_session, gara_id, round_number):
    """user_id in ordine di posizione per il turno indicato."""
    return [
        rc.user_id
        for rc in db_session.query(RoundClassification)
        .filter_by(gara_id=gara_id, round_number=round_number)
        .order_by(RoundClassification.position)
        .all()
    ]


@pytest.mark.unit
class TestSeedingBreaksRoundTies:
    """Il parimerito di turno segue la classifica di partenza, non l'user_id."""

    def test_tie_at_round_1_follows_seeding_not_user_id(self, db_session):
        """4 giocatori, due coppie a parimerito perfetto.

        Il seeding è l'inverso dell'ordine di user_id: se il tie-break fosse
        ancora `user_id` la classifica uscirebbe [a, c, b, d]; col seeding esce
        [c, a, d, b].
        """
        a, b, c, d = _make_players(db_session, 4)
        gara = _make_gara(db_session, [a, b, c, d])

        SeedingService.ensure_seeding(gara.id, [d.id, c.id, b.id, a.id])

        # a batte b, c batte d: {a, c} a +2 con 1 vittoria, {b, d} a -2 con 0
        _add_match(db_session, gara, 1, winner=a, loser=b)
        _add_match(db_session, gara, 1, winner=c, loser=d)

        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        assert _positions(db_session, gara.id, 1) == [c.id, a.id, d.id, b.id]

    def test_seeding_propagates_through_rounds(self, db_session):
        """Il parimerito del turno 2 risale al sorteggio via turno 1."""
        a, b, c, d = _make_players(db_session, 4)
        gara = _make_gara(db_session, [a, b, c, d])

        SeedingService.ensure_seeding(gara.id, [d.id, c.id, b.id, a.id])

        _add_match(db_session, gara, 1, winner=a, loser=b)
        _add_match(db_session, gara, 1, winner=c, loser=d)
        RoundClassification.calculate_classification_after_round(gara.id, 1)

        # Turno 2 speculare: a e c restano appaiati (2 vittorie, +4), idem b e d
        _add_match(db_session, gara, 2, winner=a, loser=d)
        _add_match(db_session, gara, 2, winner=c, loser=b)
        RoundClassification.calculate_classification_after_round(gara.id, 2)
        db_session.flush()

        assert _positions(db_session, gara.id, 2) == [c.id, a.id, d.id, b.id]

        # previous_position del turno 1 punta al sorteggio, non a NULL
        rc_round1 = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, round_number=1, user_id=c.id)
            .one()
        )
        assert rc_round1.previous_position == 2

    def test_without_seeding_falls_back_to_user_id(self, db_session):
        """Gare pre-esistenti (nessun turno 0): comportamento storico invariato."""
        a, b, c, d = _make_players(db_session, 4)
        gara = _make_gara(db_session, [a, b, c, d])

        _add_match(db_session, gara, 1, winner=a, loser=b)
        _add_match(db_session, gara, 1, winner=c, loser=d)

        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        assert _positions(db_session, gara.id, 1) == [a.id, c.id, b.id, d.id]

    def test_rack_system_tie_follows_seeding(self, db_session):
        """Anche il sistema RACK usa il seeding prima dell'user_id."""
        a, b, c, d = _make_players(db_session, 4)
        gara = _make_gara(db_session, [a, b, c, d], classification_system="RACK")

        SeedingService.ensure_seeding(gara.id, [d.id, c.id, b.id, a.id])

        _add_match(db_session, gara, 1, winner=a, loser=b)
        _add_match(db_session, gara, 1, winner=c, loser=d)

        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        assert _positions(db_session, gara.id, 1) == [c.id, a.id, d.id, b.id]


@pytest.mark.unit
class TestSeedingOrderPerPolicy:
    """Ogni policy di primo accoppiamento produce la propria classifica iniziale."""

    def test_rating_policy_orders_by_rating_desc(self, db_session):
        """first_round_policy=rating: il seeding è il rating decrescente.

        I rating sono in ordine inverso rispetto agli user_id, così l'ordine
        atteso non può nascere per caso dall'ordine di creazione.
        """
        players = _make_players(db_session, 4, ratings=[400, 500, 600, 700])
        gara = _make_gara(db_session, players, first_round_policy="rating")

        order = AmalfiStrategy().get_seeding_order(gara)

        assert order == [p.id for p in reversed(players)]

    def test_rating_policy_seeding_drives_round_1_ties(self, db_session):
        """Con policy rating, a parimerito vince chi ha il rating più alto."""
        a, b, c, d = _make_players(db_session, 4, ratings=[400, 500, 600, 700])
        gara = _make_gara(db_session, [a, b, c, d], first_round_policy="rating")

        strategy = AmalfiStrategy()
        SeedingService.ensure_seeding(gara.id, strategy.get_seeding_order(gara))

        _add_match(db_session, gara, 1, winner=a, loser=b)
        _add_match(db_session, gara, 1, winner=c, loser=d)
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        # c (600) davanti ad a (400) fra i vincitori; d (700) davanti a b (500)
        assert _positions(db_session, gara.id, 1) == [c.id, a.id, d.id, b.id]

    def test_random_policy_persists_a_seeding(self, db_session):
        """Con policy random il seeding è comunque salvato e completo."""
        players = _make_players(db_session, 5)
        gara = _make_gara(db_session, players)

        seeding = AmalfiStrategy()._get_first_round_classification(gara)

        assert len(seeding) == 5
        assert {rc.user_id for rc in seeding} == {p.id for p in players}
        assert [rc.position for rc in seeding] == [1, 2, 3, 4, 5]
        assert all(rc.round_number == SEEDING_ROUND for rc in seeding)

    def test_seeding_survives_in_database(self, db_session):
        """Il seeding non è più un oggetto volatile: finisce su DB."""
        players = _make_players(db_session, 4)
        gara = _make_gara(db_session, players)

        AmalfiStrategy()._get_first_round_classification(gara)
        db_session.flush()

        persisted = SeedingService.get_seeding(gara.id)
        assert len(persisted) == 4


@pytest.mark.unit
class TestSeedingIdempotency:
    """Riavviare il primo turno non deve rimescolare il sorteggio."""

    def test_ensure_seeding_is_idempotent(self, db_session):
        players = _make_players(db_session, 4)
        gara = _make_gara(db_session, players)
        ids = [p.id for p in players]

        first = SeedingService.ensure_seeding(gara.id, ids)
        second = SeedingService.ensure_seeding(gara.id, list(reversed(ids)))

        assert [rc.user_id for rc in first] == ids
        assert [rc.user_id for rc in second] == ids

    def test_second_call_does_not_duplicate_rows(self, db_session):
        """Il vincolo unique_round_classification non deve mai scattare."""
        players = _make_players(db_session, 4)
        gara = _make_gara(db_session, players)
        ids = [p.id for p in players]

        SeedingService.ensure_seeding(gara.id, ids)
        SeedingService.ensure_seeding(gara.id, ids)
        db_session.flush()

        assert len(SeedingService.get_seeding(gara.id)) == 4

    def test_repeated_first_round_generation_keeps_draw(self, db_session):
        """Rigenerare il primo turno riusa il sorteggio già estratto."""
        players = _make_players(db_session, 6)
        gara = _make_gara(db_session, players)
        strategy = AmalfiStrategy()

        first = [rc.user_id for rc in strategy._get_first_round_classification(gara)]
        second = [rc.user_id for rc in strategy._get_first_round_classification(gara)]

        assert first == second

    def test_duplicate_ids_in_order_are_ignored(self, db_session):
        players = _make_players(db_session, 3)
        gara = _make_gara(db_session, players)
        ids = [p.id for p in players]

        seeding = SeedingService.ensure_seeding(gara.id, ids + [ids[0]])

        assert [rc.user_id for rc in seeding] == ids
