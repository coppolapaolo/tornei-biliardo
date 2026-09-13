"""
Module: models/individual_match/match_lifecycle_service.py
Purpose: Match lifecycle management service (extracted from IndividualMatchService)
Sprint 13: IndividualMatchService decomposition
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional, List, Set

from ..base import db, utc_now
from ..transaction.manager import transactional
from ..status_enum import MatchStatus
from .models import IndividualMatch

logger = logging.getLogger(__name__)


class MatchLifecycleService:
    """Service for individual match lifecycle management."""

    @staticmethod
    @transactional(domain="individual_match")
    def start_match(match_id: int, user_id: int) -> IndividualMatch:
        """Start an individual match (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_player(user_id):
            raise ValueError("Only match players can start the match")

        match.start_match()
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def start_next_set(match_id: int, user_id: int):
        """Comincia il set successivo di una sfida al meglio dei set.

        Un set finito non tira dietro il seguente: qualcuno deve cominciarlo,
        perché fra un set e l'altro al tavolo succedono cose (si cambia, si
        beve, si aspetta). Finché non c'è, però, non si può segnare niente e
        la partita non si può nemmeno chiudere — quindi il comando deve
        esistere davvero. Sulle sfide individuali non c'era: il segnapunti
        offriva «Inizia il set N» e il pulsante chiamava una funzione che
        nessuno aveva scritto.
        """
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_player(user_id):
            raise ValueError("Only match players can start the next set")

        return match.start_next_set()

    @staticmethod
    @transactional(domain="individual_match")
    def confirm_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Confirm match result by a player (new UX)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_player(user_id):
            raise ValueError("Only match players can confirm the result")

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        match.confirm_result(user_id)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def reject_match_result(match_id: int, user_id: int) -> IndividualMatch:
        """Reject match result - removes last rack (new UX)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_player(user_id):
            raise ValueError("Only match players can reject the result")

        if not match.is_ready_for_validation():
            raise ValueError("Match is not ready for validation")

        match.reject_result(user_id)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def complete_match(match_id: int, winner_id: int, user_id: int) -> IndividualMatch:
        """Complete a match - legacy method for backward compatibility."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_player(user_id):
            raise ValueError("Only match players can complete the match")

        match.complete_match(winner_id)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def complete_individual_match(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualMatch:
        """Complete an individual match - alias for complete_match."""
        return MatchLifecycleService.complete_match(match_id, winner_id, user_id)

    @staticmethod
    @transactional(domain="individual_match")
    def cancel_match(
        match_id: int, user_id: int, reason: Optional[str] = None
    ) -> IndividualMatch:
        """Cancel a match (must be one of the players)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_player(user_id):
            raise ValueError("Only match players can cancel the match")

        match.cancel_match(reason)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def forfeit_match(match_id: int, user_id: int) -> IndividualMatch:
        """Forfeit an individual match - user loses, opponent wins.

        The forfeiting player keeps their current score (racks already won).
        The opponent receives the winning score (distance).

        Args:
            match_id: ID of the match
            user_id: ID of player forfeiting

        Returns:
            The updated IndividualMatch object

        Raises:
            ValueError: If invalid forfeit conditions
        """
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        # Delegate to model method which handles all validation and logic
        match.forfeit_match(user_id)
        return match

    #: Prefisso dell'``action_url`` dei promemoria, usato anche per ritrovarli
    #: in fase di deduplica: è l'unico legame match↔notifica che esiste anche
    #: sulle notifiche create prima che venisse aggiunto ``related_entities``.
    REMINDER_URL_PREFIX = "/match/matches/"

    @staticmethod
    def send_match_reminders(
        hours_before: int = 2, window_minutes: int = 60
    ) -> List[int]:
        """Send reminder notifications for upcoming matches.

        Finds matches scheduled within a time window and sends reminders
        to both players. Designed to be called hourly (see
        ``scripts/send_match_reminders.py``).

        La finestra di default è di **60 minuti** perché gli scheduled task di
        PythonAnywhere non scendono sotto la cadenza oraria: con i 15 minuti
        originali il task avrebbe coperto un quarto d'ora su sessanta e tre
        promemoria su quattro non sarebbero mai partiti. Il prezzo è che il
        promemoria arriva fra ``hours_before`` e ``hours_before + 1`` ore prima
        del match invece che a un orario esatto — per questo il testo non
        promette più "fra due ore" ma riporta l'orario dell'incontro.

        Un match già avvisato non viene riavvisato: le esecuzioni sono
        idempotenti anche quando le finestre si sovrappongono, cosa che
        succede appena lo scheduler parte con qualche minuto di ritardo.

        Args:
            hours_before: Hours before match to send reminder (default 2)
            window_minutes: Time window in minutes to check (default 60)

        Returns:
            ID dei match per cui è partito **almeno un** promemoria. Un match
            in cui entrambi i giocatori hanno la notifica disattivata (o sono
            in quiet hours: ``create_notification`` restituisce ``None`` senza
            sollevare) non compare, così il conteggio stampato dallo scheduled
            task dice quanti avvisi sono davvero usciti e non quanti match
            erano nella finestra.
        """
        from flask_babel import _
        from utils.jinja import format_datetime_local_text
        from utils.local_time import resolve_timezone_for_user_id
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationType, NotificationPriority

        now = utc_now()
        window_start = now + timedelta(hours=hours_before)
        window_end = window_start + timedelta(minutes=window_minutes)

        # Find matches in the reminder window with status SCHEDULED
        upcoming_matches = IndividualMatch.query.filter(
            IndividualMatch.scheduled_at.between(window_start, window_end),
            IndividualMatch.status == MatchStatus.SCHEDULED.value,
        ).all()

        already_reminded = MatchLifecycleService._already_reminded_match_ids(
            upcoming_matches,
            stale_after=timedelta(hours=hours_before, minutes=window_minutes),
        )

        reminded_match_ids: List[int] = []

        for match in upcoming_matches:
            if match.id in already_reminded:
                continue

            # Get both player IDs
            player_ids = [match.player1_id, match.player2_id]
            location_text = match.location or ""

            try:
                # Un avviso per giocatore, e non uno solo per tutti e due:
                # `scheduled_at` è UTC (convenzione di progetto) e va mostrato
                # nel fuso di **chi lo legge** (ADR-043). Due giocatori in fusi
                # diversi hanno bisogno di due frasi diverse, e qui non c'è
                # nessun `current_user` da cui dedurlo — è uno scheduled task.
                created = []
                for player_id in player_ids:
                    when = format_datetime_local_text(
                        match.scheduled_at,
                        tz=resolve_timezone_for_user_id(player_id),
                    )
                    created.extend(
                        NotificationFactory.create_bulk_notification(
                            user_ids=[player_id],
                            notification_type=NotificationType.MATCH_REMINDER,
                            title=_("Promemoria sfida"),
                            message=_(
                                "La tua sfida è programmata per il "
                                "%(when)s%(location)s",
                                when=when,
                                location=(
                                    f" presso {location_text}" if location_text else ""
                                ),
                            ),
                            priority=NotificationPriority.HIGH,
                            related_entities={"individual_match_id": match.id},
                            action_url=(
                                f"{MatchLifecycleService.REMINDER_URL_PREFIX}"
                                f"{match.id}"
                            ),
                            action_text=_("Visualizza"),
                            continue_on_error=True,
                        )
                    )
                # `create_bulk_notification` mette None in lista sia per un
                # errore sia per una preferenza che blocca l'invio: se sono
                # tutti None non è uscito niente e il match non va contato.
                if any(notification is not None for notification in created):
                    reminded_match_ids.append(match.id)
            except Exception:
                # Un match che non riesce non deve fermare gli altri, ma il
                # commento diceva "log" senza loggare: in uno scheduled task
                # l'errore spariva e il job risultava riuscito a vuoto.
                logger.exception("Invio promemoria fallito per il match %s", match.id)

        return reminded_match_ids

    @staticmethod
    def _already_reminded_match_ids(
        matches: List["IndividualMatch"], stale_after: timedelta
    ) -> Set[int]:
        """Match fra i ``matches`` che hanno già ricevuto un promemoria valido.

        La soglia è calcolata **per match**, non globalmente: un promemoria
        conta solo se creato dopo ``scheduled_at - stale_after``, cioè dentro
        la finestra in cui poteva riferirsi all'orario attuale dell'incontro.

        Serve per le riprogrammazioni ravvicinate. Con una soglia globale
        (``now - stale_after``) bastava spostare il match poco dopo l'invio del
        primo promemoria perché quel record, ancora recente, bloccasse il nuovo
        avviso: il giocatore restava con in mano l'orario vecchio e nessuna
        correzione. Ancorandola a ``scheduled_at`` il promemoria del vecchio
        orario risulta troppo vecchio per la nuova programmazione, e il match
        viene riavvisato.

        Nota: un utente che ha disattivato le notifiche MATCH_REMINDER non ne
        ha nessuna da trovare, quindi il suo match risulta "non avvisato" e il
        giro dopo ci riprova — a vuoto, perché la preferenza lo blocca di
        nuovo. Nessun effetto visibile, e il caso opposto (dedurre l'invio da
        un record che non esiste) costerebbe una tabella di stato in più.
        """
        from ..notification.models import Notification, NotificationType

        if not matches:
            return set()

        by_url = {
            f"{MatchLifecycleService.REMINDER_URL_PREFIX}{match.id}": match
            for match in matches
        }
        rows = (
            db.session.query(Notification.action_url, Notification.created_at)
            .filter(
                Notification.notification_type == NotificationType.MATCH_REMINDER,
                Notification.action_url.in_(list(by_url)),
            )
            .all()
        )

        reminded: Set[int] = set()
        for action_url, created_at in rows:
            match = by_url.get(action_url)
            if match is None or created_at is None:
                continue
            if created_at >= match.scheduled_at - stale_after:
                reminded.add(match.id)
        return reminded
