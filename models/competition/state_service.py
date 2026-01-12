"""
StateService - Simple extraction of state management from GaraService.

Extracted from ProvaStateMachine to follow Single Responsibility Principle
while maintaining the same simple interface and behavior.
"""

from models.base import db, transactional
from models.status_enum import GaraStatus
from models.exceptions import InvalidTransitionError
from models.competition.models import Gara


class StateService:
    """Simple service for managing Gara state transitions.

    Mirrors the existing ProvaStateMachine interface exactly.
    """

    @staticmethod
    def _require(gara: Gara, expected: GaraStatus) -> None:
        """Validate required state for transition."""
        current_status = gara.status or GaraStatus.SETUP.value
        if current_status != expected.value:
            raise InvalidTransitionError(
                f"Transizione non ammessa: {gara.status!r} → "
                f"{expected.name.lower()} richiesta come stato corrente."
            )

    @staticmethod
    def to_inscription(gara: Gara) -> Gara:
        """setup → inscription"""
        StateService._require(gara, GaraStatus.SETUP)

        # Validazione: le date di iscrizione devono essere impostate
        if not gara.inscription_start or not gara.inscription_end:
            raise InvalidTransitionError("Date di iscrizione non impostate")

        gara.status = GaraStatus.INSCRIPTION.value
        db.session.add(gara)
        return gara

    @staticmethod
    @transactional(domain="competition")
    def reopen_setup(gara: Gara) -> Gara:
        """inscription → setup"""
        StateService._require(gara, GaraStatus.INSCRIPTION)
        gara.status = GaraStatus.SETUP.value
        db.session.add(gara)
        return gara

    @staticmethod
    def start_playing(gara: Gara) -> Gara:
        """inscription → playing"""
        StateService._require(gara, GaraStatus.INSCRIPTION)

        # Controllo sul numero di iscritti vs minimo richiesto
        min_required = gara.min_participants or 2
        try:
            count = len(gara.inscriptions)  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            count = 0

        if count < min_required:
            raise InvalidTransitionError(
                f"Giocatori insufficienti per iniziare la gara "
                f"(minimo: {min_required}, iscritti: {count})"
            )

        gara.status = GaraStatus.PLAYING.value
        gara.current_round = 1
        db.session.add(gara)
        return gara

    @staticmethod
    @transactional(domain="competition")
    def start_ssr(gara: Gara) -> Gara:
        """playing → awaiting_ssr

        Transition to SSR phase when rounds are complete but tiebreakers are needed.
        """
        StateService._require(gara, GaraStatus.PLAYING)

        # Check for pending or in-progress matches
        from models.match.models import Match
        from models.status_enum import MatchStatus

        pending_matches = Match.query.filter_by(gara_id=gara.id).filter(
            Match.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value])  # type: ignore[attr-defined]
        ).first()

        if pending_matches:
            raise InvalidTransitionError("Match ancora in corso")

        gara.status = GaraStatus.AWAITING_SSR.value
        db.session.add(gara)
        return gara

    @staticmethod
    def _require_one_of(gara: Gara, expected: list[GaraStatus]) -> None:
        """Validate that gara is in one of the expected states."""
        current_status = gara.status or GaraStatus.SETUP.value
        if current_status not in [s.value for s in expected]:
            allowed = " o ".join(s.name.lower() for s in expected)
            raise InvalidTransitionError(
                f"Transizione non ammessa: {gara.status!r} → "
                f"richiesto uno tra: {allowed}."
            )

    @staticmethod
    @transactional(domain="competition")
    def complete(gara: Gara) -> Gara:
        """playing|awaiting_ssr → completed"""
        StateService._require_one_of(gara, [GaraStatus.PLAYING, GaraStatus.AWAITING_SSR])

        # Check for pending or in-progress matches
        from models.match.models import Match
        from models.status_enum import MatchStatus

        pending_matches = Match.query.filter_by(gara_id=gara.id).filter(
            Match.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value])  # type: ignore[attr-defined]
        ).first()

        if pending_matches:
            raise InvalidTransitionError("Match ancora in corso")

        gara.status = GaraStatus.COMPLETED.value
        db.session.add(gara)

        # Emit CompetitionCompletedEvent for gamification
        from models.events.competition_events import CompetitionCompletedEvent
        from models.events.base import EventBus
        from models.classification.models import RoundClassification
        from models.competition.models import Inscription

        # Get winner from final round classification
        winner_id = None
        winner_name = None
        final_standings = None

        final_round_class = (
            RoundClassification.query
            .filter_by(gara_id=gara.id, round_number=gara.current_round)
            .order_by(RoundClassification.position.asc())
            .all()
        )

        if final_round_class:
            # First position is the winner
            winner_classification = final_round_class[0]
            winner_id = winner_classification.user_id
            if winner_classification.user:
                winner_name = winner_classification.user.username

            # Build final standings
            final_standings = [
                {
                    "position": rc.position,
                    "user_id": rc.user_id,
                    "username": rc.user.username if rc.user else None,
                    "matches_won": rc.matches_won,
                    "rack_difference": rc.rack_difference
                }
                for rc in final_round_class
            ]

        # Count participants
        total_participants = Inscription.query.filter_by(
            gara_id=gara.id,
            is_withdrawn=False,
            is_waitlist=False
        ).count()

        gara_name = gara.name or f"Gara {gara.number}"

        event = CompetitionCompletedEvent(
            gara_id=gara.id,
            name=gara_name,
            winner_id=winner_id,
            winner_name=winner_name,
            final_standings=final_standings,
            total_participants=total_participants,
            total_rounds=gara.current_round
        )
        EventBus.publish(event)

        return gara
