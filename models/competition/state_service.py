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
    @transactional(domain="competition")
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
    @transactional(domain="competition")
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
    def complete(gara: Gara) -> Gara:
        """playing → completed"""
        StateService._require(gara, GaraStatus.PLAYING)

        # Check for pending or in-progress matches
        from models.match.models import Match
        from models.status_enum import MatchStatus

        pending_matches = Match.query.filter_by(gara_id=gara.id).filter(
            Match.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value])
        ).first()

        if pending_matches:
            raise InvalidTransitionError("Match ancora in corso")

        gara.status = GaraStatus.COMPLETED.value
        db.session.add(gara)
        return gara
