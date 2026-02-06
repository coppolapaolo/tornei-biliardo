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

from models.base import db, utc_now
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

        Gestisce due tipi di waitlist:
        - CAPACITY: max_participants superato
        - PARITY: odd_number_policy="no" e count diventa dispari

        Con policy NO, ordine di controllo:
        1. Prima verifica capacità (max_participants)
        2. Poi verifica parità (odd_number_policy="no")
        """
        from models.competition.models import Gara, WaitlistReason
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
        now = utc_now()
        if gara.inscription_start and gara.inscription_end:
            if now < gara.inscription_start:
                raise ValueError("Iscrizioni non ancora aperte")
            if now > gara.inscription_end:
                raise ValueError("Iscrizioni chiuse")

        # Conta iscrizioni attive (non in waitlist)
        active_count = (
            db.session.query(Inscription)
            .filter_by(gara_id=gara_id, is_waitlist=False, is_withdrawn=False)
            .count()
        )

        # Conta iscrizioni in waitlist
        total_count = (
            db.session.query(Inscription)
            .filter_by(gara_id=gara_id, is_withdrawn=False)
            .count()
        )

        is_waitlist = False
        waitlist_reason = None
        waitlist_position = None

        # 1. Verifica capacità (max_participants)
        if gara.max_participants and gara.max_participants > 0:
            if total_count >= gara.max_participants:
                is_waitlist = True
                waitlist_reason = WaitlistReason.CAPACITY.value
                waitlist_position = (
                    gara.get_waitlist_count() + 1
                    if hasattr(gara, "get_waitlist_count")
                    else total_count - gara.max_participants + 1
                )

        # 2. Verifica parità (odd_number_policy="no")
        # Solo se non siamo già in waitlist per capacità
        # E solo se ci sarà più di 1 giocatore (il primo deve sempre essere accettato)
        if not is_waitlist and gara.odd_number_policy == "no":
            new_active_count = active_count + 1

            # Conta chi è già in parity waitlist
            parity_waitlist_count = (
                db.session.query(Inscription)
                .filter_by(
                    gara_id=gara_id,
                    is_waitlist=True,
                    waitlist_reason=WaitlistReason.PARITY.value,
                    is_withdrawn=False,
                )
                .count()
            )

            if new_active_count > 1 and new_active_count % 2 == 1:
                # Risultato sarebbe dispari
                if parity_waitlist_count > 0:
                    # C'è qualcuno in parity waitlist: accetta nuovo E promuovi
                    # Così: active+1+1 = even
                    pass  # Non mettere in waitlist, promozione avverrà dopo
                else:
                    # Nessuno in waitlist: metti in waitlist
                    is_waitlist = True
                    waitlist_reason = WaitlistReason.PARITY.value
                    waitlist_position = 1

        ins = Inscription(
            user_id=user_id,
            gara_id=gara_id,
            is_waitlist=is_waitlist,
            waitlist_position=waitlist_position,
            waitlist_reason=waitlist_reason,
        )
        db.session.add(ins)
        db.session.flush()  # Get ID for event

        # Se abbiamo aggiunto un giocatore attivo e c'è qualcuno in waitlist parità,
        # promuovilo (perché ora abbiamo reso pari il count)
        if not is_waitlist and gara.odd_number_policy == "no":
            InscriptionService._promote_from_parity_waitlist(gara_id)

        # Emit InscriptionCreatedEvent for gamification
        from models.events.competition_events import InscriptionCreatedEvent
        from models.events.base import EventBus

        gara_name = gara.name or f"Gara {gara.number}"
        inscription_status = "waitlist" if is_waitlist else "confirmed"

        event = InscriptionCreatedEvent(
            inscription_id=ins.id if ins.id else 0,
            gara_id=gara_id,
            gara_name=gara_name,
            user_id=user_id,
            username=user.username,
            inscription_status=inscription_status,
            waitlist_position=waitlist_position
        )
        EventBus.publish(event)

        # Transaction managed by @transactional decorator
        return ins

    @staticmethod
    def _promote_from_parity_waitlist(gara_id: int) -> Optional[Inscription]:
        """Promuove il primo giocatore dalla waitlist parità.

        Chiamato quando un nuovo giocatore si iscrive e rende il count pari.
        """
        from models.competition.models import WaitlistReason

        first_parity_waitlist = (
            db.session.query(Inscription)
            .filter_by(
                gara_id=gara_id,
                is_waitlist=True,
                waitlist_reason=WaitlistReason.PARITY.value,
                is_withdrawn=False,
            )
            .order_by(Inscription.waitlist_position.asc())
            .first()
        )

        if first_parity_waitlist:
            first_parity_waitlist.is_waitlist = False
            first_parity_waitlist.waitlist_position = None
            first_parity_waitlist.waitlist_reason = None

            # Ricalcola posizioni degli altri in waitlist parità
            remaining = (
                db.session.query(Inscription)
                .filter_by(
                    gara_id=gara_id,
                    is_waitlist=True,
                    waitlist_reason=WaitlistReason.PARITY.value,
                    is_withdrawn=False,
                )
                .order_by(Inscription.waitlist_position.asc())
                .all()
            )
            for i, insc in enumerate(remaining, 1):
                insc.waitlist_position = i

            return first_parity_waitlist
        return None

    @staticmethod
    def _demote_last_to_parity_waitlist(gara_id: int) -> Optional[Inscription]:
        """Mette l'ultimo iscritto attivo in waitlist parità.

        Chiamato quando una disiscrizione rende il count dispari.
        """
        from models.competition.models import WaitlistReason

        # Trova l'ultimo iscritto attivo (per created_at)
        last_active = (
            db.session.query(Inscription)
            .filter_by(
                gara_id=gara_id,
                is_waitlist=False,
                is_withdrawn=False,
            )
            .order_by(Inscription.created_at.desc())
            .first()
        )

        if last_active:
            # Conta quanti sono già in waitlist parità
            parity_waitlist_count = (
                db.session.query(Inscription)
                .filter_by(
                    gara_id=gara_id,
                    is_waitlist=True,
                    waitlist_reason=WaitlistReason.PARITY.value,
                    is_withdrawn=False,
                )
                .count()
            )

            last_active.is_waitlist = True
            last_active.waitlist_reason = WaitlistReason.PARITY.value
            last_active.waitlist_position = parity_waitlist_count + 1

            return last_active
        return None

    @staticmethod
    @transactional(domain="competition")
    def uninscribe_user(user_id: int, gara_id: int) -> bool:
        """Cancella l'iscrizione di un utente dalla gara.

        Gestisce due casi:
        1. Se c'è waitlist capacità, promuove il primo
        2. Se odd_number_policy="no" e count diventa dispari, demota l'ultimo

        Returns: True se rimossa, False se non trovata.
        """
        from models.competition.models import Gara, WaitlistReason

        inscription = (
            db.session.query(Inscription)
            .filter_by(user_id=user_id, gara_id=gara_id)
            .first()
        )
        if inscription:
            was_active = not inscription.is_waitlist and not inscription.is_withdrawn
            was_parity_waitlist = (
                inscription.is_waitlist
                and inscription.waitlist_reason == WaitlistReason.PARITY.value
            )
            gara_id_for_promotion = inscription.gara_id

            db.session.delete(inscription)
            db.session.flush()

            gara = db.session.get(Gara, gara_id_for_promotion)
            if not gara:
                return True

            # Se l'utente era in parity waitlist, ricalcola le posizioni
            if was_parity_waitlist:
                remaining_parity = (
                    db.session.query(Inscription)
                    .filter_by(
                        gara_id=gara_id_for_promotion,
                        is_waitlist=True,
                        waitlist_reason=WaitlistReason.PARITY.value,
                        is_withdrawn=False,
                    )
                    .order_by(Inscription.waitlist_position.asc())
                    .all()
                )
                for i, insc in enumerate(remaining_parity, 1):
                    insc.waitlist_position = i
                return True

            # Se l'utente era attivo
            if was_active:
                # Conta iscrizioni attive rimanenti
                active_count = (
                    db.session.query(Inscription)
                    .filter_by(
                        gara_id=gara_id_for_promotion,
                        is_waitlist=False,
                        is_withdrawn=False,
                    )
                    .count()
                )

                # Caso 1: Promuovi dalla waitlist capacità se c'è spazio
                if gara.max_participants and gara.max_participants > 0:
                    first_capacity_waitlist = (
                        db.session.query(Inscription)
                        .filter_by(
                            gara_id=gara_id_for_promotion,
                            is_waitlist=True,
                            waitlist_reason=WaitlistReason.CAPACITY.value,
                            is_withdrawn=False,
                        )
                        .order_by(Inscription.waitlist_position.asc())
                        .first()
                    )

                    if first_capacity_waitlist:
                        InscriptionService._promote_and_notify(
                            first_capacity_waitlist, gara
                        )
                        return True

                # Caso 2: Se odd_number_policy="no" e count è ora dispari
                if gara.odd_number_policy == "no" and active_count % 2 == 1:
                    # Prima verifica se c'è qualcuno in parity waitlist da promuovere
                    first_parity = (
                        db.session.query(Inscription)
                        .filter_by(
                            gara_id=gara_id_for_promotion,
                            is_waitlist=True,
                            waitlist_reason=WaitlistReason.PARITY.value,
                            is_withdrawn=False,
                        )
                        .order_by(Inscription.waitlist_position.asc())
                        .first()
                    )

                    if first_parity:
                        # Promuovi dalla parity waitlist
                        InscriptionService._promote_and_notify(first_parity, gara)
                    else:
                        # Nessuno in parity waitlist, demota l'ultimo attivo
                        InscriptionService._demote_last_to_parity_waitlist(
                            gara_id_for_promotion
                        )

                # Caso 3: Standard waitlist (senza reason specificato)
                else:
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
                        InscriptionService._promote_and_notify(first_waitlist, gara)

            return True
        return False

    @staticmethod
    def _promote_and_notify(inscription: Inscription, gara: "Gara") -> None:
        """Promuove un'iscrizione dalla waitlist e invia notifica."""
        from models.notification.factory import NotificationFactory
        from models.notification.models import NotificationPriority

        old_reason = inscription.waitlist_reason
        inscription.is_waitlist = False
        inscription.waitlist_position = None
        inscription.waitlist_reason = None

        # Ricalcola posizioni degli altri nella stessa waitlist
        if old_reason:
            remaining = (
                db.session.query(Inscription)
                .filter_by(
                    gara_id=inscription.gara_id,
                    is_waitlist=True,
                    waitlist_reason=old_reason,
                    is_withdrawn=False,
                )
                .order_by(Inscription.waitlist_position.asc())
                .all()
            )
        else:
            remaining = (
                db.session.query(Inscription)
                .filter_by(
                    gara_id=inscription.gara_id,
                    is_waitlist=True,
                    is_withdrawn=False,
                )
                .order_by(Inscription.waitlist_position.asc())
                .all()
            )

        for i, insc in enumerate(remaining, 1):
            insc.waitlist_position = i

        # Invia notifica
        gara_display = gara.name or f'Gara {gara.number}'
        msg = (
            f"Sei stato promosso dalla lista d'attesa "
            f"per la gara '{gara_display}'"
        )
        try:
            NotificationFactory.create_account_update_notification(
                user_id=inscription.user_id,
                title="Posto disponibile!",
                message=msg,
                priority=NotificationPriority.HIGH,
                update_type="waitlist_promotion",
                related_entities={
                    "gara_id": gara.id,
                    "gara_name": gara.name
                }
            )
        except Exception as e:
            print(f"DEBUG: Error creating promotion notification: {e}")

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
        now = utc_now()

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
