"""Sfide a due che aspettano la conferma di un giocatore (2026-09-14).

Una sfida a due si chiude con la **doppia conferma** dei giocatori (ADR-051).
Quando si raggiunge la distanza chi vince firma d'ufficio
(``IndividualRackService.add_rack_for_player``); nel formato libero firma chi
preme «Termina». Da quel momento la partita aspetta la firma dell'altro — ed è
lì che resta, quando l'altro non la dà mai.

Regole, decise dall'utente il 2026-09-14 (``SPECIFICHE.md``, nota datata):

* **dashboard** — passato un giorno dalla prima firma
  (:data:`DASHBOARD_GRACE`), la partita non compare più fra le sfide in corso
  della dashboard, né per chi deve firmare né per chi aspetta. Resta
  nell'elenco delle sfide con lo stato «In attesa di conferma»;
* **blocco** — chi ha almeno una partita che aspetta la **sua** firma non può
  lanciare né accettare altre sfide individuali finché non la conferma o la
  rifiuta. Il blocco scatta subito, non dopo un giorno: il giorno riguarda
  solo la dashboard. Chi aspetta non è mai bloccato per questo.

«Aspetta la firma di X» vuol dire: partita in corso, pronta per la validazione,
l'avversario ha già confermato e X no. Una partita senza nessuna firma non
aspetta nessuno in particolare: nel formato libero è «pronta» fin dal primo
triangolo, mentre i due stanno ancora giocando.

La **partita di altri due** (ADR-084) non entra in nessuna di queste regole:
non l'hanno chiesta i giocatori, quindi non li blocca, e non aspetta una firma
sola ma la decisione di ciascuno. L'avviso a fine referto va a **entrambi**;
quello del rifiuto all'altro giocatore e a chi l'ha segnata (2026-10-18).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from flask_babel import ngettext
from sqlalchemy import and_, or_

from ..base import utc_now
from ..exceptions import ConflictError
from ..status_enum import MatchStatus
from .match_models import IndividualMatch

#: Quanto resta in dashboard una partita che aspetta una conferma, contato
#: dalla prima firma.
DASHBOARD_GRACE = timedelta(hours=24)


class PendingConfirmationError(ConflictError):
    """Il giocatore ha partite da confermare prima di altre sfide (HTTP 409).

    ``match_ids`` elenca le partite che aspettano la sua firma: la route le usa
    per proporgli di chiuderle invece di un errore secco.
    """

    def __init__(self, match_ids: List[int], message: Optional[str] = None):
        self.match_ids = list(match_ids)
        if message is None:
            message = ngettext(
                "Hai una partita che aspetta la tua conferma: confermala o "
                "rifiutala prima di altre sfide.",
                "Hai %(num)d partite che aspettano la tua conferma: confermale o "
                "rifiutale prima di altre sfide.",
                len(self.match_ids),
            )
        super().__init__(message)


class PendingConfirmationService:
    """Chi deve firmare cosa, e cosa ne consegue."""

    @staticmethod
    def pending_for(user_id: int) -> List[IndividualMatch]:
        """Le partite che aspettano la firma di ``user_id``, dalla più vecchia."""
        candidate = (
            IndividualMatch.query.filter(
                IndividualMatch.status == MatchStatus.IN_PROGRESS,
                # La partita di un terzo non blocca chi non l'ha chiesta.
                IndividualMatch.scorer_id.is_(None),
                or_(
                    and_(
                        IndividualMatch.player1_id == user_id,
                        IndividualMatch.player2_confirmed.is_(True),
                        IndividualMatch.player1_confirmed.is_(False),
                    ),
                    and_(
                        IndividualMatch.player2_id == user_id,
                        IndividualMatch.player1_confirmed.is_(True),
                        IndividualMatch.player2_confirmed.is_(False),
                    ),
                ),
            )
            .order_by(IndividualMatch.id.asc())
            .all()
        )
        # Il filtro SQL guarda le firme; «pronta per la validazione» dipende
        # dalla distanza effettiva (Distance VO), e si chiede al modello.
        return [m for m in candidate if m.awaiting_confirmation_from_id == user_id]

    @staticmethod
    def ensure_none_pending(user_id: int) -> None:
        """Solleva :class:`PendingConfirmationError` se qualcuna aspetta lui."""
        pending = PendingConfirmationService.pending_for(user_id)
        if pending:
            raise PendingConfirmationError([m.id for m in pending])

    @staticmethod
    def is_hidden_from_dashboard(
        match: IndividualMatch, now: Optional[datetime] = None
    ) -> bool:
        """Vero se la partita aspetta una firma da più di un giorno.

        Vale per entrambi i giocatori: per chi aspetta non c'è niente da fare,
        per chi deve firmare il promemoria è il blocco sulle sfide nuove.
        Senza l'orario della prima firma (righe antecedenti alla colonna) il
        giorno non si può contare, e la partita resta visibile.
        """
        since = match.awaiting_confirmation_since
        if since is None:
            return False
        return (now or utc_now()) - since > DASHBOARD_GRACE


def pagina_della_sfida(match: IndividualMatch) -> str:
    """Il link della sfida nelle notifiche, scritto per esteso.

    Niente ``url_for``: la notifica può nascere fuori da una richiesta.
    """
    return f"/match/matches/{match.id}"


def _nome(match: IndividualMatch, user_id: int) -> str:
    giocatore = match.player1 if user_id == match.player1_id else match.player2
    return giocatore.username if giocatore is not None else ""


def avvisa_chi_deve_firmare(match: IndividualMatch) -> None:
    """Alla prima firma, una notifica a chi deve ancora firmare (2026-10-17).

    Fino a questa data arrivava solo l'evento in tempo reale: chi non aveva la
    pagina aperta non sapeva di avere una sfida da confermare. La firma nasce
    in tre posti — la conferma, la firma d'ufficio alla distanza, il referto
    TPA — e ognuno chiama questa funzione dopo ``confirm_result``.

    Un avviso ancora da leggere basta: un rifiuto seguito da una nuova firma,
    o un triangolo tolto e rimesso, non ne accumulano altri.

    Nella partita di altri due la chiama la chiusura del referto, e scrive a
    **entrambi** i giocatori (ADR-084).
    """
    from flask_babel import lazy_gettext as _l

    from models.notification.models import NotificationPriority, NotificationType
    from models.notification.services import NotificationService

    if match.scorer_id is not None:
        _avvisa_i_due_giocatori(match)
        return

    destinatario_id = match.awaiting_confirmation_from_id
    if destinatario_id is None:
        return

    link = pagina_della_sfida(match)
    if _gia_avvisato(destinatario_id, link):
        return

    firmatario_id = (
        match.player1_id if destinatario_id == match.player2_id else match.player2_id
    )
    NotificationService.create_notification(
        user_id=destinatario_id,
        notification_type=NotificationType.MATCH_RESULT_TO_CONFIRM,
        title=_l("Una sfida aspetta la tua firma"),
        message=_l(
            "%(nome)s ha firmato il risultato della vostra sfida "
            "(%(p1)s-%(p2)s): confermalo o rifiutalo.",
            nome=_nome(match, firmatario_id),
            p1=match.player1_score,
            p2=match.player2_score,
        ),
        priority=NotificationPriority.NORMAL,
        related_entities={"individual_match_id": match.id},
        action_url=link,
        action_text=_l("Apri la sfida"),
    )


def _gia_avvisato(destinatario_id: int, link: str) -> bool:
    """Un avviso «da firmare» ancora da leggere, per questa sfida."""
    from models.notification.models import (
        Notification,
        NotificationStatus,
        NotificationType,
    )

    return (
        Notification.query.filter(
            Notification.user_id == destinatario_id,
            Notification.notification_type == NotificationType.MATCH_RESULT_TO_CONFIRM,
            Notification.action_url == link,
            Notification.status.in_(  # type: ignore[attr-defined]
                [NotificationStatus.PENDING, NotificationStatus.SENT]
            ),
        ).first()
        is not None
    )


def _avvisa_i_due_giocatori(match: IndividualMatch) -> None:
    """Chi segna ha chiuso il referto: tocca ai due giocatori (ADR-084).

    Uno per uno, a chi non ha ancora deciso, con la descrizione della partita:
    non l'hanno chiesta loro, e senza la descrizione non saprebbero di quale
    partita si tratta.
    """
    from flask_babel import lazy_gettext as _l

    from models.notification.models import NotificationPriority, NotificationType
    from models.notification.services import NotificationService

    link = pagina_della_sfida(match)
    chi_segna = match.scorer.username if match.scorer is not None else ""
    descrizione = match.description or ""
    for giocatore_id in (match.player1_id, match.player2_id):
        if not match.awaits_decision_from(giocatore_id):
            continue
        if _gia_avvisato(giocatore_id, link):
            continue
        NotificationService.create_notification(
            user_id=giocatore_id,
            notification_type=NotificationType.MATCH_RESULT_TO_CONFIRM,
            title=_l("Una partita aspetta la tua conferma"),
            message=(
                _l(
                    "%(scorer)s ha chiuso il referto di «%(descrizione)s» "
                    "(%(p1)s-%(p2)s): confermala o rifiutala.",
                    scorer=chi_segna,
                    descrizione=descrizione,
                    p1=match.player1_score,
                    p2=match.player2_score,
                )
                if descrizione
                else _l(
                    "%(scorer)s ha chiuso il referto della vostra partita "
                    "(%(p1)s-%(p2)s): confermala o rifiutala.",
                    scorer=chi_segna,
                    p1=match.player1_score,
                    p2=match.player2_score,
                )
            ),
            priority=NotificationPriority.NORMAL,
            related_entities={"individual_match_id": match.id},
            action_url=link,
            action_text=_l("Apri la partita"),
        )


def avvisa_annullata_da_chi_segna(match: IndividualMatch) -> None:
    """Chi segna ha annullato la partita: lo si dice ai due giocatori."""
    from flask_babel import lazy_gettext as _l

    from models.notification.models import NotificationPriority, NotificationType
    from models.notification.services import NotificationService

    chi_segna = match.scorer.username if match.scorer is not None else ""
    for giocatore_id in (match.player1_id, match.player2_id):
        NotificationService.create_notification(
            user_id=giocatore_id,
            notification_type=NotificationType.MATCH_CANCELLED,
            title=_l("Partita annullata"),
            message=_l(
                "%(scorer)s ha annullato la partita che stava segnando: non "
                "conta per nessuno dei due.",
                scorer=chi_segna,
            ),
            priority=NotificationPriority.NORMAL,
            related_entities={"individual_match_id": match.id},
            action_url=pagina_della_sfida(match),
            action_text=_l("Apri la partita"),
        )


def ritira_gli_avvisi_in_sospeso(match: IndividualMatch) -> None:
    """Gli avvisi ancora da leggere che portano a questa partita scadono.

    Dopo il rifiuto della partita di altri due nessuno dei due ha più niente
    da confermare: una richiesta — o l'avviso «qualcuno segna la tua
    partita» — rimasta nella casella porterebbe a una partita che non gli si
    mostra più. Scaduti e non cancellati: la storia delle notifiche resta
    com'era. Toglierli serve anche alla correzione: `_gia_avvisato` non
    salterebbe la richiesta nuova.
    """
    from models.notification.models import (
        Notification,
        NotificationStatus,
        NotificationType,
    )

    link = pagina_della_sfida(match)
    for avviso in Notification.query.filter(
        Notification.user_id.in_([match.player1_id, match.player2_id]),
        Notification.notification_type.in_(  # type: ignore[attr-defined]
            [NotificationType.MATCH_RESULT_TO_CONFIRM, NotificationType.MATCH_ACCEPTED]
        ),
        Notification.action_url == link,
        Notification.status.in_(  # type: ignore[attr-defined]
            [NotificationStatus.PENDING, NotificationStatus.SENT]
        ),
    ).all():
        avviso.status = NotificationStatus.EXPIRED


def avvisa_del_rifiuto(match: IndividualMatch, rifiutata_da: int) -> None:
    """Uno dei due ha rifiutato la partita di altri due: lo sanno tutti.

    Regola del 2026-10-18 (ADR-084, emendamento): un rifiuto basta, e lo
    vengono a sapere **l'altro giocatore** — che magari l'aveva confermata, e
    la vede sparire — e **chi l'ha segnata**, che può correggerla o
    cancellarla. Con la descrizione, se c'è: chi segna ne tiene più d'una.

    All'altro giocatore niente link alla partita: non gli si mostra più.
    """
    from flask_babel import gettext as _
    from flask_babel import lazy_gettext as _l

    from models.notification.models import NotificationPriority, NotificationType
    from models.notification.services import NotificationService

    ritira_gli_avvisi_in_sospeso(match)

    nome = _nome(match, rifiutata_da)
    descrizione = match.description or ""
    altro_id = (
        match.player2_id if rifiutata_da == match.player1_id else match.player1_id
    )

    def all_altro() -> str:
        if descrizione:
            return _(
                "%(nome)s ha rifiutato la partita «%(descrizione)s»: non conta "
                "per nessuno dei due.",
                nome=nome,
                descrizione=descrizione,
            )
        return _(
            "%(nome)s ha rifiutato la vostra partita segnata da un terzo: non "
            "conta per nessuno dei due.",
            nome=nome,
        )

    def a_chi_segna() -> str:
        if descrizione:
            return _(
                "%(nome)s ha rifiutato la partita «%(descrizione)s»: puoi "
                "correggerla o cancellarla.",
                nome=nome,
                descrizione=descrizione,
            )
        return _(
            "%(nome)s ha rifiutato la partita che hai segnato: puoi "
            "correggerla o cancellarla.",
            nome=nome,
        )

    NotificationService.create_notification(
        user_id=altro_id,
        notification_type=NotificationType.MATCH_CANCELLED,
        title=_l("Partita rifiutata"),
        message=all_altro,
        priority=NotificationPriority.NORMAL,
        related_entities={"individual_match_id": match.id},
    )
    if match.scorer_id is not None:
        NotificationService.create_notification(
            user_id=match.scorer_id,
            notification_type=NotificationType.MATCH_CANCELLED,
            title=_l("Partita rifiutata"),
            message=a_chi_segna,
            priority=NotificationPriority.HIGH,
            related_entities={"individual_match_id": match.id},
            action_url=pagina_della_sfida(match),
            action_text=_l("Apri la partita"),
        )


def avvisa_del_ritiro(
    match: IndividualMatch, ritirata_da: int, avversario_id: int
) -> None:
    """La sfida che aspettava la firma di ``avversario_id`` è stata ritirata."""
    from flask_babel import lazy_gettext as _l

    from models.notification.models import NotificationPriority, NotificationType
    from models.notification.services import NotificationService

    NotificationService.create_notification(
        user_id=avversario_id,
        notification_type=NotificationType.MATCH_CANCELLED,
        title=_l("Sfida ritirata"),
        message=_l(
            "%(nome)s ha ritirato la sfida che aspettava la tua firma: "
            "non conta più per nessuno dei due.",
            nome=_nome(match, ritirata_da),
        ),
        priority=NotificationPriority.NORMAL,
        related_entities={"individual_match_id": match.id},
        action_url=pagina_della_sfida(match),
        action_text=_l("Apri la sfida"),
    )


__all__ = [
    "DASHBOARD_GRACE",
    "PendingConfirmationError",
    "PendingConfirmationService",
    "avvisa_annullata_da_chi_segna",
    "avvisa_chi_deve_firmare",
    "avvisa_del_rifiuto",
    "avvisa_del_ritiro",
    "pagina_della_sfida",
    "ritira_gli_avvisi_in_sospeso",
]
