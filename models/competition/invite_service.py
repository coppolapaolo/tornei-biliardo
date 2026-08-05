"""Link pubblico di iscrizione a una singola gara (issue #61).

Il direttore condivide `/g/<token>` su una locandina o un post. Chi lo segue
non conosce l'applicazione: arriva da fuori, e la risposta deve essere
corretta anche quando la gara non è iscrivibile (iscrizioni non ancora
aperte, chiuse, gara in corso o conclusa).

Qui vive solo la decisione — *cosa* deve succedere a questo utente su questa
gara. Il testo mostrato e il redirect stanno nella route: così la decisione è
verificabile senza un client HTTP e senza contesto di traduzione.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from models.base import utc_now
from models.exceptions import ConflictError, PermissionDeniedError
from models.status_enum import GaraStatus


class InviteOutcome(str, Enum):
    """Esito della visita a un link pubblico di iscrizione."""

    INSCRIBED = "inscribed"  # iscritto adesso, seguendo il link
    WAITLISTED = "waitlisted"  # iscritto adesso, ma in lista d'attesa
    ALREADY_INSCRIBED = "already_inscribed"  # era già iscritto
    CONFIRM_NEEDED = "confirm_needed"  # può iscriversi, decide lui col pulsante
    NOT_OPEN_YET = "not_open_yet"  # iscrizioni non ancora aperte
    CLOSED = "closed"  # iscrizioni chiuse
    IN_PROGRESS = "in_progress"  # gara già iniziata
    COMPLETED = "completed"  # gara conclusa
    CANCELLED = "cancelled"  # gara annullata
    NOT_ELIGIBLE = "not_eligible"  # admin, direttore della gara, playoff
    ERROR = "error"  # iscrizione fallita


@dataclass(frozen=True)
class InviteResult:
    """Esito + il dato che serve al messaggio (posizione in lista d'attesa)."""

    outcome: InviteOutcome
    waitlist_position: Optional[int] = None


# Un utente in questi stati non si iscrive più: la gara è oltre la fase utile.
_TERMINAL_STATUSES = {
    GaraStatus.PLAYING.value: InviteOutcome.IN_PROGRESS,
    GaraStatus.AWAITING_SSR.value: InviteOutcome.IN_PROGRESS,
    GaraStatus.COMPLETED.value: InviteOutcome.COMPLETED,
    GaraStatus.CANCELLED.value: InviteOutcome.CANCELLED,
}


class GaraInviteService:
    """Decide l'esito di una visita al link pubblico di una gara."""

    @staticmethod
    def evaluate(gara, user, *, auto_inscribe: bool) -> InviteResult:
        """Cosa deve succedere a `user` che apre il link di `gara`.

        Args:
            gara: la gara puntata dal token (già risolta e non cancellata).
            user: utente autenticato.
            auto_inscribe: True quando l'utente arriva direttamente dal link
                (l'issue chiede che sia già iscritto all'arrivo). False quando
                torna dal login: lì l'iscrizione deve restare un gesto suo, un
                click sul pulsante, non l'effetto collaterale di un login.

        Returns:
            InviteResult: nessuna eccezione esce da qui — ogni caso è un
            esito da mostrare all'utente, non un errore.
        """
        from models.competition.models import Inscription

        existing = Inscription.query.filter_by(user_id=user.id, gara_id=gara.id).first()
        if existing is not None and not existing.is_withdrawn:
            # Prima di ogni altro controllo: a chi è già iscritto va detto che
            # è iscritto, anche se nel frattempo le iscrizioni si sono chiuse.
            return InviteResult(
                InviteOutcome.ALREADY_INSCRIBED,
                waitlist_position=(
                    existing.waitlist_position if existing.is_waitlist else None
                ),
            )

        if not GaraInviteService.is_eligible(gara, user):
            return InviteResult(InviteOutcome.NOT_ELIGIBLE)

        blocked = _TERMINAL_STATUSES.get(gara.status)
        if blocked is not None:
            return InviteResult(blocked)

        if gara.status != GaraStatus.INSCRIPTION.value:
            # SETUP: la gara esiste ma il direttore non ha ancora aperto.
            return InviteResult(InviteOutcome.NOT_OPEN_YET)

        now = utc_now()
        if gara.inscription_start and now < gara.inscription_start:
            return InviteResult(InviteOutcome.NOT_OPEN_YET)
        if gara.inscription_end and now > gara.inscription_end:
            return InviteResult(InviteOutcome.CLOSED)

        if not auto_inscribe:
            return InviteResult(InviteOutcome.CONFIRM_NEEDED)

        return GaraInviteService._inscribe(gara, user)

    @staticmethod
    def is_eligible(gara, user) -> bool:
        """Chi non può giocare questa gara non va iscritto di soppiatto.

        Admin non partecipa ai tornei; chi gestisce *questa* gara nemmeno
        (arrivare sul proprio link non deve trasformare il direttore in
        concorrente); i playoff sono riservati ai qualificati.
        """
        if not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_admin", False):
            return False
        if gara.is_playoff:
            return False
        can_manage = getattr(user, "can_manage_competition", None)
        if callable(can_manage) and can_manage(gara.id):
            return False
        return True

    @staticmethod
    def inscription_open(gara) -> bool:
        """True se in questo momento la gara accetta iscrizioni.

        Unica lettura della finestra di iscrizione condivisa fra il link
        pubblico e il pulsante «Iscriviti» della pagina gara: mostrare il
        pulsante con criteri diversi da quelli che poi lo accettano è il modo
        classico per farlo rispondere "le iscrizioni non sono disponibili".
        """
        if gara.status != GaraStatus.INSCRIPTION.value:
            return False
        now = utc_now()
        if gara.inscription_start and now < gara.inscription_start:
            return False
        if gara.inscription_end and now > gara.inscription_end:
            return False
        return True

    @staticmethod
    def _inscribe(gara, user) -> InviteResult:
        from models.competition.inscription_service import InscriptionService

        try:
            inscription = InscriptionService.inscribe_user(
                user_id=user.id, gara_id=gara.id
            )
        except (ConflictError, PermissionDeniedError):
            # Il servizio rivalida le stesse condizioni con la propria
            # sensibilità: se le vede diversamente (finestra chiusa un istante
            # fa) l'utente vede "non è stato possibile", non un 500.
            return InviteResult(InviteOutcome.ERROR)

        if inscription is None:
            return InviteResult(InviteOutcome.ERROR)
        if inscription.is_waitlist:
            return InviteResult(
                InviteOutcome.WAITLISTED,
                waitlist_position=inscription.waitlist_position,
            )
        return InviteResult(InviteOutcome.INSCRIBED)
