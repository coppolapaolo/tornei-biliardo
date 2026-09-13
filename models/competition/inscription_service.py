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

import logging
from typing import Optional
from datetime import datetime

from flask_babel import gettext as _

from models.base import db, utc_now
from models.status_enum import GaraStatus
from models.exceptions import (
    NotFoundError,
    ConflictError,
    ValidationError,
    PermissionDeniedError,
)
from .models import Inscription
from models.transaction.manager import transactional

# Forward import to avoid circular dependencies
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.competition.models import Gara

logger = logging.getLogger(__name__)


class InscriptionService:
    """Operazioni di business su Inscription."""

    @staticmethod
    @transactional(domain="competition")
    def inscribe_user(
        user_id: int,
        gara_id: int,
        _bypass_playoff_check: bool = False,
        _d_ufficio: bool = False,
    ) -> Optional[Inscription]:
        """Registra un utente a una gara se non già iscritto.

        Gestisce due tipi di waitlist:
        - CAPACITY: max_participants superato
        - PARITY: odd_number_policy="no" e count diventa dispari

        Con policy NO, ordine di controllo:
        1. Prima verifica capacità (max_participants)
        2. Poi verifica parità (odd_number_policy="no")

        Args:
            _bypass_playoff_check: Internal flag used by PlayoffService
                to inscribe qualified players into playoff gare.
            _d_ufficio: iscrizione decisa esplicitamente dal direttore di un
                playoff: entra sempre fra gli attivi, senza lista d'attesa né
                per capienza né per parità. Il limite dei posti vale per la
                cascata degli inviti, non per una scelta del direttore.
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

        # Playoff gare: inscription reserved to qualified players only
        if gara.is_playoff and not _bypass_playoff_check:
            raise PermissionDeniedError(
                "Gara playoff — iscrizione riservata ai qualificati"
            )

        user = db.session.get(User, user_id)
        if not user:
            return None

        # Validazione: Admin non può partecipare ai tornei
        if user.role == UserRole.ADMIN.value:
            raise PermissionDeniedError("Admin non può partecipare ai tornei")

        # Competizione di prova (ADR-058): solo fittizi, e i fittizi solo lì.
        # Il filtro di visibilità già nasconde la prova ai giocatori veri;
        # questo è il punto unico che lo garantisce anche a chi la vede.
        if gara.is_prova and not user.is_fittizio:
            raise PermissionDeniedError(
                "In una competizione di prova si iscrivono solo i giocatori fittizi"
            )
        if user.is_fittizio and not gara.is_prova:
            raise PermissionDeniedError(
                "Un giocatore fittizio gioca solo nella sua prova"
            )

        # Validazione: Verifica periodo di iscrizione
        # IMPORTANT: Use UTC for all datetime comparisons
        # Database stores naive datetimes which are treated as UTC
        # Chi entra in un playoff dall'invito non passa dalla finestra: la
        # finestra serve alle gare aperte a tutti, qui il biglietto è l'invito,
        # e un sì arrivato a finestra chiusa ma prima dell'avvio vale.
        now = utc_now()
        if (
            gara.inscription_start
            and gara.inscription_end
            and not _bypass_playoff_check
        ):
            if now < gara.inscription_start:
                raise ConflictError("Iscrizioni non ancora aperte")
            if now > gara.inscription_end:
                raise ConflictError("Iscrizioni chiuse")

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
        if not _d_ufficio and gara.max_participants and gara.max_participants > 0:
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
        if not is_waitlist and not _d_ufficio and gara.odd_number_policy == "no":
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
        # Squadra precompilata dal testo del profilo (US-1, US-8), e solo qui:
        # è l'unico momento in cui `user.squadra` viene letto. Se il testo non
        # corrisponde a nessuna voce dell'elenco l'iscrizione nasce senza
        # squadra e la voce si crea dalla schermata, che può prima mostrare i
        # nomi simili — cosa che qui, in automatico, sarebbe un doppione in più
        # invece che uno in meno.
        if gara.separate_teammates:
            from models.squadra.service import SquadraService

            suggerita = SquadraService.suggest_for_user(gara, user)
            if suggerita:
                ins.squadra_id = suggerita.id

        # Categoria riportata dalla gara precedente dello stesso campionato
        # (ADR-049). Senza, un campionato da otto prove significherebbe
        # riassegnare tutti otto volte; con, il direttore corregge soltanto chi
        # è cambiato di categoria. Si scrive il campo a mano invece di chiamare
        # `set_inscription_categoria_by_name`: siamo già dentro un metodo
        # `@transactional`, e annidarli fa rollback (ADR-012).
        if gara.effective_has_handicap:
            from models.categoria.service import CategoriaService

            categoria = CategoriaService.suggest_for_user(gara, user)
            if categoria:
                ins.categoria_id = categoria.id

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
            waitlist_position=waitlist_position,
        )
        EventBus.publish(event)

        # Transaction managed by @transactional decorator
        return ins

    @staticmethod
    def _promote_from_parity_waitlist(gara_id: int) -> Optional[Inscription]:
        """Promuove il primo giocatore dalla waitlist parità.

        Chiamato quando un nuovo giocatore si iscrive e rende il count pari.
        A gara avviata non promuove nessuno: vedi
        `_lista_attesa_ancora_aperta`.
        """
        from models.competition.models import Gara, WaitlistReason

        gara = db.session.get(Gara, gara_id)
        if gara is not None and not InscriptionService._lista_attesa_ancora_aperta(
            gara
        ):
            return None

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
    def _lista_attesa_ancora_aperta(gara: "Gara") -> bool:
        """La lista d'attesa serve **solo fino all'avvio della gara**.

        Dopo il primo turno la composizione degli iscritti è la base degli
        abbinamenti già sorteggiati e della classifica: promuovere qualcuno lo
        farebbe entrare senza i turni giocati e con zero punti, e retrocedere
        un attivo lo toglierebbe da partite che ha davanti (issue #260).

        Il controllo sta qui, non nei chiamanti, perché le strade che toccano
        la lista sono parecchie — disiscrizione volontaria, cancellazione dal
        direttore, esclusione per forfait, cambio del massimo iscritti — e
        presidiarle una a una lascerebbe scoperta la prossima.
        """
        return gara.status in (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value)

    @staticmethod
    def _demote_last_to_parity_waitlist(gara_id: int) -> Optional[Inscription]:
        """Mette l'ultimo iscritto attivo in waitlist parità.

        Chiamato quando una disiscrizione rende il count dispari.
        """
        from models.competition.models import Gara, WaitlistReason

        gara = db.session.get(Gara, gara_id)
        if gara is not None and not InscriptionService._lista_attesa_ancora_aperta(
            gara
        ):
            return None

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

                # Caso 1: Promuovi dalla waitlist capacità se c'è spazio. Lo
                # spazio va contato: in un playoff il direttore può iscrivere
                # oltre i posti, e allora un'uscita non libera un posto.
                if (
                    gara.max_participants
                    and gara.max_participants > 0
                    and active_count < gara.max_participants
                ):
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

                    # Stessa condizione del caso 1: si promuove solo se
                    # l'uscita ha liberato davvero un posto. In una gara
                    # normale gli attivi non superano mai il massimo, quindi
                    # dopo un'uscita il posto c'è sempre; in un playoff con
                    # aggiunte d'ufficio oltre i posti no.
                    posti_pieni = bool(
                        gara.max_participants
                        and gara.max_participants > 0
                        and active_count >= gara.max_participants
                    )
                    if first_waitlist and not posti_pieni:
                        InscriptionService._promote_and_notify(first_waitlist, gara)

            return True
        return False

    @staticmethod
    def _promote_and_notify(inscription: Inscription, gara: "Gara") -> None:
        """Promuove un'iscrizione dalla waitlist e invia notifica.

        A gara avviata non promuove nessuno: vedi
        `_lista_attesa_ancora_aperta`.
        """
        from models.notification.factory import NotificationFactory
        from models.notification.models import NotificationPriority

        if not InscriptionService._lista_attesa_ancora_aperta(gara):
            return

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
        gara_display = gara.name or f"Gara {gara.number}"
        msg = (
            f"Sei stato promosso dalla lista d'attesa " f"per la gara '{gara_display}'"
        )
        try:
            NotificationFactory.create_account_update_notification(
                user_id=inscription.user_id,
                title="Posto disponibile!",
                message=msg,
                priority=NotificationPriority.HIGH,
                update_type="waitlist_promotion",
                related_entities={"gara_id": gara.id, "gara_name": gara.name},
            )
        except Exception:
            # La promozione e' gia' avvenuta: il posto e' suo anche se la
            # notifica non parte. Per questo l'errore resta catturato — ma
            # deve arrivare a GlitchTip, altrimenti il giocatore promosso che
            # non viene avvisato e' un guasto senza sintomi (issue #256).
            logger.error(
                "Notifica di promozione dalla lista d'attesa non inviata "
                "(utente=%s, gara=%s)",
                inscription.user_id,
                gara.id,
                exc_info=True,
            )

    @staticmethod
    def nome_gara(gara: "Gara") -> str:
        """Il nome della gara come lo legge un giocatore in una notifica."""
        return gara.name or _("Gara %(numero)s", numero=gara.number)

    @staticmethod
    def notifica_di_gara(user_id: int, gara: "Gara", messaggio: str) -> None:
        """Una notifica a un iscritto su quello che il direttore ha fatto.

        Passa da `create_bulk_notification` e non da
        `create_tournament_notification`, che rilegge il testo con
        `str.format`: uno username con una graffa lo farebbe saltare. Il
        riferimento `gara_id` fa riconoscere la competizione di prova.
        """
        from models.notification.factory import NotificationFactory
        from models.notification.models import NotificationPriority, NotificationType

        NotificationFactory.create_bulk_notification(
            user_ids=[user_id],
            notification_type=NotificationType.TOURNAMENT_REGISTRATION,
            title=_("Aggiornamento gara"),
            message=messaggio,
            priority=NotificationPriority.HIGH,
            related_entities={
                "gara_id": gara.id,
                "tournament_id": gara.id,
                "tournament_name": InscriptionService.nome_gara(gara),
            },
            action_url=f"/gara/{gara.id}",
            action_text=_("Vedi la gara"),
        )

    @staticmethod
    @transactional(domain="competition")
    def admin_uninscribe_user(user_id: int, gara_id: int, admin_user_id: int) -> bool:
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

            was_active = not inscription.is_waitlist and not inscription.is_withdrawn
            gara_name = gara.name or f"Gara {gara.number}"

            # Invia notifica all'utente discritto. Fino al 2026-09-13 era una
            # f-string non tradotta che scriveva «L'direttore di gara»: ora
            # dice chi, per nome.
            try:
                if inscription.is_waitlist:
                    message = _(
                        "%(direttore)s ti ha tolto dalla lista d'attesa della "
                        "gara %(gara)s.",
                        direttore=admin_user.username,
                        gara=InscriptionService.nome_gara(gara),
                    )
                else:
                    message = _(
                        "%(direttore)s ha annullato la tua iscrizione alla gara "
                        "%(gara)s.",
                        direttore=admin_user.username,
                        gara=InscriptionService.nome_gara(gara),
                    )
                InscriptionService.notifica_di_gara(user_id, gara, str(message))
            except Exception:
                logger.error(
                    "Notifica di disiscrizione non inviata " "(utente=%s, gara=%s)",
                    user_id,
                    gara_id,
                    exc_info=True,
                )

            # Rimuovi l'iscrizione
            db.session.delete(inscription)
            # Flush così la riga rimossa non conta più nelle query sottostanti
            # (conteggio attivi per la parità).
            db.session.flush()

            # Se l'utente era attivo (non in lista d'attesa),
            # promuovi il primo della lista d'attesa
            if was_active:
                first_waitlist = (
                    db.session.query(Inscription)
                    .filter_by(gara_id=gara_id, is_waitlist=True, is_withdrawn=False)
                    .order_by(Inscription.waitlist_position.asc())
                    .first()
                )

                if first_waitlist:
                    # Promuovi dalla lista d'attesa
                    first_waitlist.is_waitlist = False
                    first_waitlist.waitlist_position = None
                    first_waitlist.waitlist_reason = None

                    # Ricalcola le posizioni degli altri in lista d'attesa
                    remaining_waitlist = (
                        db.session.query(Inscription)
                        .filter_by(
                            gara_id=gara_id, is_waitlist=True, is_withdrawn=False
                        )
                        .order_by(Inscription.waitlist_position.asc())
                        .all()
                    )

                    for i, insc in enumerate(remaining_waitlist, 1):
                        insc.waitlist_position = i

                    # Invia notifica al promosso
                    try:
                        from models.notification.factory import NotificationFactory
                        from models.notification.models import NotificationPriority

                        promo_msg = (
                            f"Sei stato promosso dalla lista d'attesa "
                            f"per {gara_name}"
                        )
                        notification_result = (
                            NotificationFactory.create_tournament_notification(
                                user_ids=[first_waitlist.user_id],
                                tournament_name=gara_name,
                                message_template=promo_msg,
                                priority=NotificationPriority.HIGH,
                                tournament_id=gara_id,
                            )
                        )
                        logger.debug(
                            "Notifica di promozione creata (utente=%s): %s",
                            first_waitlist.user_id,
                            notification_result,
                        )
                    except Exception:
                        logger.error(
                            "Notifica di promozione non inviata "
                            "(utente=%s, gara=%s)",
                            first_waitlist.user_id,
                            gara_id,
                            exc_info=True,
                        )

                # Nessuno da promuovere: se la gara non ammette numeri dispari
                # (odd_number_policy="no") e la rimozione ha reso il numero di
                # iscritti attivi dispari, l'ultimo iscritto va in waitlist
                # parità così da ripristinare la parità. Stessa logica di
                # `uninscribe_user` (Caso 2). Vedi issue #45.
                elif gara.odd_number_policy == "no":
                    active_count = (
                        db.session.query(Inscription)
                        .filter_by(
                            gara_id=gara_id,
                            is_waitlist=False,
                            is_withdrawn=False,
                        )
                        .count()
                    )
                    if active_count % 2 == 1:
                        InscriptionService._demote_last_to_parity_waitlist(gara_id)

            # Transaction managed by @transactional decorator
            return True
        return False

    @staticmethod
    def find_previous_gara_in_campionato(gara: "Gara") -> Optional["Gara"]:
        """Gara del campionato che precede ``gara`` per ``number``.

        None per le gare standalone e per la prima gara del campionato.
        """
        from models.competition.models import Gara

        if not gara.campionato_id:
            return None
        return (
            db.session.query(Gara)
            .filter(
                Gara.campionato_id == gara.campionato_id,
                Gara.number < gara.number,
                Gara.deleted_at.is_(None),
            )
            .order_by(Gara.number.desc())
            .first()
        )

    @staticmethod
    def copy_inscriptions_from_gara(source_gara_id: int, target_gara_id: int) -> int:
        """Copia gli iscritti attivi di una gara su un'altra. Ritorna quanti.

        Usata dall'opzione "auto-copia iscritti" alla creazione di una gara di
        campionato (issue #58): il flag esisteva solo lato client, dove
        precompilava i *parametri* della gara, e nessuno copiava le iscrizioni.

        Copia solo le iscrizioni attive (non ritirate, non in lista d'attesa):
        chi si era ritirato dalla prova precedente non viene riportato. Ogni
        giocatore passa da ``inscribe_user``, quindi capienza e policy sui
        numeri dispari della gara di destinazione sono rispettate (chi eccede
        finisce in lista d'attesa) e gli eventi di dominio sono emessi come per
        un'iscrizione manuale del director.

        Senza ``@transactional``: ogni ``inscribe_user`` porta il proprio, quindi
        un'iscrizione fallita non annulla quelle già copiate. (Il vecchio timore
        dei decoratori annidati non vale più dal 2026-09-13, ADR-061.)
        """
        source_inscriptions = (
            db.session.query(Inscription)
            .filter_by(gara_id=source_gara_id, is_withdrawn=False, is_waitlist=False)
            .order_by(Inscription.initial_order, Inscription.id)
            .all()
        )

        copied = 0
        for inscription in source_inscriptions:
            try:
                if InscriptionService.inscribe_user(
                    inscription.user_id, target_gara_id
                ):
                    copied += 1
            except (PermissionDeniedError, ConflictError):
                # Un singolo giocatore non copiabile (es. account passato ad
                # admin) non deve far fallire la copia degli altri.
                continue
        return copied

    @staticmethod
    @transactional(domain="competition")
    def open_inscriptions(
        gara_id: int,
        inscription_start: datetime,
        inscription_end: datetime,
        min_participants: Optional[int] = None,
        max_participants: Optional[int] = None,
    ) -> "Gara":
        """Apre le iscrizioni per una gara con validazione delle date.

        Minimo e massimo si decidono qui, nello stesso foglio delle date
        (canvas 1.8): sono i numeri che dicono se la gara parte e quando e'
        piena, e fino al 2026-09-12 stavano nella modifica della gara, cioe'
        altrove. `None` lascia quello che c'e'; il massimo accetta anche
        «senza limite» (0 o vuoto, che qui arriva come `max_participants=0`).

        Una fine oltre l'inizio della gara viene **accorciata** a quell'istante:
        iscriversi a partita cominciata non vuol dire niente. L'aggiustamento è
        silenzioso qui e visibile a chi chiama, che confronta
        `gara.inscription_end` con la fine richiesta (lo fa la route, con una
        nota in pagina).

        Prima l'aggiustamento veniva *annunciato* sollevando un ValueError. Ma
        il metodo è `@transactional`: l'eccezione faceva rollback, la correzione
        spariva con tutto il resto e la gara restava in `setup`. All'utente
        arrivava «È stata automaticamente impostata alla data della gara», una
        frase che descriveva qualcosa che non era successo, sopra a un'apertura
        che non aveva avuto luogo — e che quindi non aveva motivo di riprovare.
        """
        from models.competition.models import Gara
        from models.competition.state_service import StateService

        if inscription_start > inscription_end:
            raise ValidationError(
                "La data di inizio deve essere precedente alla data di fine!"
            )

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise NotFoundError(f"Gara {gara_id} non trovata")

        if min_participants is not None:
            if min_participants < 2:
                raise ValidationError("Servono almeno 2 iscritti per giocare")
            gara.min_participants = min_participants
        if max_participants is not None:
            if max_participants <= 0:
                gara.max_participants = None
            elif max_participants < (gara.min_participants or 0):
                raise ValidationError(
                    "Il massimo degli iscritti non puo' essere sotto il minimo"
                )
            else:
                gara.max_participants = max_participants

        if gara.date and gara.time:
            from datetime import datetime as dt

            gara_datetime = dt.combine(gara.date, gara.time)
            inscription_end = min(inscription_end, gara_datetime)

        gara.inscription_start = inscription_start
        gara.inscription_end = inscription_end
        return StateService.to_inscription(gara)

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
            raise NotFoundError(f"Gara {gara_id} non trovata")

        if not gara.can_modify_inscription_dates():
            raise ConflictError(
                "Impossibile modificare le date: il primo turno è già stato avviato!"
            )

        if inscription_start > inscription_end:
            raise ValidationError(
                "La data di inizio deve essere precedente alla data di fine!"
            )

        # Verifica che la fine iscrizioni non sia dopo la data della gara
        if gara.date and inscription_end.date() > gara.date:
            raise ValidationError(
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

        # Conta le iscrizioni attive (escludi lista d'attesa E ritirati, coerente
        # con la definizione canonica di "iscrizione attiva": is_withdrawn=False,
        # is_waitlist=False — vedi models/CLAUDE.md "Filtering Active Inscriptions")
        active_inscriptions = (
            db.session.query(Inscription)
            .filter_by(gara_id=gara_id, is_withdrawn=False, is_waitlist=False)
            .count()
        )

        # Verifica se soddisfa il numero minimo di partecipanti
        return active_inscriptions >= gara.min_participants


__all__ = ["InscriptionService"]
