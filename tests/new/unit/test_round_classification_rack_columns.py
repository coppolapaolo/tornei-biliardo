"""Le due colonne rack hanno significato fisso, e le righe storiche reggono.

`rack_difference` è sempre la differenza, `racks_won` sempre il totale. Chi
legge sceglie quale guardare tramite `ranking_rack_value`, unico punto che
conosce `gara.classification_system`.

Le righe scritte prima della separazione (migration 20260728) hanno
`racks_won` NULL nelle gare WINS, e nelle gare RACK il totale copiato dal
vecchio valore. Il fallback deve restituire il numero giusto in entrambi i casi,
altrimenti le gare già chiuse mostrerebbero zeri.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models import Gara, Inscription, Match, User
from models.classification.models import RoundClassification
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _gara_with_result(db_session, classification_system: str) -> Gara:
    """Gara a due giocatori dove totale (11) e differenza (+4) non coincidono."""
    suffix = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{suffix}",
        email=f"dir_{suffix}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("x")
    player_a = User(
        username=f"a_{suffix}", email=f"a_{suffix}@test.com", role=UserRole.PLAYER.value
    )
    player_a.set_password("x")
    player_b = User(
        username=f"b_{suffix}", email=f"b_{suffix}@test.com", role=UserRole.PLAYER.value
    )
    player_b.set_password("x")
    db_session.add_all([director, player_a, player_b])
    db_session.flush()

    gara = Gara(
        number=1,
        name=f"Rack columns {suffix}",
        date=date(2026, 5, 1),
        time=time(18, 0),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=director.id,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        matchmaking_strategy="amalfi",
        classification_system=classification_system,
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

    # a: 11 rack vinti, 7 persi → totale 11, differenza +4
    for scores in ((5, 3), (6, 4)):
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=player_a.id,
                player2_id=player_b.id,
                player1_score=scores[0],
                player2_score=scores[1],
                winner_id=player_a.id,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
    db_session.flush()

    gara._player_a_id = player_a.id  # type: ignore[attr-defined]
    return gara


def _row_for_a(db_session, gara) -> RoundClassification:
    return (
        db_session.query(RoundClassification)
        .filter_by(gara_id=gara.id, user_id=gara._player_a_id)
        .one()
    )


@pytest.mark.unit
class TestRackColumnsHaveFixedMeaning:
    """Ogni colonna una grandezza, sempre la stessa."""

    @pytest.mark.parametrize("classification_system", ["WINS", "RACK", "POSITION"])
    def test_both_columns_are_populated(self, db_session, classification_system):
        gara = _gara_with_result(db_session, classification_system)
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        row = _row_for_a(db_session, gara)
        assert row.racks_won == 11, "il totale non dipende dal sistema di classifica"
        assert row.rack_difference == 4, "la differenza non dipende dal sistema"

    def test_ranking_value_is_total_for_rack_gare(self, db_session):
        gara = _gara_with_result(db_session, "RACK")
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        row = _row_for_a(db_session, gara)
        assert row.is_rack_ranking is True
        assert row.ranking_rack_value == 11

    @pytest.mark.parametrize("classification_system", ["WINS", "POSITION"])
    def test_ranking_value_is_difference_otherwise(
        self, db_session, classification_system
    ):
        gara = _gara_with_result(db_session, classification_system)
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        row = _row_for_a(db_session, gara)
        assert row.is_rack_ranking is False
        assert row.ranking_rack_value == 4


@pytest.mark.unit
class TestLegacyRowsFallback:
    """Righe scritte prima della separazione delle colonne."""

    def test_rack_gara_legacy_row_uses_old_column(self, db_session):
        """Gara RACK storica: `racks_won` NULL, il totale sta in rack_difference.

        È lo stato in cui la migration lascia le righe che non riesce a
        popolare, e quello di qualunque riga scritta dal codice precedente.
        """
        gara = _gara_with_result(db_session, "RACK")
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        row = _row_for_a(db_session, gara)
        # Simula la riga storica: totale dentro rack_difference, racks_won assente
        row.rack_difference = 11
        row.racks_won = None
        db_session.flush()

        assert row.ranking_rack_value == 11

    def test_wins_gara_legacy_row_uses_difference(self, db_session):
        """Gara WINS storica: `racks_won` NULL, ma la classifica non lo usa."""
        gara = _gara_with_result(db_session, "WINS")
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        row = _row_for_a(db_session, gara)
        row.racks_won = None
        db_session.flush()

        assert row.ranking_rack_value == 4

    def test_recalculation_heals_legacy_row(self, db_session):
        """Un ricalcolo riscrive entrambe le colonne con la semantica nuova."""
        gara = _gara_with_result(db_session, "RACK")
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        row = _row_for_a(db_session, gara)
        row.rack_difference = 11  # valore stantio in stile pre-separazione
        row.racks_won = None
        db_session.flush()

        RoundClassification.calculate_classification_after_round(gara.id, 1)
        db_session.flush()

        healed = _row_for_a(db_session, gara)
        assert healed.racks_won == 11
        assert healed.rack_difference == 4
