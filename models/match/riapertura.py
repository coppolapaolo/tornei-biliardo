"""Una partita riaperta dai giocatori si riprende il tavolo, se può.

La doppia conferma chiude la partita e libera il tavolo, che passa subito alla
prima partita in attesa (`TableAssignmentService.release_and_reassign_table`).
«Annulla ultimo triangolo» la riapre: è quasi sempre un errore di inserimento
sull'ultimo triangolo — segnato il 5 a uno che era ancora a 4 — e i due sono
ancora al tavolo a giocare. Fino al 2026-10-29 la riapertura lasciava la
partita senza tavolo, e il segnapunti, che senza tavolo spegneva il +1, non
permetteva più di andare avanti.

Cosa succede adesso (decisione dell'utente del 2026-10-29):

* il tavolo d'origine è ancora libero → torna alla partita, e nessuno se ne
  accorge;
* è già passato a un'altra partita → la riaperta prende un altro tavolo
  libero, se c'è, altrimenti resta senza. In entrambi i casi i direttori
  ricevono un avviso: i due giocatori sono probabilmente ancora al tavolo
  d'origine, e chi l'ha ricevuto potrebbe trovarlo occupato.

Senza tavolo la partita **non si blocca**: si continua a segnare e ad annullare
(`Match.aspetta_un_tavolo`). Il tavolo serve per cominciare, non per finire.
"""

from __future__ import annotations

from typing import Optional

from models.base import db
from models.status_enum import MatchStatus

from .models import Match


def _nomi(match: Match) -> str:
    giocatori = [p.username for p in (match.player1, match.player2) if p]
    trio = match.trio_match if match.is_trio else None
    if trio is not None and trio.player3 is not None:
        giocatori.append(trio.player3.username)
    return " – ".join(giocatori)


def riprendi_il_tavolo(match: Match) -> None:
    """Rimette un tavolo alla partita appena riaperta, e avvisa se non è il suo.

    Si chiama con la partita già tornata in gioco, dentro la transazione di chi
    l'ha riaperta.
    """
    if match.table_assignment or not match.gara_id or match.is_bye:
        return
    gara = match.gara
    if gara is None or not gara.get_available_tables():
        return

    from .table_assignment_service import TableAssignmentService

    db.session.flush()
    originale = match.played_on_table
    liberi = TableAssignmentService._get_free_tables(match.gara_id)
    if originale and originale in liberi:
        match.table_assignment = originale
        return

    occupante: Optional[Match] = None
    if originale:
        occupante = Match.query.filter(
            Match.gara_id == match.gara_id,
            Match.table_assignment == originale,
            Match.status == MatchStatus.PLAYING.value,
            Match.id != match.id,
        ).first()
    nuovo = liberi[0] if liberi else None
    if nuovo:
        match.table_assignment = nuovo
    _avvisa_i_direttori(match, originale, nuovo, occupante)


def _avvisa_i_direttori(
    match: Match,
    originale: Optional[str],
    nuovo: Optional[str],
    occupante: Optional[Match],
) -> None:
    from flask_babel import gettext as _

    from models.competition.direzione import direzione_della_gara
    from models.notification.models import NotificationPriority, NotificationType
    from models.notification.services import NotificationService

    gara = match.gara
    partita = _nomi(match)
    altra = _nomi(occupante) if occupante is not None else None

    def messaggio() -> str:
        if altra and nuovo:
            return _(
                "%(partita)s è stata riaperta dopo l'ultimo triangolo, ma il "
                "tavolo %(tavolo)s era già passato a %(altra)s. Le è stato "
                "assegnato il tavolo %(nuovo)s: i due però probabilmente stanno "
                "ancora giocando al %(tavolo)s, e %(altra)s potrebbero trovarlo "
                "occupato.",
                partita=partita,
                tavolo=originale,
                altra=altra,
                nuovo=nuovo,
            )
        if altra:
            return _(
                "%(partita)s è stata riaperta dopo l'ultimo triangolo e si gioca "
                "senza tavolo: il %(tavolo)s era già passato a %(altra)s, che "
                "potrebbero trovarlo ancora occupato. Assegnale un tavolo appena "
                "se ne libera uno.",
                partita=partita,
                tavolo=originale,
                altra=altra,
            )
        if nuovo:
            return _(
                "%(partita)s è stata riaperta dopo l'ultimo triangolo: le è "
                "stato assegnato il tavolo %(nuovo)s.",
                partita=partita,
                nuovo=nuovo,
            )
        return _(
            "%(partita)s è stata riaperta dopo l'ultimo triangolo e si gioca "
            "senza tavolo. Assegnale un tavolo appena se ne libera uno.",
            partita=partita,
        )

    for direttore in direzione_della_gara(gara):
        NotificationService.create_notification(
            user_id=direttore.utente.id,
            notification_type=NotificationType.TAVOLO_DA_SISTEMARE,
            title=lambda: _("Tavolo da sistemare · %(gara)s", gara=gara.name),
            message=messaggio,
            priority=NotificationPriority.HIGH,
            related_entities={"gara_id": gara.id, "match_id": match.id},
            action_url=f"/admin/gara/{gara.id}",
        )
