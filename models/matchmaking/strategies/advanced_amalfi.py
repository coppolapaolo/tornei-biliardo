from __future__ import annotations
from typing import Sequence, Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from .base import BaseStrategy, Pairing, ValidationResult
from models.competition.models import Prova
from models.challenge.models import Challenge
from models.user.models import User
from models.classification.models import RoundClassification
from models.matchmaking.strategies.amalfi_adapter import AmalfiStrategy


@dataclass
class AdvancedPairingOptions:
    """Options for advanced pairing generation."""

    allow_x_replacement: bool = True
    allow_trio_matches: bool = True
    use_challenges_for_x: bool = True
    use_individual_matches_for_x: bool = True
    max_trio_size: int = 3
    anti_rematch_weight: float = 0.8


class AdvancedAmalfiStrategy(BaseStrategy):
    """Advanced Amalfi strategy with X-replacement, trio matches, and anti-rematch logic."""

    # Strategy metadata
    name = "advanced_amalfi"
    display_name = "Advanced Amalfi"
    description = (
        "Amalfi algorithm with X-replacement, trio matches, and enhanced anti-rematch"
    )
    min_players = 2
    max_players = None
    supports_byes = True
    requires_classification = True

    def __init__(self, base_amalfi_strategy: AmalfiStrategy):
        super().__init__()
        self._base_strategy = base_amalfi_strategy
        self._options = AdvancedPairingOptions()

    def validate(self, prova: object) -> ValidationResult:
        """Validate prova for advanced Amalfi strategy."""
        # Cast to Prova for type safety
        prova_obj: Prova = prova  # type: ignore

        # Use base strategy validation
        base_result = self._base_strategy.validate(prova)

        # Get strategy-specific validation
        strategy_validation = self._validate_strategy_specific(prova_obj)

        # Combine results
        all_errors = list(base_result.errors) + strategy_validation.get("errors", [])
        all_warnings = list(base_result.warnings) + strategy_validation.get(
            "warnings", []
        )

        if all_errors:
            return ValidationResult.failure(all_errors, all_warnings)
        else:
            return ValidationResult.success(
                messages=list(base_result.messages) + all_warnings,
                warnings=all_warnings,
            )

    def _validate_strategy_specific(self, prova: object) -> Dict[str, List[str]]:
        """Validate prova for advanced Amalfi strategy."""
        # Cast to Prova for type safety
        prova_obj: Prova = prova  # type: ignore

        errors = []
        warnings = []

        # Use base validation first
        base_validation = self._base_strategy.validate(prova)
        if not base_validation.ok:
            errors.extend(base_validation.errors)
            warnings.extend(base_validation.warnings)

        # Additional validations for advanced features
        if self._options.allow_trio_matches and prova_obj.without_x:
            warnings.append("Trio matches enabled with 'without X' mode - may conflict")

        return {"errors": errors, "warnings": warnings}

    def _generate_pairings(
        self,
        processed_data: Dict[str, Any],
        round_number: int,
        preview_mode: bool = True,
    ) -> Sequence[Pairing]:
        """Generate advanced pairings with X-replacement and trio support."""
        prova: Prova = processed_data["prova"]

        # Get base Amalfi pairings
        base_pairings = self._base_strategy._generate_pairings(
            processed_data, round_number, preview_mode
        )

        # Enhance pairings with advanced features
        enhanced_pairings = []

        for pairing in base_pairings:
            if (
                pairing.is_bye
                and self._options.allow_x_replacement
                and pairing.player1_id is not None
            ):
                # Try to replace X with alternative
                replacement = self._generate_x_replacement(
                    prova, pairing.player1_id, round_number, preview_mode
                )
                if replacement:
                    enhanced_pairings.append(replacement)
                else:
                    enhanced_pairings.append(pairing)
            elif len(pairing.players) > 2 and self._options.allow_trio_matches:
                # Handle trio matches
                trio_pairing = self._enhance_trio_match(pairing, prova, round_number)
                enhanced_pairings.append(trio_pairing)
            else:
                enhanced_pairings.append(pairing)

        return enhanced_pairings

    def _generate_x_replacement(
        self, prova: Prova, player_id: int, round_number: int, preview_mode: bool
    ) -> Optional[Pairing]:
        """Generate X replacement using challenges or individual matches."""

        # Try challenge-based replacement first
        if self._options.use_challenges_for_x:
            challenge_replacement = self._try_challenge_replacement(
                prova, player_id, round_number, preview_mode
            )
            if challenge_replacement:
                return challenge_replacement

        # Try individual match replacement
        if self._options.use_individual_matches_for_x:
            individual_replacement = self._try_individual_match_replacement(
                prova, player_id, round_number, preview_mode
            )
            if individual_replacement:
                return individual_replacement

        return None

    def _try_challenge_replacement(
        self, prova: Prova, player_id: int, round_number: int, preview_mode: bool
    ) -> Optional[Pairing]:
        """Try to replace X with a challenge."""
        # Find suitable challenge for this player
        suitable_challenge = self._find_suitable_challenge(prova, player_id)

        if suitable_challenge:
            # Create a "challenge pairing" that will be handled specially
            challenge_pairing = Pairing(
                players=(player_id,),
                is_bye=False,  # Not a bye, but a special challenge match
                round_number=round_number,
                pairing_quality=0.9,  # High quality as it's meaningful
                estimated_duration=20,  # Challenge duration
                requires_handicap=False,
                notes=f"Challenge: {suitable_challenge.name}",
            )
            return challenge_pairing

        return None

    def _try_individual_match_replacement(
        self, prova: Prova, player_id: int, round_number: int, preview_mode: bool
    ) -> Optional[Pairing]:
        """Try to replace X with an individual match."""
        # Find suitable opponent for individual match
        suitable_opponent = self._find_suitable_opponent(prova, player_id, round_number)

        if suitable_opponent:
            # Create individual match pairing
            individual_pairing = Pairing(
                players=(player_id, suitable_opponent),
                is_bye=False,
                round_number=round_number,
                pairing_quality=0.7,  # Medium quality
                estimated_duration=45,  # Individual match duration
                requires_handicap=True,  # May need handicap
                notes="Individual match replacement for X",
            )
            return individual_pairing

        return None

    def _enhance_trio_match(
        self, pairing: Pairing, prova: Prova, round_number: int
    ) -> Pairing:
        """Enhance trio match with additional metadata."""
        # Add trio-specific metadata
        trio_pairing = Pairing(
            players=pairing.players,
            is_bye=pairing.is_bye,
            round_number=pairing.round_number,
            pairing_quality=0.6,  # Lower quality due to complexity
            estimated_duration=60,  # Trio match duration
            requires_handicap=True,  # Trio matches often need handicap
            notes="Trio match (3 players)",
        )
        return trio_pairing

    def _find_suitable_challenge(
        self, prova: Prova, player_id: int
    ) -> Optional[Challenge]:
        """Find a suitable challenge for X replacement."""
        # Look for challenges that are appropriate for this player and prova
        from models.challenge.services import ChallengeService

        try:
            # Get challenges suitable for X replacement
            suitable_challenge = ChallengeService.get_challenge_for_x_replacement(
                prova.id
            )

            return suitable_challenge
        except Exception:
            # If challenge service is not available, return None
            pass

        return None

    def _find_suitable_opponent(
        self, prova: Prova, player_id: int, round_number: int
    ) -> Optional[int]:
        """Find a suitable opponent for individual match replacement."""
        # Get players who also have bye or are available
        active_players = self._get_active_players(prova)

        # Exclude current player
        other_players = [p for p in active_players if p != player_id]

        if not other_players:
            return None

        # Try to find player with similar ranking
        if round_number > 1:
            similar_ranked = self._find_similar_ranked_player(
                player_id, other_players, prova.id, round_number
            )
            if similar_ranked:
                return similar_ranked

        # Return first available player
        return other_players[0] if other_players else None

    def _get_active_players(self, prova: Prova) -> List[int]:
        """Get list of active player IDs."""
        # Handle the relationship properly
        inscriptions = getattr(prova, "inscriptions", [])
        if not inscriptions:
            return []

        try:
            # Try to iterate over the relationship directly
            return [
                inscription.user_id
                for inscription in inscriptions
                if not getattr(inscription, "is_withdrawn", False)
            ]
        except Exception:
            # Fallback to empty list
            return []

    def _find_similar_ranked_player(
        self, player_id: int, candidate_ids: List[int], prova_id: int, round_number: int
    ) -> Optional[int]:
        """Find player with similar ranking."""
        try:
            # Get current round classifications
            classifications = RoundClassification.query.filter_by(
                prova_id=prova_id, round_number=round_number - 1
            ).all()

            # Create position mapping
            positions = {c.user_id: c.position for c in classifications}

            player_position = positions.get(player_id, 0)

            # Find player with closest position
            best_match = None
            min_diff = float("inf")

            for candidate_id in candidate_ids:
                candidate_position = positions.get(candidate_id, 0)
                diff = abs(candidate_position - player_position)
                if diff < min_diff:
                    min_diff = diff
                    best_match = candidate_id

            return best_match
        except Exception:
            # If classification data is not available, return None
            return None

    def _apply_side_effects(
        self, pairings: Sequence[Pairing], prova: object, round_number: int
    ) -> None:
        """Apply side effects for advanced pairings."""
        # Cast to Prova for type safety
        prova_obj: Prova = prova  # type: ignore

        # Let base strategy handle standard side effects
        self._base_strategy._apply_side_effects(pairings, prova, round_number)

        # Apply additional side effects for advanced features
        for pairing in pairings:
            if "Challenge:" in (pairing.notes or ""):
                # Record challenge assignment
                self._record_challenge_assignment(prova_obj, pairing, round_number)
            elif "Individual match" in (pairing.notes or ""):
                # Record individual match intention
                self._record_individual_match_intention(
                    prova_obj, pairing, round_number
                )

    def _record_challenge_assignment(
        self, prova: Prova, pairing: Pairing, round_number: int
    ) -> None:
        """Record challenge assignment for X replacement."""
        # This would typically update some tracking system
        pass

    def _record_individual_match_intention(
        self, prova: Prova, pairing: Pairing, round_number: int
    ) -> None:
        """Record intention to create individual match for X replacement."""
        # This would typically update some tracking system
        pass

    def _postprocess_pairings(
        self, pairings: Sequence[Pairing], prova: object, round_number: int
    ) -> Sequence[Pairing]:
        """Postprocess pairings with quality improvements."""
        # Cast to Prova for type safety
        prova_obj: Prova = prova  # type: ignore

        # Apply anti-rematch logic to improve pairing quality
        enhanced_pairings = []

        for pairing in pairings:
            if not pairing.is_bye and len(pairing.players) >= 2:
                # Calculate enhanced quality based on anti-rematch
                quality = self._calculate_enhanced_pairing_quality(
                    pairing, prova_obj, round_number
                )

                enhanced_pairing = Pairing(
                    players=pairing.players,
                    is_bye=pairing.is_bye,
                    round_number=pairing.round_number,
                    pairing_quality=quality,
                    estimated_duration=pairing.estimated_duration,
                    requires_handicap=pairing.requires_handicap,
                    notes=pairing.notes,
                )
                enhanced_pairings.append(enhanced_pairing)
            else:
                enhanced_pairings.append(pairing)

        return enhanced_pairings

    def _calculate_enhanced_pairing_quality(
        self, pairing: Pairing, prova: Prova, round_number: int
    ) -> float:
        """Calculate enhanced pairing quality with anti-rematch consideration."""
        base_quality = pairing.pairing_quality or 0.5

        # Check if players have played before (anti-rematch)
        from models.classification.models import PlayerEncounter

        if len(pairing.players) >= 2:
            player1_id, player2_id = pairing.players[0], pairing.players[1]
            have_played = PlayerEncounter.have_played(prova.id, player1_id, player2_id)

            if have_played:
                # Reduce quality for rematch
                return base_quality * self._options.anti_rematch_weight

        return base_quality
