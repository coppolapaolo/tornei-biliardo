"""Regressione issue #63 — SSR con gruppi di 3+ giocatori.

Lo spareggio serve a decidere le posizioni entro
``tiebreaker_until_position``: pretendere punteggi tutti diversi costringeva
il director a inventare punti per separare giocatori che nessuno deve
separare (nell'issue: FLAVIO promosso a 1 punto solo per non pareggiare con
LAURA B, entrambi fuori dal podio).
"""

import pytest

from models.competition.spareggio_service import SpareggioService


@pytest.mark.unit
class TestPositionsToDiscriminate:
    """Quante posizioni in cima al gruppo lo SSR deve separare davvero."""

    def test_group_at_limit_needs_only_a_winner(self):
        """Scenario dell'issue: 4 giocatori parimerito al 3° posto, limite 3.

        Solo il 3° posto è conteso: basta un vincitore netto.
        """
        assert (
            SpareggioService.positions_to_discriminate(
                group_size=4, group_position=3, tiebreaker_limit=3
            )
            == 1
        )

    def test_group_from_first_needs_full_podium(self):
        """4 parimerito dalla 1ª posizione con limite 3: servono 3 separazioni."""
        assert (
            SpareggioService.positions_to_discriminate(
                group_size=4, group_position=1, tiebreaker_limit=3
            )
            == 3
        )

    def test_pair_always_needs_one_separation(self):
        assert (
            SpareggioService.positions_to_discriminate(
                group_size=2, group_position=1, tiebreaker_limit=3
            )
            == 1
        )

    def test_single_player_group_needs_nothing(self):
        assert (
            SpareggioService.positions_to_discriminate(
                group_size=1, group_position=1, tiebreaker_limit=3
            )
            == 0
        )

    def test_never_exceeds_group_size_minus_one(self):
        """Un gruppo di 2 dalla 1ª con limite 5 richiede comunque 1 sola."""
        assert (
            SpareggioService.positions_to_discriminate(
                group_size=2, group_position=1, tiebreaker_limit=5
            )
            == 1
        )


@pytest.mark.unit
class TestScoresResolveGroup:
    """Regola di risoluzione applicata ai punteggi."""

    def test_issue_scenario_accepts_tie_below_podium(self):
        """MARCO 2, LEONARDO 1, LAURA B 0, FLAVIO 0 → risolto (k=1)."""
        assert SpareggioService.scores_resolve_group([2, 1, 0, 0], 1) is True

    def test_tied_top_is_not_resolved(self):
        """Due a pari in testa: il posto conteso resta indeciso."""
        assert SpareggioService.scores_resolve_group([2, 2, 0, 0], 1) is False

    def test_missing_score_is_not_resolved(self):
        assert SpareggioService.scores_resolve_group([2, None, 0], 1) is False

    def test_zero_is_a_valid_score(self):
        assert SpareggioService.scores_resolve_group([1, 0], 1) is True

    def test_tie_at_second_place_blocks_when_two_needed(self):
        """Con k=2 anche il 2° posto è conteso: 3,1,1 non basta."""
        assert SpareggioService.scores_resolve_group([3, 1, 1], 2) is False
        assert SpareggioService.scores_resolve_group([3, 2, 1], 2) is True


@pytest.mark.unit
class TestValidateSsrScoresForGroup:
    """La validazione lato salvataggio segue la stessa regola."""

    def test_accepts_ties_outside_contested_positions(self):
        scores = {1: 2, 2: 1, 3: 0, 4: 0}
        is_valid, error = SpareggioService.validate_ssr_scores_for_group(
            scores, needs_distinct_top=1
        )
        assert is_valid is True
        assert error == ""

    def test_rejects_shared_top_score(self):
        scores = {1: 2, 2: 2, 3: 0}
        is_valid, error = SpareggioService.validate_ssr_scores_for_group(
            scores, needs_distinct_top=1
        )
        assert is_valid is False
        assert "vincitore" in error

    def test_negative_scores_still_rejected(self):
        scores = {1: 2, 2: -1}
        is_valid, error = SpareggioService.validate_ssr_scores_for_group(
            scores, needs_distinct_top=1
        )
        assert is_valid is False
        assert "non negativi" in error

    def test_default_keeps_all_distinct_behaviour(self):
        """Senza needs_distinct_top resta la regola storica "tutti diversi"."""
        is_valid, _error = SpareggioService.validate_ssr_scores_for_group({1: 0, 2: 0})
        assert is_valid is False


@pytest.mark.unit
class TestIsGroupResolved:
    def test_uses_needs_distinct_top_from_group(self):
        group = {
            "position": 3,
            "rack_totali": 10,
            "needs_distinct_top": 1,
            "players": [
                {"user_id": 1, "username": "MARCO", "current_ssr_score": 2},
                {"user_id": 2, "username": "LEONARDO", "current_ssr_score": 1},
                {"user_id": 3, "username": "LAURA B", "current_ssr_score": 0},
                {"user_id": 4, "username": "FLAVIO", "current_ssr_score": 0},
            ],
        }
        assert SpareggioService.is_group_resolved(group) is True
