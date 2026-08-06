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
from models.status_enum import GaraStatus


class InviteOutcome(str, Enum):
    """Esito della visita a un link pubblico di iscrizione."""

    ALREADY_INSCRIBED = "already_inscribed"  # era già iscritto
    ALREADY_WAITLISTED = "already_waitlisted"  # era già in lista d'attesa
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
    def evaluate(gara, user) -> InviteResult:
        """Cosa deve succedere a `user` che apre il link di `gara`.

        **Non iscrive mai.** L'issue chiedeva che chi segue il link si
        trovasse già iscritto all'arrivo, ma quel link vive su una locandina o
        un post: è pubblico per costruzione. Iscrivere durante una GET
        significa che chiunque lo conosca può incorporarlo altrove come
        `<img src="...">` e iscrivere a sua insaputa chi passa di lì con la
        sessione aperta — e un'iscrizione non voluta non è un fastidio
        estetico, occupa un posto e può spingere qualcun altro in lista
        d'attesa. Il token casuale rende il link non indovinabile, ma non
        cambia nulla qui: chi lo incorpora è proprio chi lo ha ricevuto.

        L'iscrizione resta la POST protetta da CSRF che era, a un click di
        distanza: chi può iscriversi riceve `CONFIRM_NEEDED` e il pulsante.

        Args:
            gara: la gara puntata dal token (già risolta e non cancellata).
            user: utente autenticato.

        Returns:
            InviteResult: nessuna eccezione esce da qui — ogni caso è un
            esito da mostrare all'utente, non un errore.
        """
        from models.competition.models import Inscription

        existing = Inscription.query.filter_by(user_id=user.id, gara_id=gara.id).first()
        if existing is not None and not existing.is_withdrawn:
            # Prima di ogni altro controllo: a chi è già iscritto va detto che
            # è iscritto, anche se nel frattempo le iscrizioni si sono chiuse.
            # Chi è in lista d'attesa NON è iscritto e basta: riaprire il link
            # e leggere "sei già iscritto" gli farebbe credere di avere un
            # posto. Esito distinto, così il messaggio riporta la posizione
            # esattamente come quando ci è finito.
            if existing.is_waitlist:
                return InviteResult(
                    InviteOutcome.ALREADY_WAITLISTED,
                    waitlist_position=existing.waitlist_position,
                )
            return InviteResult(InviteOutcome.ALREADY_INSCRIBED)

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

        return InviteResult(InviteOutcome.CONFIRM_NEEDED)

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
