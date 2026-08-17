"""I due calcolatori di classifica di turno devono produrre lo stesso risultato.

Storicamente esistevano due implementazioni parallele:

- `RoundClassification.calculate_classification_after_round` (marcata
  `.. deprecated::` ma usata da tutte le route di produzione)
- `StrategyBasedClassificationService.calculate_round_classification`
  (dichiarata "recommended" ma usata solo dalla fusione di due utenti)

Ogni correzione di dominio finiva in una sola delle due: B14 (semantica di
`rack_difference` nelle gare RACK) e il tiebreak SSR erano solo nella legacy,
il rispetto di ADR-027 sulla distanza dei trii e la gestione del walkover trio
erano solo in quella a strategie.

Questo file è la rete di sicurezza della consolidazione: fissa l'equivalenza su
uno spettro di scenari di dominio, così che unificare le due implementazioni sia
verificabile invece che sperato.
"""

from __future__ import annotations

import uuid
from datetime import date, time
from typing import List, Tuple

import pytest

from models import Gara, Inscription, Match, User
from models.classification.gara_classification import (
    StrategyBasedClassificationService,
)
from models.classification.models import GaraClassification, RoundClassification
from models.classification.seeding_service import SeedingService
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _players(db_session, count: int) -> List[User]:
    suffix = str(uuid.uuid4())[:8]
    users = []
    for i in range(count):
        user = User(
            username=f"p{i}_{suffix}",
            email=f"p{i}_{suffix}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("x")
        users.append(user)
    db_session.add_all(users)
    db_session.flush()
    return users


def _gara(
    db_session,
    players: List[User],
    classification_system: str = "WINS",
    matchmaking_strategy: str = "amalfi",
    distance: int = 5,
    is_multi_set: bool = False,
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
        name=f"Equivalence {suffix}",
        date=date(2026, 4, 1),
        time=time(18, 0),
        discipline="9_ball",
        distance=distance,
        is_race_to=True,
        is_multi_set=is_multi_set,
        match_distance=3 if is_multi_set else None,
        director_id=director.id,
        rounds_count=3,
        current_round=1,
        min_participants=len(players),
        matchmaking_strategy=matchmaking_strategy,
        classification_system=classification_system,
        first_round_policy="random",
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


def _match(db_session, gara, p1, p2, s1, s2, round_number=1, is_bye=False):
    winner = None
    if s1 > s2:
        winner = p1.id
    elif s2 > s1:
        winner = p2.id if p2 else None

    match = Match(
        gara_id=gara.id,
        round_number=round_number,
        player1_id=p1.id,
        player2_id=p2.id if p2 else None,
        player1_score=s1,
        player2_score=s2,
        winner_id=p1.id if is_bye else winner,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        is_bye=is_bye,
    )
    db_session.add(match)
    db_session.flush()
    return match


def _snapshot(db_session, gara_id: int, round_number: int) -> List[Tuple]:
    """Stato persistito della classifica, confrontabile fra i due calcolatori."""
    return [
        (
            rc.position,
            rc.user_id,
            rc.matches_won,
            rc.rack_difference,
            rc.racks_won,
        )
        for rc in db_session.query(RoundClassification)
        .filter_by(gara_id=gara_id, round_number=round_number)
        .order_by(RoundClassification.position)
        .all()
    ]


def _run_both(db_session, build_scenario) -> Tuple[List[Tuple], List[Tuple]]:
    """Costruisce due volte lo stesso scenario e lo calcola nei due modi.

    Due gare distinte invece di ricalcolare la stessa: così un calcolatore non
    può ereditare le righe scritte dall'altro.
    """
    gara_legacy = build_scenario()
    gara_strategy = build_scenario()

    RoundClassification.calculate_classification_after_round(gara_legacy.id, 1)
    StrategyBasedClassificationService().calculate_round_classification(
        gara_strategy.id, 1
    )
    db_session.flush()

    legacy = _snapshot(db_session, gara_legacy.id, 1)
    strategy = _snapshot(db_session, gara_strategy.id, 1)

    # Gli user_id differiscono fra le due gare: confronta la forma della
    # classifica (posizione, vittorie, valore rack) e la corrispondenza
    # posizionale, non gli id.
    return (
        [(pos, mw, rd, rw) for pos, _uid, mw, rd, rw in legacy],
        [(pos, mw, rd, rw) for pos, _uid, mw, rd, rw in strategy],
    )


@pytest.mark.unit
class TestCalculatorsEquivalence:
    """Stessi input di dominio → stessa classifica, con entrambi i calcolatori."""

    def test_regular_matches_wins_system(self, db_session):
        def build():
            a, b, c, d = _players(db_session, 4)
            gara = _gara(db_session, [a, b, c, d])
            _match(db_session, gara, a, b, 5, 3)
            _match(db_session, gara, c, d, 5, 1)
            return gara

        legacy, strategy = _run_both(db_session, build)
        assert legacy == strategy

    def test_tie_gives_nobody_a_win(self, db_session):
        def build():
            a, b = _players(db_session, 2)
            gara = _gara(db_session, [a, b])
            _match(db_session, gara, a, b, 4, 4)
            return gara

        legacy, strategy = _run_both(db_session, build)
        assert legacy == strategy
        assert all(matches_won == 0 for _pos, matches_won, _rd, _rw in legacy)

    def test_bye_match(self, db_session):
        def build():
            a, b, c = _players(db_session, 3)
            gara = _gara(db_session, [a, b, c])
            _match(db_session, gara, a, b, 5, 2)
            _match(db_session, gara, c, None, 5, 0, is_bye=True)
            return gara

        legacy, strategy = _run_both(db_session, build)
        assert legacy == strategy

    def test_rack_system_stores_total_racks(self, db_session):
        def build():
            a, b, c, d = _players(db_session, 4)
            gara = _gara(db_session, [a, b, c, d], classification_system="RACK")
            _match(db_session, gara, a, b, 5, 4)
            _match(db_session, gara, c, d, 5, 0)
            return gara

        legacy, strategy = _run_both(db_session, build)
        assert legacy == strategy
        # Le due colonne non si sovrascrivono più: il totale è sempre >= 0,
        # la differenza può essere negativa e resta disponibile.
        assert all(racks_won >= 0 for _pos, _mw, _rd, racks_won in legacy)
        assert any(rack_diff < 0 for _pos, _mw, rack_diff, _rw in legacy)

    def test_rack_system_ssr_tiebreak(self, db_session):
        """Lo SSR separa due giocatori con lo stesso totale rack.

        Era implementato solo nel calcolatore legacy. Lo scenario è costruito
        per essere discriminante: senza SSR vincerebbe `b`, che ha differenza
        rack nettamente migliore a parità di rack totali.
        """

        def build():
            a, b, c, d = _players(db_session, 4)
            gara = _gara(db_session, [a, b, c, d], classification_system="RACK")
            # Stessi rack totali (5), differenze diverse: a +1, b +5
            _match(db_session, gara, a, c, 5, 4)
            _match(db_session, gara, b, d, 5, 0)
            db_session.add(
                GaraClassification(
                    gara_id=gara.id, user_id=a.id, position=1, spot_shot_wins=3
                )
            )
            db_session.add(
                GaraClassification(
                    gara_id=gara.id, user_id=b.id, position=2, spot_shot_wins=0
                )
            )
            db_session.flush()
            gara._winner_by_ssr = a.id  # type: ignore[attr-defined]
            return gara

        gara_legacy = build()
        gara_strategy = build()

        RoundClassification.calculate_classification_after_round(gara_legacy.id, 1)
        StrategyBasedClassificationService().calculate_round_classification(
            gara_strategy.id, 1
        )
        db_session.flush()

        for gara in (gara_legacy, gara_strategy):
            first = (
                db_session.query(RoundClassification)
                .filter_by(gara_id=gara.id, round_number=1, position=1)
                .one()
            )
            assert first.user_id == gara._winner_by_ssr, (
                "Chi ha SSR più alto deve stare davanti a parità di rack totali "
                f"(gara {gara.id})"
            )

    def test_missing_ssr_sorts_after_zero(self, db_session):
        """Chi non ha tirato lo SSR ordina dopo chi ha tirato e fatto 0.

        Discriminante: `a` ha differenza rack migliore, quindi senza la
        convenzione "-1 = non ha tirato" starebbe davanti.
        """

        def build():
            a, b, c, d = _players(db_session, 4)
            gara = _gara(db_session, [a, b, c, d], classification_system="RACK")
            # Stessi rack totali (5), differenze diverse: a +5, b +1
            _match(db_session, gara, a, c, 5, 0)
            _match(db_session, gara, b, d, 5, 4)
            # Solo b ha un punteggio SSR, pari a 0. `a` non ha tirato.
            db_session.add(
                GaraClassification(
                    gara_id=gara.id, user_id=b.id, position=1, spot_shot_wins=0
                )
            )
            db_session.flush()
            gara._expected_first = b.id  # type: ignore[attr-defined]
            return gara

        gara_legacy = build()
        gara_strategy = build()

        RoundClassification.calculate_classification_after_round(gara_legacy.id, 1)
        StrategyBasedClassificationService().calculate_round_classification(
            gara_strategy.id, 1
        )
        db_session.flush()

        for gara in (gara_legacy, gara_strategy):
            first = (
                db_session.query(RoundClassification)
                .filter_by(gara_id=gara.id, round_number=1, position=1)
                .one()
            )
            assert first.user_id == gara._expected_first

    def test_seeding_tiebreak_is_honoured_by_both(self, db_session):
        """Anche il parimerito per classifica di partenza deve coincidere."""

        def build():
            a, b, c, d = _players(db_session, 4)
            gara = _gara(db_session, [a, b, c, d])
            SeedingService.ensure_seeding(gara.id, [d.id, c.id, b.id, a.id])
            _match(db_session, gara, a, b, 5, 3)
            _match(db_session, gara, c, d, 5, 3)
            expected = [c.id, a.id, d.id, b.id]
            gara._expected_order = expected  # type: ignore[attr-defined]
            return gara

        gara_legacy = build()
        gara_strategy = build()

        RoundClassification.calculate_classification_after_round(gara_legacy.id, 1)
        StrategyBasedClassificationService().calculate_round_classification(
            gara_strategy.id, 1
        )
        db_session.flush()

        for gara in (gara_legacy, gara_strategy):
            order = [
                rc.user_id
                for rc in db_session.query(RoundClassification)
                .filter_by(gara_id=gara.id, round_number=1)
                .order_by(RoundClassification.position)
                .all()
            ]
            assert order == gara._expected_order

    def test_cumulative_across_two_rounds(self, db_session):
        """L'aggregazione è cumulativa fino al turno richiesto in entrambi."""

        def build():
            a, b, c, d = _players(db_session, 4)
            gara = _gara(db_session, [a, b, c, d])
            _match(db_session, gara, a, b, 5, 3, round_number=1)
            _match(db_session, gara, c, d, 5, 1, round_number=1)
            _match(db_session, gara, a, c, 5, 4, round_number=2)
            _match(db_session, gara, b, d, 5, 2, round_number=2)
            return gara

        gara_legacy = build()
        gara_strategy = build()

        RoundClassification.calculate_classification_after_round(gara_legacy.id, 2)
        StrategyBasedClassificationService().calculate_round_classification(
            gara_strategy.id, 2
        )
        db_session.flush()

        legacy = [
            (p, mw, rd, rw)
            for p, _u, mw, rd, rw in _snapshot(db_session, gara_legacy.id, 2)
        ]
        strategy = [
            (p, mw, rd, rw)
            for p, _u, mw, rd, rw in _snapshot(db_session, gara_strategy.id, 2)
        ]
        assert legacy == strategy

    def test_stale_rows_are_removed(self, db_session):
        """Un giocatore senza più match validi sparisce dalla classifica."""
        a, b, c, d = _players(db_session, 4)
        gara = _gara(db_session, [a, b, c, d])
        match_cd = _match(db_session, gara, c, d, 5, 1)
        _match(db_session, gara, a, b, 5, 3)

        service = StrategyBasedClassificationService()
        service.calculate_round_classification(gara.id, 1)
        db_session.flush()
        assert len(_snapshot(db_session, gara.id, 1)) == 4

        # c e d tornano senza risultato: devono uscire dalla classifica
        match_cd.status = MatchStatus.PENDING.value
        match_cd.winner_id = None
        db_session.add(match_cd)
        db_session.flush()

        service.calculate_round_classification(gara.id, 1)
        db_session.flush()

        remaining = {
            uid for _pos, uid, _mw, _rd, _rw in _snapshot(db_session, gara.id, 1)
        }
        assert remaining == {a.id, b.id}
