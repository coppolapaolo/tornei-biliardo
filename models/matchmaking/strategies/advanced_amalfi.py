from __future__ import annotations
from typing import Sequence, Dict, Any, List, Optional
from dataclasses import dataclass

from .base import BaseStrategy, Pairing, ValidationResult
from models.competition.models import Gara
from models.challenge.models import Challenge
from models.classification.models import RoundClassification
from models.matchmaking.strategies.amalfi_adapter import AmalfiStrategy


@dataclass
class AdvancedPairingOptions:
    """Configuration options for advanced Amalfi pairing strategy enhancements.

    Controls sophisticated tournament features that go beyond basic pairing:
    X-replacement alternatives, trio match handling, and enhanced anti-rematch logic.
    These options enable tournament directors to optimize player engagement and
    competitive balance based on specific tournament objectives.
    """

    allow_x_replacement: bool = True  # Enable bye alternatives (challenges, individual matches)
    allow_trio_matches: bool = True  # Support three-player matches for odd counts
    use_challenges_for_x: bool = True  # Offer skill challenges as bye replacement
    use_individual_matches_for_x: bool = True  # Enable casual matches during byes
    max_trio_size: int = 3  # Maximum players per trio match
    anti_rematch_weight: float = 0.8  # Quality penalty for repeated pairings (0.0-1.0)


class AdvancedAmalfiStrategy(BaseStrategy):
    """Enhanced Amalfi strategy with community engagement and advanced tournament features.

    Extends the sophisticated Amalfi algorithm with modern tournament management
    capabilities including X-replacement systems (bye alternatives), trio match
    support, and enhanced anti-rematch intelligence. Designed for competitive
    pool tournaments that prioritize player engagement and community building.

    Advanced Features:
    - X-replacement: Challenges and individual matches instead of sitting out
    - Trio matches: Three-player formats to minimize byes
    - Enhanced anti-rematch: Weighted quality assessment for rematch avoidance
    - Challenge integration: Skill development opportunities during tournament
    - Individual match support: Casual play opportunities for community building

    Design Pattern: Decorator (enhances base Amalfi) + Strategy + Template Method
    Business Context: Competitive American Pool tournaments with community focus
    """

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
        """Initialize advanced strategy as decorator over base Amalfi algorithm.

        Args:
            base_amalfi_strategy: Core Amalfi algorithm to enhance with advanced features
        """
        super().__init__()
        self._base_strategy = base_amalfi_strategy
        self._options = AdvancedPairingOptions()

    def validate(self, gara: object) -> ValidationResult:
        """Validate tournament configuration for advanced Amalfi strategy requirements.

        Combines base Amalfi validation with advanced feature compatibility checks.
        Ensures tournament settings support enhanced features like trio matches,
        challenge integration, and X-replacement systems.

        Args:
            gara: Tournament object to validate against advanced requirements

        Returns:
            ValidationResult with comprehensive feedback on configuration compatibility
        """
        # Cast to Gara for type safety
        gara_obj: Gara = gara  # type: ignore

        # Use base strategy validation
        base_result = self._base_strategy.validate(gara)

        # Get strategy-specific validation
        strategy_validation = self._validate_strategy_specific(gara_obj)

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

    def _validate_strategy_specific(self, gara: object) -> Dict[str, List[str]]:
        """Validate gara for advanced Amalfi strategy."""
        # Cast to Gara for type safety
        gara_obj: Gara = gara  # type: ignore

        errors = []
        warnings = []

        # Use base validation first
        base_validation = self._base_strategy.validate(gara)
        if not base_validation.ok:
            errors.extend(base_validation.errors)
            warnings.extend(base_validation.warnings)

        # Check compatibility between advanced features and tournament settings
        if self._options.allow_trio_matches and gara_obj.without_x:
            warnings.append(
                "Trio matches enabled with 'without X' mode - configuration may need review"
            )

        return {"errors": errors, "warnings": warnings}

    def _generate_pairings(
        self,
        processed_data: Dict[str, Any],
        round_number: int,
        preview_mode: bool = True,
    ) -> Sequence[Pairing]:
        """Generate advanced pairings with X-replacement and trio support."""
        gara: Gara = processed_data["gara"]

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
                    gara, pairing.player1_id, round_number, preview_mode
                )
                if replacement:
                    enhanced_pairings.append(replacement)
                else:
                    enhanced_pairings.append(pairing)
            elif len(pairing.players) > 2 and self._options.allow_trio_matches:
                # Handle trio matches
                trio_pairing = self._enhance_trio_match(pairing, gara, round_number)
                enhanced_pairings.append(trio_pairing)
            else:
                enhanced_pairings.append(pairing)

        return enhanced_pairings

    def _generate_x_replacement(
        self, gara: Gara, player_id: int, round_number: int, preview_mode: bool
    ) -> Optional[Pairing]:
        """Generate meaningful activity alternatives for players who would receive a bye.

        X-replacement maximizes player engagement by offering skill challenges or
        individual matches instead of sitting idle. This maintains tournament momentum
        while providing additional competitive and social opportunities.

        Replacement Priority:
        1. Skill challenges: Individual practice with tournament scoring integration
        2. Individual matches: Casual games with available players

        Args:
            gara: Tournament context with available challenges and players
            player_id: Player receiving the bye who needs alternative activity
            round_number: Current round number for context
            preview_mode: Whether this is preview (no side effects) or execution

        Returns:
            Alternative Pairing object, or None if no suitable replacement available
        """

        # Priority 1: Skill challenges provide individual development opportunities
        if self._options.use_challenges_for_x:
            challenge_replacement = self._try_challenge_replacement(
                gara, player_id, round_number, preview_mode
            )
            if challenge_replacement:
                return challenge_replacement

        # Priority 2: Individual matches maintain social and competitive engagement
        if self._options.use_individual_matches_for_x:
            individual_replacement = self._try_individual_match_replacement(
                gara, player_id, round_number, preview_mode
            )
            if individual_replacement:
                return individual_replacement

        return None

    def _try_challenge_replacement(
        self, gara: Gara, player_id: int, round_number: int, preview_mode: bool
    ) -> Optional[Pairing]:
        """Attempt to replace bye with skill challenge for individual development.

        Challenges provide structured skill practice that integrates with tournament
        scoring while keeping players engaged. This approach transforms downtime
        into valuable training opportunities.

        Returns:
            Challenge-based Pairing with high quality score (meaningful activity)
        """
        # Locate appropriate skill challenge matching player level and tournament context
        suitable_challenge = self._find_suitable_challenge(gara, player_id)

        if suitable_challenge:
            # Create challenge pairing with high engagement value
            challenge_pairing = Pairing(
                players=(player_id,),
                is_bye=False,  # Challenge activity, not idle time
                round_number=round_number,
                pairing_quality=0.9,  # High quality due to skill development value
                estimated_duration=20,  # Typical challenge completion time
                requires_handicap=False,  # Individual challenges don't need handicaps
                notes=f"Skill Challenge: {suitable_challenge.name}",
            )
            return challenge_pairing

        return None

    def _try_individual_match_replacement(
        self, gara: Gara, player_id: int, round_number: int, preview_mode: bool
    ) -> Optional[Pairing]:
        """Attempt to replace bye with individual match for social engagement.

        Individual matches provide casual competitive opportunities with other
        available players, maintaining the social aspects of tournament participation
        while ensuring no player sits idle unnecessarily.

        Returns:
            Individual match Pairing with moderate quality (social engagement value)
        """
        # Identify available player for casual competitive engagement
        suitable_opponent = self._find_suitable_opponent(gara, player_id, round_number)

        if suitable_opponent:
            # Create casual match pairing for social engagement
            individual_pairing = Pairing(
                players=(player_id, suitable_opponent),
                is_bye=False,
                round_number=round_number,
                pairing_quality=0.7,  # Good quality for casual competitive play
                estimated_duration=45,  # Standard individual match duration
                requires_handicap=True,  # May benefit from skill balancing
                notes="Casual match for bye replacement and community engagement",
            )
            return individual_pairing

        return None

    def _enhance_trio_match(
        self, pairing: Pairing, gara: Gara, round_number: int
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
        self, gara: Gara, player_id: int
    ) -> Optional[Challenge]:
        """Locate appropriate skill challenge for individual player development.

        Searches for challenges that match the player's skill level and tournament
        context, ensuring the X-replacement activity provides meaningful value.

        Args:
            gara: Tournament context for challenge scope
            player_id: Player needing alternative activity

        Returns:
            Challenge object suitable for tournament integration, or None if unavailable
        """
        # Query challenge system for tournament-appropriate skill development opportunities
        from models.challenge.services import ChallengeService

        try:
            # Request challenge recommendation from challenge service
            suitable_challenge = ChallengeService.get_challenge_for_x_replacement(
                gara.id
            )

            return suitable_challenge
        except Exception:
            # Graceful degradation if challenge system unavailable
            pass

        return None

    def _find_suitable_opponent(
        self, gara: Gara, player_id: int, round_number: int
    ) -> Optional[int]:
        """Find a suitable opponent for individual match replacement."""
        # Get players who also have bye or are available
        active_players = self._get_active_players(gara)

        # Exclude current player
        other_players = [p for p in active_players if p != player_id]

        if not other_players:
            return None

        # Try to find player with similar ranking
        if round_number > 1:
            similar_ranked = self._find_similar_ranked_player(
                player_id, other_players, gara.id, round_number
            )
            if similar_ranked:
                return similar_ranked

        # Return first available player
        return other_players[0] if other_players else None

    def _get_active_players(self, gara: Gara) -> List[int]:
        """Get list of active player IDs."""
        # Handle the relationship properly
        inscriptions = getattr(gara, "inscriptions", [])
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
        self, player_id: int, candidate_ids: List[int], gara_id: int, round_number: int
    ) -> Optional[int]:
        """Find player with similar ranking."""
        try:
            # Get current round classifications
            classifications = RoundClassification.query.filter_by(
                gara_id=gara_id, round_number=round_number - 1
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
        self, pairings: Sequence[Pairing], gara: object, round_number: int
    ) -> None:
        """Apply side effects for advanced pairings."""
        # Cast to Gara for type safety
        gara_obj: Gara = gara  # type: ignore

        # Let base strategy handle standard side effects
        self._base_strategy._apply_side_effects(pairings, gara, round_number)

        # Apply additional side effects for advanced features
        for pairing in pairings:
            if "Challenge:" in (pairing.notes or ""):
                # Record challenge assignment
                self._record_challenge_assignment(gara_obj, pairing, round_number)
            elif "Individual match" in (pairing.notes or ""):
                # Record individual match intention
                self._record_individual_match_intention(gara_obj, pairing, round_number)

    def _record_challenge_assignment(
        self, gara: Gara, pairing: Pairing, round_number: int
    ) -> None:
        """Record challenge assignment for X replacement."""
        # This would typically update some tracking system

    def _record_individual_match_intention(
        self, gara: Gara, pairing: Pairing, round_number: int
    ) -> None:
        """Record intention to create individual match for X replacement."""
        # This would typically update some tracking system

    def _postprocess_pairings(
        self, pairings: Sequence[Pairing], gara: object, round_number: int
    ) -> Sequence[Pairing]:
        """Postprocess pairings with quality improvements."""
        # Cast to Gara for type safety
        gara_obj: Gara = gara  # type: ignore

        # Apply anti-rematch logic to improve pairing quality
        enhanced_pairings = []

        for pairing in pairings:
            if not pairing.is_bye and len(pairing.players) >= 2:
                # Calculate enhanced quality based on anti-rematch
                quality = self._calculate_enhanced_pairing_quality(
                    pairing, gara_obj, round_number
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
        self, pairing: Pairing, gara: Gara, round_number: int
    ) -> float:
        """Calculate pairing quality with advanced anti-rematch intelligence.

        Enhances base pairing quality assessment by incorporating encounter history
        and applying configurable penalties for repeated matchups. This promotes
        variety and fairness throughout the tournament.

        Quality Factors:
        - Base algorithmic quality from Amalfi engine
        - Anti-rematch penalty based on encounter history
        - Weighted adjustment using configured anti_rematch_weight

        Args:
            pairing: Pairing object to assess
            gara: Tournament context for encounter history
            round_number: Current round for temporal context

        Returns:
            Enhanced quality score incorporating rematch avoidance preferences
        """
        base_quality = pairing.pairing_quality or 0.5

        # Apply anti-rematch intelligence to promote variety and fairness
        from models.classification.models import PlayerEncounter

        if len(pairing.players) >= 2:
            player1_id, player2_id = pairing.players[0], pairing.players[1]
            have_played = PlayerEncounter.have_played(gara.id, player1_id, player2_id)

            if have_played:
                # Apply configured quality penalty for repeated matchups
                return base_quality * self._options.anti_rematch_weight

        return base_quality
