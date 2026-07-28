"""Regression B14: il campo `RoundClassification.rack_difference` cambia
significato in base a `gara.classification_system`, NON a `matchmaking_strategy`.

Storicamente (pre-B14):
- `matchmaking_strategy == "random"` → salvava `racks_won` totali
- altrimenti → salvava la vera differenza (won - lost)

Conseguenza: una gara `random` + `classification_system=WINS` mostrava
nel template "Diff. Rack" un numero che era in realtà i rack vinti totali
(vedi scenario produzione 2026-05-20, screenshot utente: PAOLO/PIETRO
mostravano "+11" che era racks_won, non la diff reale +4).

Fix (PR successiva alla #3): la condizione usa `classification_system`,
coerente con `is_rack_only` nei template e con i sort key di
`gara_strategies.py`.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models import Gara, Inscription, Match, User
from models.classification.models import RoundClassification
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _setup_two_player_gara(db_session, matchmaking: str, classification: str) -> Gara:
    suffix = str(uuid.uuid4())[:8]
    director = User(
        username=f"director_{suffix}",
        email=f"director_{suffix}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("x")
    player_a = User(
        username=f"alpha_{suffix}",
        email=f"alpha_{suffix}@test.com",
        role=UserRole.PLAYER.value,
    )
    player_a.set_password("x")
    player_b = User(
        username=f"bravo_{suffix}",
        email=f"bravo_{suffix}@test.com",
        role=UserRole.PLAYER.value,
    )
    player_b.set_password("x")
    db_session.add_all([director, player_a, player_b])
    db_session.flush()

    gara = Gara(
        number=1,
        name=f"Gara B14 {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="palla_9",
        distance=5,
        is_race_to=True,
        director_id=director.id,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        matchmaking_strategy=matchmaking,
        classification_system=classification,
        status=GaraStatus.PLAYING.value,
    )
    db_session.add(gara)
    db_session.flush()

    for player in (player_a, player_b):
        db_session.add(
            Inscription(
                gara_id=gara.id,
                user_id=player.id,
                is_withdrawn=False,
                is_forfeit=False,
                is_waitlist=False,
            )
        )

    # Match con asimmetria forte: rack_won totali (11) ≠ rack_difference (+4)
    # player_a: vinto 11 rack totali, persi 7 → diff = +4
    # player_b: vinto 7 rack totali, persi 11 → diff = -4
    match1 = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=player_a.id,
        player2_id=player_b.id,
        player1_score=5,
        player2_score=3,
        winner_id=player_a.id,
        status=MatchStatus.COMPLETED.value,
    )
    match2 = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=player_a.id,
        player2_id=player_b.id,
        player1_score=6,
        player2_score=4,
        winner_id=player_a.id,
        status=MatchStatus.COMPLETED.value,
    )
    db_session.add_all([match1, match2])
    db_session.flush()
    gara._test_player_a_id = player_a.id  # type: ignore[attr-defined]
    gara._test_player_b_id = player_b.id  # type: ignore[attr-defined]
    return gara


@pytest.mark.unit
class TestB14FieldMeaningRegression:
    """Il campo rack_difference riflette classification_system, non matchmaking."""

    def test_random_with_wins_system_stores_true_rack_difference(self, db_session):
        """matchmaking=random + classification_system=WINS:
        rack_difference DEVE essere la vera differenza (won - lost), NON racks_won.

        Pre-fix: salvava 11 (racks_won totali). Post-fix: salva 4 (diff vera).
        """
        gara = _setup_two_player_gara(
            db_session, matchmaking="random", classification="WINS"
        )
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        rc_a = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, user_id=gara._test_player_a_id)
            .first()
        )
        assert rc_a is not None
        # player_a: rack_won=11, rack_lost=7 → diff=+4
        assert rc_a.rack_difference == 4, (
            f"Per classification_system=WINS deve essere la vera differenza (+4), "
            f"non racks_won (11). Got: {rc_a.rack_difference}"
        )

    def test_random_with_rack_system_stores_total_racks_won(self, db_session):
        """matchmaking=random + classification_system=RACK:
        rack_difference DEVE essere racks_won totali (semantica
        retro-compatibile con il vecchio comportamento Random).
        """
        gara = _setup_two_player_gara(
            db_session, matchmaking="random", classification="RACK"
        )
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        rc_a = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, user_id=gara._test_player_a_id)
            .first()
        )
        assert rc_a is not None
        # player_a: racks_won=11 → il campo deve essere 11 (label "Rack Totali")
        assert rc_a.rack_difference == 11, (
            f"Per classification_system=RACK deve essere racks_won (11). "
            f"Got: {rc_a.rack_difference}"
        )

    def test_amalfi_with_rack_system_stores_total_racks_won(self, db_session):
        """matchmaking=amalfi + classification_system=RACK:
        anche per Amalfi il campo deve seguire classification_system.
        Pre-fix Amalfi salvava sempre la diff (ignorando classification_system).
        """
        gara = _setup_two_player_gara(
            db_session, matchmaking="amalfi", classification="RACK"
        )
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        rc_a = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, user_id=gara._test_player_a_id)
            .first()
        )
        assert rc_a is not None
        assert rc_a.rack_difference == 11, (
            f"Amalfi+RACK deve salvare racks_won (11), non diff (+4). "
            f"Got: {rc_a.rack_difference}"
        )

    def test_amalfi_with_wins_system_stores_true_rack_difference(self, db_session):
        """matchmaking=amalfi + classification_system=WINS (default storico):
        comportamento standard, rack_difference = won - lost. Sanity check.
        """
        gara = _setup_two_player_gara(
            db_session, matchmaking="amalfi", classification="WINS"
        )
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        rc_a = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, user_id=gara._test_player_a_id)
            .first()
        )
        assert rc_a is not None
        assert rc_a.rack_difference == 4


@pytest.mark.unit
class TestB14AppliesToStrategyPathToo:
    """Il fix B14 vale anche per il percorso a strategie.

    `StrategyBasedClassificationService` è il secondo calcolatore di classifica
    di turno (lo usa la fusione di due utenti). Salvava sempre la differenza
    vera, ignorando `classification_system`: ricalcolare una gara RACK per quella
    via cambiava il significato della colonna sotto ai template e a
    SpareggioService.
    """

    def test_strategy_path_rack_system_stores_total_racks_won(self, db_session):
        from models.classification.gara_classification import (
            StrategyBasedClassificationService,
        )

        gara = _setup_two_player_gara(
            db_session, matchmaking="random", classification="RACK"
        )
        StrategyBasedClassificationService().calculate_round_classification(gara.id, 1)
        db_session.flush()

        rc_a = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, user_id=gara._test_player_a_id)
            .first()
        )
        assert rc_a is not None
        assert rc_a.rack_difference == 11, (
            f"Il percorso a strategie deve rispettare B14 come quello legacy: "
            f"racks_won (11), non diff (+4). Got: {rc_a.rack_difference}"
        )

    def test_strategy_path_wins_system_stores_true_difference(self, db_session):
        from models.classification.gara_classification import (
            StrategyBasedClassificationService,
        )

        gara = _setup_two_player_gara(
            db_session, matchmaking="amalfi", classification="WINS"
        )
        StrategyBasedClassificationService().calculate_round_classification(gara.id, 1)
        db_session.flush()

        rc_a = (
            db_session.query(RoundClassification)
            .filter_by(gara_id=gara.id, user_id=gara._test_player_a_id)
            .first()
        )
        assert rc_a is not None
        assert rc_a.rack_difference == 4

    def test_both_paths_agree_on_rack_system(self, db_session):
        """I due calcolatori devono produrre lo stesso valore in colonna."""
        from models.classification.gara_classification import (
            StrategyBasedClassificationService,
        )

        gara_legacy = _setup_two_player_gara(
            db_session, matchmaking="random", classification="RACK"
        )
        gara_strategy = _setup_two_player_gara(
            db_session, matchmaking="random", classification="RACK"
        )

        RoundClassification.calculate_classification_after_round(gara_legacy.id, 1)
        StrategyBasedClassificationService().calculate_round_classification(
            gara_strategy.id, 1
        )
        db_session.flush()

        def _value(gara):
            return (
                db_session.query(RoundClassification)
                .filter_by(gara_id=gara.id, user_id=gara._test_player_a_id)
                .first()
                .rack_difference
            )

        assert _value(gara_legacy) == _value(gara_strategy)
