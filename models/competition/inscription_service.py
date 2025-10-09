"""
Inscription Service - Competition Domain

Service for managing competition inscriptions and waitlist operations.
Extracted from GaraService to follow Single Responsibility Principle.

Business Operations:
- User inscription and waitlist management
- Inscription validation and date management
- Admin inscription controls
- Waitlist promotion and notifications

Author: Refactoring Phase 1 - Task 1.2 (GaraService Decomposition)
Created: 2025-01-18
"""

from __future__ import annotations

from typing import Optional
from datetime import datetime

from models.base import db
from models.status_enum import GaraStatus
from .models import Inscription
from models.transaction.manager import transactional

# Forward import to avoid circular dependencies
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.competition.models import Gara


class InscriptionService:
    """Operazioni di business su Inscription."""

    @staticmethod
    @transactional(domain="competition")
    def inscribe_user(user_id: int, gara_id: int) -> Optional[Inscription]:
        """Registra un utente a una gara se non già iscritto.

        Se la gara è piena, l'utente viene messo in lista d'attesa.
        """
        from models.competition.models import Gara
        from models.user.models import User
        from models.user.role_enum import UserRole

        existing = (
            db.session.query(Inscription)
            .filter_by(user_id=user_id, gara_id=gara_id)
            .first()
        )
        if existing:
            return existing

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return None

        user = db.session.get(User, user_id)
        if not user:
            return None

        # Validazione: Admin non può partecipare ai tornei
        if user.role == UserRole.ADMIN.value:
            raise ValueError("Admin non può partecipare ai tornei")

        # Validazione: Verifica periodo di iscrizione
        # IMPORTANT: Use UTC for all datetime comparisons
        # Database stores naive datetimes which are treated as UTC
        now = datetime.utcnow()
        if gara.inscription_start and gara.inscription_end:
            if now < gara.inscription_start:
                raise ValueError("Iscrizioni non ancora aperte")
            if now > gara.inscription_end:
                raise ValueError("Iscrizioni chiuse")

        # Verifica se la gara è piena (per waitlist)
        is_waitlist = False
        if gara.max_participants and gara.max_participants > 0:
            current_count = (
                db.session.query(Inscription).filter_by(gara_id=gara_id).count()
            )
            # If max participants reached, put user on waitlist
            # instead of throwing error
            is_waitlist = current_count >= gara.max_participants
        waitlist_position = None

        if is_waitlist:
            # Calcola la posizione in lista d'attesa
            waitlist_position = (
                gara.get_waitlist_count() + 1
                if hasattr(gara, "get_waitlist_count")
                else None
            )

        ins = Inscription(
            user_id=user_id,
            gara_id=gara_id,
            is_waitlist=is_waitlist,
            waitlist_position=waitlist_position,
        )
        db.session.add(ins)
        # Transaction managed by @transactional decorator
        return ins

    @staticmethod
    @transactional(domain="competition")
    def uninscribe_user(user_id: int, gara_id: int) -> bool:
        """Cancella l'iscrizione di un utente dalla gara.

        Se l'utente non era in lista d'attesa, promuove il primo della lista d'attesa.
        Invia notifica al promosso.

        Returns: True se rimossa, False se non trovata.
        """
        from models.competition.models import Gara

        inscription = (
            db.session.query(Inscription)
            .filter_by(user_id=user_id, gara_id=gara_id)
            .first()
        )
        if inscription:
            was_active = not inscription.is_waitlist and not inscription.is_withdrawn
            gara_id_for_promotion = inscription.gara_id

            db.session.delete(inscription)

            # Se l'utente era attivo (non in lista d'attesa),
            # promuovi il primo della lista d'attesa
            if was_active:
                gara = db.session.get(Gara, gara_id_for_promotion)
                if gara:
                    first_waitlist = (
                        db.session.query(Inscription)
                        .filter_by(
                            gara_id=gara_id_for_promotion,
                            is_waitlist=True,
                            is_withdrawn=False,
                        )
                        .order_by(Inscription.waitlist_position.asc())
                        .first()
                    )

                    if first_waitlist:
                        # Promuovi dalla lista d'attesa
                        first_waitlist.is_waitlist = False
                        first_waitlist.waitlist_position = None

                        # Ricalcola le posizioni degli altri in lista d'attesa
                        remaining_waitlist = (
                            db.session.query(Inscription)
                            .filter_by(
                                gara_id=gara_id_for_promotion,
                                is_waitlist=True,
                                is_withdrawn=False,
                            )
                            .order_by(Inscription.waitlist_position.asc())
                            .all()
                        )

                        for i, insc in enumerate(remaining_waitlist, 1):
                            insc.waitlist_position = i

                        # Invia notifica al promosso
                        # Use NotificationFactory for standardized error handling
                        from models.notification.factory import NotificationFactory
                        from models.notification.models import NotificationPriority

                        gara_display = (
                            gara.name or f'Gara {gara.number}'
                        )
                        msg = (
                            f"Sei stato promosso dalla lista d'attesa "
                            f"per la gara '{gara_display}'"
                        )
                        notification_result = (
                            NotificationFactory
                            .create_account_update_notification(
                                user_id=first_waitlist.user_id,
                                title="Posto disponibile!",
                                message=msg,
                                priority=NotificationPriority.HIGH,
                                update_type="waitlist_promotion",
                                related_entities={
                                    "gara_id": gara.id,
                                    "gara_name": gara.name
                                }
                            )
                        )
                        print(
                            f"DEBUG: Promotion notification created "
                            f"for user {first_waitlist.user_id}: "
                            f"{notification_result}"
                        )

            # Transaction managed by @transactional decorator
            return True
        return False

    @staticmethod
    @transactional(domain="competition")
    def admin_uninscribe_user(
        user_id: int, gara_id: int, admin_user_id: int
    ) -> bool:
        """Disiscrive un utente dalla gara da parte di admin/direttore.

        Invia notifica all'utente discritto e promuove il primo della
        lista d'attesa se applicabile.

        Returns: True se rimossa, False se non trovata.
        """
        from models.competition.models import Gara
        from models.user.models import User

        inscription = (
            db.session.query(Inscription)
            .filter_by(user_id=user_id, gara_id=gara_id)
            .first()
        )

        if inscription:
            gara = db.session.get(Gara, gara_id)
            admin_user = db.session.get(User, admin_user_id)

            was_active = (
                not inscription.is_waitlist and not inscription.is_withdrawn
            )
            gara_name = gara.name or f"Gara {gara.number}"
            admin_role = (
                "admin" if admin_user.is_admin else "direttore di gara"
            )

            # Invia notifica all'utente discritto
            try:
                from models.notification.factory import NotificationFactory
                from models.notification.models import NotificationPriority

                message = (
                    f"L'{admin_role} ha annullato la tua iscrizione "
                    f"alla {gara_name}"
                )
                if inscription.is_waitlist:
                    message = (
                        f"L'{admin_role} ti ha rimosso dalla lista "
                        f"d'attesa per la {gara_name}"
                    )

                notification_result = (
                    NotificationFactory.create_tournament_notification(
                        user_ids=[user_id],
                        tournament_name=gara_name,
                        message_template=message,
                        priority=NotificationPriority.HIGH,
                        tournament_id=gara_id,
                    )
                )
                print(
                    f"DEBUG: Notification created for user "
                    f"{user_id}: {notification_result}"
                )
            except Exception as e:
                print(
                    f"DEBUG: Error creating notification "
                    f"for user {user_id}: {e}"
                )

            # Rimuovi l'iscrizione
            db.session.delete(inscription)

            # Se l'utente era attivo (non in lista d'attesa),
            # promuovi il primo della lista d'attesa
            if was_active:
                first_waitlist = (
                    db.session.query(Inscription)
                    .filter_by(
                        gara_id=gara_id,
                        is_waitlist=True,
                        is_withdrawn=False
                    )
                    .order_by(Inscription.waitlist_position.asc())
                    .first()
                )

                if first_waitlist:
                    # Promuovi dalla lista d'attesa
                    first_waitlist.is_waitlist = False
                    first_waitlist.waitlist_position = None

                    # Ricalcola le posizioni degli altri in lista d'attesa
                    remaining_waitlist = (
                        db.session.query(Inscription)
                        .filter_by(
                            gara_id=gara_id,
                            is_waitlist=True,
                            is_withdrawn=False
                        )
                        .order_by(Inscription.waitlist_position.asc())
                        .all()
                    )

                    for i, insc in enumerate(remaining_waitlist, 1):
                        insc.waitlist_position = i

                    # Invia notifica al promosso
                    try:
                        from models.notification.factory import (
                            NotificationFactory
                        )
                        from models.notification.models import (
                            NotificationPriority
                        )

                        promo_msg = (
                            f"Sei stato promosso dalla lista d'attesa "
                            f"per {gara_name}"
                        )
                        notification_result = (
                            NotificationFactory
                            .create_tournament_notification(
                                user_ids=[first_waitlist.user_id],
                                tournament_name=gara_name,
                                message_template=promo_msg,
                                priority=NotificationPriority.HIGH,
                                tournament_id=gara_id,
                            )
                        )
                        print(
                            f"DEBUG: Promotion notification created "
                            f"for user {first_waitlist.user_id}: "
                            f"{notification_result}"
                        )
                    except Exception as e:
                        print(
                            f"DEBUG: Error creating promotion "
                            f"notification for user "
                            f"{first_waitlist.user_id}: {e}"
                        )

            # Transaction managed by @transactional decorator
            return True
        return False

    @staticmethod
    @transactional(domain="competition")
    def open_inscriptions(
        gara_id: int, inscription_start: datetime, inscription_end: datetime
    ) -> "Gara":
        """Apre le iscrizioni per una gara con validazione delle date."""
        from models.competition.models import Gara
        from models.competition.state_service import StateService

        if inscription_start > inscription_end:
            raise ValueError(
                "La data di inizio deve essere precedente alla data di fine!"
            )

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Valida che la data di fine iscrizioni non superi la data della gara
        adjusted = False
        if gara.date and gara.time:
            # Converti date in datetime per confronto
            from datetime import datetime as dt
            gara_datetime = dt.combine(gara.date, gara.time)

            if inscription_end > gara_datetime:
                inscription_end = gara_datetime
                adjusted = True

        gara.inscription_start = inscription_start
        gara.inscription_end = inscription_end
        gara = StateService.to_inscription(gara)

        # Solleva un'eccezione informativa se la data è stata aggiustata
        if adjusted:
            raise ValueError(
                "La data di fine iscrizioni non può superare la data della gara. "
                "È stata automaticamente impostata alla data della gara."
            )

        return gara

    @staticmethod
    @transactional(domain="competition")
    def modify_inscription_dates(
        gara_id: int, inscription_start: datetime, inscription_end: datetime
    ) -> "Gara":
        """Modifica le date di iscrizione per una gara.

        Permette di:
        - Estendere il periodo di iscrizione (più tempo per iscriversi)
        - Accorciare il periodo (chiudere prima)
        - Modificare le date se non ancora iniziate
        """
        from models.competition.models import Gara
        from models.competition.state_service import StateService

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if not gara.can_modify_inscription_dates():
            raise ValueError(
                "Impossibile modificare le date: il primo turno è già stato avviato!"
            )

        if inscription_start > inscription_end:
            raise ValueError(
                "La data di inizio deve essere precedente alla data di fine!"
            )

        # Verifica che la fine iscrizioni non sia dopo la data della gara
        if gara.date and inscription_end.date() > gara.date:
            raise ValueError(
                "Le iscrizioni non possono terminare dopo la data della gara!"
            )

        current_status = gara.status or GaraStatus.SETUP.value

        # Aggiorna le date
        gara.inscription_start = inscription_start
        gara.inscription_end = inscription_end

        # Gestione intelligente dello stato
        now = datetime.utcnow()

        # Se le iscrizioni devono ancora iniziare
        if inscription_start > now:
            # Solo se non siamo già in setup, torniamo in setup
            if current_status == GaraStatus.INSCRIPTION.value:
                gara = StateService.reopen_setup(gara)

        # Se siamo nel periodo di iscrizione
        elif inscription_start <= now <= inscription_end:
            # Solo se non siamo già in inscription, passiamo a inscription
            if current_status == GaraStatus.SETUP.value:
                gara = StateService.to_inscription(gara)
            # Se siamo già in inscription, non fare nulla (solo aggiorna le date)

        # Se le iscrizioni sono terminate
        elif now > inscription_end:
            # Se eravamo in inscription e ora sono scadute, manteniamo inscription
            # (sarà il sistema a gestire la transizione quando si avvia il turno)
            pass

        db.session.add(gara)
        # Transaction managed by @transactional decorator
        return gara

    @staticmethod
    def can_start_with_current_inscriptions(gara_id: int) -> bool:
        """Verifica se una gara può iniziare con le iscrizioni attuali."""
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False

        # Conta le iscrizioni attive (escludi lista d'attesa)
        active_inscriptions = (
            db.session.query(Inscription)
            .filter_by(gara_id=gara_id, is_waitlist=False)
            .count()
        )

        # Verifica se soddisfa il numero minimo di partecipanti
        return active_inscriptions >= gara.min_participants


__all__ = ["InscriptionService"]
