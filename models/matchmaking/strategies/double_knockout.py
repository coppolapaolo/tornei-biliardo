"""
Module: models/matchmaking/strategies/double_knockout.py
Purpose: Double Knockout (double elimination) pairing strategy implementation
Requirements: SPECIFICHE.md - Double knockout tournament format
"""

from __future__ import annotations

import math
from typing import Sequence, List, Tuple, Optional, Dict, TYPE_CHECKING, Any

from .base import Pairing, ValidationResult, PairingStrategy, StrategyMetrics

if TYPE_CHECKING:
    from models.competition.models import Prova


class DoubleKnockoutStrategy(PairingStrategy):
    """Double Knockout (double elimination) pairing strategy."""

    # PairingStrategy metadata
    name = "double_knockout"
    display_name = "Double Knockout"
    description = "Double elimination tournament format with winners and losers bracket"
    min_players = 4
    max_players = 64
    supports_byes = True
    requires_classification = False

    def __init__(self):
        self.strategy_name = "double_knockout"

    def validate(self, prova: object) -> ValidationResult:
        """Validate if Double Knockout can be used for this prova."""
        try:
            # Get active inscriptions
            inscriptions = list(prova.inscriptions)  # type: ignore[arg-type]
            active_inscriptions = [i for i in inscriptions if i.status == "confirmed"]
            player_count = len(active_inscriptions)

            if player_count < 4:
                return ValidationResult(
                    ok=False, messages=("Double Knockout requires at least 4 players",)
                )

            if player_count > 64:
                return ValidationResult(
                    ok=False,
                    messages=(
                        "Double Knockout with more than 64 players may be impractical",
                    ),
                )

            # Calculate required rounds (approximately 2 * log2(n) rounds)
            required_rounds = self.get_total_rounds_needed(player_count)

            if (
                getattr(prova, "rounds_count", None) is not None
                and getattr(prova, "rounds_count") < required_rounds
            ):
                return ValidationResult(
                    ok=False,
                    messages=(
                        f"Double Knockout requires approximately {required_rounds} rounds, but prova has {getattr(prova, 'rounds_count', 'unknown')}",
                    ),
                )

            return ValidationResult(ok=True)

        except Exception as e:
            return ValidationResult(ok=False, messages=(f"Validation error: {str(e)}",))

    def preview(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Preview pairings for a specific round without side effects."""
        return self._generate_round_pairings(prova, round_number)  # type: ignore[arg-type]

    def propose(self, prova: object, round_number: int) -> Sequence[Pairing]:
        """Propose actual pairings for the round."""
        return self._generate_round_pairings(prova, round_number)  # type: ignore[arg-type]

    def _generate_round_pairings(
        self, prova: object, round_number: int
    ) -> List[Pairing]:
        """Generate pairings for a specific round using Double Knockout."""
        try:
            from typing import cast

            if round_number == 1:
                return self._generate_first_round_pairings(cast("Prova", prova))
            else:
                return self._generate_subsequent_round_pairings(
                    cast("Prova", prova), round_number
                )

        except Exception as e:
            print(f"Error generating Double Knockout pairings: {e}")
            return []

    def _generate_first_round_pairings(self, prova: "Prova") -> List[Pairing]:
        """Generate first round pairings (winners bracket only)."""
        from .direct_elimination import DirectEliminationStrategy

        # First round is identical to direct elimination
        de_strategy = DirectEliminationStrategy()
        return de_strategy._generate_first_round_pairings(prova)

    def _generate_subsequent_round_pairings(
        self, prova: "Prova", round_number: int
    ) -> List[Pairing]:
        """Generate pairings for subsequent rounds with winners and losers brackets."""
        from ...match.models import Match

        # Get all completed matches up to previous round
        # Use text() to create a raw SQL expression for the comparison to avoid mocking issues
        from sqlalchemy import text

        all_matches = (
            Match.query.filter_by(prova_id=prova.id, status="completed")
            .filter(text("round_number < :round_number"))
            .params(round_number=round_number)
            .all()
        )

        # Track player status: active, eliminated_once, eliminated_twice
        player_status = self._calculate_player_status(prova, all_matches)

        # Determine bracket phase
        bracket_info = self._determine_bracket_phase(prova, round_number, player_status)

        pairings = []

        if bracket_info["phase"] == "winners_bracket":
            pairings.extend(
                self._generate_winners_bracket_pairings(
                    prova, round_number, player_status, bracket_info
                )
            )
        elif bracket_info["phase"] == "losers_bracket":
            pairings.extend(
                self._generate_losers_bracket_pairings(
                    prova, round_number, player_status, bracket_info
                )
            )
        elif bracket_info["phase"] == "mixed":
            # Both brackets active
            pairings.extend(
                self._generate_winners_bracket_pairings(
                    prova, round_number, player_status, bracket_info
                )
            )
            pairings.extend(
                self._generate_losers_bracket_pairings(
                    prova, round_number, player_status, bracket_info
                )
            )
        elif bracket_info["phase"] == "grand_final":
            pairings.extend(
                self._generate_grand_final_pairings(prova, round_number, player_status)
            )

        return pairings

    def _calculate_player_status(self, prova: "Prova", matches: List) -> Dict[int, str]:
        """Calculate current status of each player."""
        player_status = {}

        # Get all players
        inscriptions = list(prova.inscriptions)  # type: ignore[arg-type]
        active_inscriptions = [i for i in inscriptions if i.status == "confirmed"]
        for inscription in active_inscriptions:
            player_status[inscription.user_id] = "active"

        # Track losses
        player_losses = {player_id: 0 for player_id in player_status.keys()}

        for match in matches:
            if match.winner_id and not match.is_bye:
                # Determine loser
                if match.player1_id == match.winner_id:
                    loser_id = match.player2_id
                else:
                    loser_id = match.player1_id

                if loser_id in player_losses:
                    player_losses[loser_id] += 1

                    if player_losses[loser_id] == 1:
                        player_status[loser_id] = "eliminated_once"
                    elif player_losses[loser_id] >= 2:
                        player_status[loser_id] = "eliminated_twice"

        return player_status

    def _determine_bracket_phase(
        self, prova: "Prova", round_number: int, player_status: Dict[int, str]
    ) -> Dict[str, Any]:
        """Determine which bracket phase we're in."""
        active_players = [
            pid for pid, status in player_status.items() if status == "active"
        ]
        eliminated_once = [
            pid for pid, status in player_status.items() if status == "eliminated_once"
        ]

        if len(active_players) > 1 and len(eliminated_once) > 1:
            return {
                "phase": "mixed",
                "winners_active": len(active_players),
                "losers_active": len(eliminated_once),
            }
        elif len(active_players) > 1:
            return {"phase": "winners_bracket", "players": active_players}
        elif len(eliminated_once) > 1:
            return {"phase": "losers_bracket", "players": eliminated_once}
        elif len(active_players) == 1 and len(eliminated_once) == 1:
            return {
                "phase": "grand_final",
                "winner_champ": active_players[0],
                "loser_champ": eliminated_once[0],
            }
        else:
            return {"phase": "finished"}

    def _generate_winners_bracket_pairings(
        self,
        prova: "Prova",
        round_number: int,
        player_status: Dict[int, str],
        bracket_info: Dict,
    ) -> List[Pairing]:
        """Generate winners bracket pairings."""
        active_players = [
            pid for pid, status in player_status.items() if status == "active"
        ]

        if len(active_players) < 2:
            return []

        # Get winners from previous winners bracket matches
        from ...match.models import Match

        previous_winners_matches = (
            Match.query.filter_by(
                prova_id=prova.id, round_number=round_number - 1, status="completed"
            )
            .filter(Match.notes != "losers_bracket")
            .all()
        )  # Assuming we mark losers bracket matches

        winners = []
        for match in previous_winners_matches:
            if match.winner_id and match.winner_id in active_players:
                winners.append(match.winner_id)

        # If this is early in tournament and we don't have enough previous matches,
        # just pair available active players
        if not winners:
            winners = active_players

        pairings = []
        winners = list(winners)

        while len(winners) >= 2:
            player1 = winners.pop(0)
            player2 = winners.pop(0)
            pairings.append(
                Pairing(players=(player1, player2), round_number=round_number)
            )

        # Handle odd winner
        if len(winners) == 1:
            pairings.append(
                Pairing(players=(winners[0],), is_bye=True, round_number=round_number)
            )

        return pairings

    def _generate_losers_bracket_pairings(
        self,
        prova: "Prova",
        round_number: int,
        player_status: Dict[int, str],
        bracket_info: Dict,
    ) -> List[Pairing]:
        """Generate losers bracket pairings."""
        eliminated_once = [
            pid for pid, status in player_status.items() if status == "eliminated_once"
        ]

        if len(eliminated_once) < 2:
            return []

        # Get recent losers from winners bracket
        from ...match.models import Match

        recent_losers = self._get_recent_winners_bracket_losers(prova, round_number)

        # Get survivors from previous losers bracket
        previous_losers_survivors = self._get_previous_losers_bracket_survivors(
            prova, round_number
        )

        # Combine and pair
        available_players = list(set(recent_losers + previous_losers_survivors))
        available_players = [p for p in available_players if p in eliminated_once]

        pairings = []
        while len(available_players) >= 2:
            player1 = available_players.pop(0)
            player2 = available_players.pop(0)
            # Mark as losers bracket match
            pairing = Pairing(players=(player1, player2), round_number=round_number)
            pairings.append(pairing)

        return pairings

    def _generate_grand_final_pairings(
        self, prova: "Prova", round_number: int, player_status: Dict[int, str]
    ) -> List[Pairing]:
        """Generate grand final pairing between winners and losers bracket champions."""
        active_players = [
            pid for pid, status in player_status.items() if status == "active"
        ]
        eliminated_once = [
            pid for pid, status in player_status.items() if status == "eliminated_once"
        ]

        if len(active_players) == 1 and len(eliminated_once) == 1:
            return [
                Pairing(
                    players=(active_players[0], eliminated_once[0]),
                    round_number=round_number,
                )
            ]

        return []

    def _get_recent_winners_bracket_losers(
        self, prova: "Prova", round_number: int
    ) -> List[int]:
        """Get players who just lost in winners bracket."""
        from ...match.models import Match

        # Look at recent winners bracket matches
        recent_matches = (
            Match.query.filter_by(
                prova_id=prova.id, round_number=round_number - 1, status="completed"
            )
            .filter(Match.notes != "losers_bracket")
            .all()
        )

        losers = []
        for match in recent_matches:
            if match.winner_id and not match.is_bye:
                if match.player1_id == match.winner_id:
                    losers.append(match.player2_id)
                else:
                    losers.append(match.player1_id)

        return losers

    def _get_previous_losers_bracket_survivors(
        self, prova: "Prova", round_number: int
    ) -> List[int]:
        """Get players who survived previous losers bracket round."""
        from ...match.models import Match

        # Look for losers bracket matches from previous round
        previous_losers_matches = (
            Match.query.filter_by(
                prova_id=prova.id, round_number=round_number - 1, status="completed"
            )
            .filter(Match.notes == "losers_bracket")
            .all()
        )

        survivors = []
        for match in previous_losers_matches:
            if match.winner_id:
                survivors.append(match.winner_id)

        return survivors

    def get_total_rounds_needed(self, player_count: int) -> int:
        """Calculate approximate total rounds needed for Double Knockout."""
        if player_count < 2:
            return 0

        # Winners bracket rounds
        winners_rounds = math.ceil(math.log2(player_count))

        # Losers bracket rounds (approximately same as winners)
        losers_rounds = winners_rounds

        # Grand final
        grand_final_rounds = 2  # Could be 1 or 2 depending on reset

        return winners_rounds + losers_rounds + grand_final_rounds

    def get_metrics(self) -> Optional[StrategyMetrics]:
        """Get performance metrics from last execution."""
        return None  # No metrics collection implemented yet


class DoubleKnockoutPairingStrategy(DoubleKnockoutStrategy):
    """Alias for compatibility with existing strategy registry."""

    pass
