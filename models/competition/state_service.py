"""
StateService - Simple extraction of state management from GaraService.

Extracted from ProvaStateMachine to follow Single Responsibility Principle
while maintaining the same simple interface and behavior.
"""

import logging

from models.base import db, transactional
from models.status_enum import GaraStatus
from models.exceptions import InvalidTransitionError
from models.competition.models import Gara

logger = logging.getLogger(__name__)


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
        """setup → inscription

        No @transactional: always called within a transactional context
        (InscriptionService.open_inscriptions, GaraService).
        """
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
        """inscription → playing

        No @transactional: always called within a transactional context
        (RoundService.start_first_round, RoundCreation).
        """
        StateService._require(gara, GaraStatus.INSCRIPTION)

        # Controllo sul numero di iscritti attivi vs minimo richiesto
        min_required = gara.min_participants or 2
        from models.competition.models import Inscription

        count = Inscription.query.filter_by(
            gara_id=gara.id, is_withdrawn=False, is_waitlist=False
        ).count()

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

        pending_matches = (
            Match.query.filter_by(gara_id=gara.id)
            .filter(
                Match.status.in_(  # type: ignore[attr-defined]
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                )
            )
            .first()
        )

        if pending_matches:
            raise InvalidTransitionError("Match ancora in corso")

        # Lo spareggio porta alla chiusura: aspetta anche lui la prova della X
        # e gli esercizi dell'ultimo turno (SPECIFICHE.md riga 102).
        from models.competition.pendenze_turno import verifica_gara_chiudibile

        verifica_gara_chiudibile(gara)

        gara.status = GaraStatus.AWAITING_SSR.value
        db.session.add(gara)
        return gara

    @staticmethod
    @transactional(domain="competition")
    def cancel_ssr(gara: Gara) -> Gara:
        """awaiting_ssr → playing

        Contropartita di `start_ssr`: senza di essa lo spareggio era un vicolo
        cieco, perché durante `awaiting_ssr` il reset dei match è bloccato
        (ADR-026) e l'unica uscita era terminare la gara. Un punteggio
        sbagliato scoperto in fase di spareggio non era più correggibile.

        I punteggi SSR vengono azzerati: tornando a `playing` i match sono di
        nuovo modificabili, quindi la classifica — e chi è a pari merito — può
        cambiare. Riavviare l'SSR ricalcola i gruppi da capo.
        """
        StateService._require(gara, GaraStatus.AWAITING_SSR)

        from models.competition.spareggio_service import SpareggioService

        SpareggioService.clear_ssr_scores(gara.id)

        gara.status = GaraStatus.PLAYING.value
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
        StateService._require_one_of(
            gara, [GaraStatus.PLAYING, GaraStatus.AWAITING_SSR]
        )

        # Check for pending or in-progress matches
        from models.match.models import Match
        from models.status_enum import MatchStatus

        pending_matches = (
            Match.query.filter_by(gara_id=gara.id)
            .filter(
                Match.status.in_(  # type: ignore[attr-defined]
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                )
            )
            .first()
        )

        if pending_matches:
            raise InvalidTransitionError("Match ancora in corso")

        # La prova della X e gli esercizi dell'ultimo turno: come una partita
        # non validata (SPECIFICHE.md riga 102).
        from models.competition.pendenze_turno import verifica_gara_chiudibile

        verifica_gara_chiudibile(gara)

        gara.status = GaraStatus.COMPLETED.value
        db.session.add(gara)

        # Emit CompetitionCompletedEvent for gamification
        from models.events.competition_events import CompetitionCompletedEvent
        from models.events.base import EventBus
        from models.classification.models import RoundClassification
        from models.competition.models import Inscription
        from models.competition.spareggio_service import SpareggioService

        # Posizioni finali con i parimerito a pari posizione. Fuori dallo
        # spareggio questo passaggio non avveniva: `finalize_classification`
        # è invocata solo dopo i punteggi SSR, e un parimerito fuori dalle
        # posizioni contese non genera spareggio (issue #63), quindi restava
        # con le posizioni progressive del calcolo per turno (issue #67).
        # `apply_final_positions` non è `@transactional`: siamo già dentro la
        # transazione di questo metodo.
        SpareggioService.apply_final_positions(gara.id)

        # Get winner from final round classification
        winner_id = None
        winner_name = None
        final_standings = None

        # Stesso turno su cui `apply_final_positions` ha appena scritto: con la
        # strategia Random i turni sono creati tutti all'avvio e
        # `gara.current_round` può restare indietro, quindi leggere da lì
        # significherebbe prendere vincitore e standings da un turno
        # intermedio. L'ordinamento tiene conto dei parimerito (#67).
        final_round_class = RoundClassification.ordered_for_display(
            gara.id, SpareggioService.effective_final_round(gara)
        )

        if final_round_class:
            # First position is the winner
            winner_classification = final_round_class[0]
            winner_id = winner_classification.user_id
            if winner_classification.user:
                winner_name = winner_classification.user.username

            # Non designare un vincitore "torneo" se il 1° posto è in uno
            # spareggio SSR ancora irrisolto. Le route gara chiamano
            # detect_tiebreakers prima di complete(); il path campionato
            # (terminate_campionato → complete) bypassa quel gate, e premieremmo
            # con XP/achievement "vittoria torneo" un vincitore non ancora
            # determinato. detect_tiebreakers ritorna solo i gruppi irrisolti.
            if getattr(gara, "tiebreaker_enabled", False) and winner_id is not None:
                from models.competition.spareggio_service import SpareggioService

                unresolved = SpareggioService.detect_tiebreakers(gara.id)
                winner_in_unresolved_tie = any(
                    any(p.get("user_id") == winner_id for p in grp["players"])
                    for grp in unresolved
                )
                if winner_in_unresolved_tie:
                    winner_id = None
                    winner_name = None

            # Build final standings
            final_standings = [
                {
                    "position": rc.position,
                    "user_id": rc.user_id,
                    "username": rc.user.username if rc.user else None,
                    "matches_won": rc.matches_won,
                    "rack_difference": rc.rack_difference,
                }
                for rc in final_round_class
            ]

        # Count participants
        total_participants = Inscription.query.filter_by(
            gara_id=gara.id, is_withdrawn=False, is_waitlist=False
        ).count()

        gara_name = gara.name or f"Gara {gara.number}"

        event = CompetitionCompletedEvent(
            gara_id=gara.id,
            name=gara_name,
            winner_id=winner_id,
            winner_name=winner_name,
            final_standings=final_standings,
            total_participants=total_participants,
            total_rounds=gara.current_round,
        )
        EventBus.publish(event)

        # Le righe `Classification` del campionato (profilo, export, avvio dei
        # playoff) si ricalcolavano solo su eventi rari — regole di punteggio,
        # riassegnazione, unione di account, terminazione — quindi la chiusura
        # della finale le lasciava alla classifica precedente. La pagina del
        # campionato non le legge (calcola al volo), il profilo sì. Un errore
        # qui non deve impedire la chiusura della gara: i fatti sono salvi e
        # il prossimo ricalcolo li rilegge.
        if gara.campionato_id:
            from models.classification.campionato_classification import (
                ClassificationService,
            )

            try:
                ClassificationService.invalidate_campionato_cache(gara.campionato_id)
                ClassificationService.update_campionato_classification(
                    gara.campionato_id
                )
            except Exception:
                logger.warning(
                    "Classifica generale del campionato %d non aggiornata "
                    "alla chiusura della gara %d",
                    gara.campionato_id,
                    gara.id,
                    exc_info=True,
                )

        return gara
