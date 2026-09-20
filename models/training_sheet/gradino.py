"""Il passaggio di livello: chi lo sancisce, e quando (D8, ADR-071).

La fase 6 aveva lasciato aperta una domanda sola — **chi dice che hai passato
il livello?** — e la fase 8c l'aveva mostrata senza chiuderla: «Valuta il
passaggio di livello» diceva all'istruttore che l'allievo era pronto, e poi non
c'era niente da premere.

Qui si chiude, con tre risposte e non una (`LevelUp`):

* `none` — la scheda non è fatta a livelli, e il gradino non esiste;
* `auto` — lo sancisce la soglia stessa, alla seduta in cui viene tenuta. È la
  risposta di chi si allena da solo: senza, il suo gradino non lo timbrerebbe
  mai nessuno;
* `instructor` — lo conferma una persona, fra quelle che leggono la scheda.

**Superato è un fatto, non uno stato che va e viene.** Timbrato `passed_at`, la
scheda resta superata anche se le sedute dopo vanno peggio: è la differenza fra
un attestato e un termometro, e la stessa ragione per cui `break_player_id` si
persiste invece di essere dedotto a ogni lettura (ADR-056).

La regola del «quando» è una sola — `streak_above_threshold`, la stessa che
usano la fine seduta e «I miei allievi» — perché due copie che divergessero
direbbero all'istruttore che l'allievo è pronto e all'allievo di no.
"""

from __future__ import annotations

from typing import List, Optional

from flask_babel import gettext as _

from ..base import db, utc_now
from ..exceptions import ConflictError, PermissionDeniedError
from ..transaction.manager import transactional
from ..user.models import User
from .measure import LevelUp
from .models import TrainingSession, TrainingSheet
from .session_service import TrainingSessionService, streak_above_threshold


def gradino_raggiunto(
    sheet: TrainingSheet, sedute: Optional[List[TrainingSession]] = None
) -> bool:
    """Se la soglia è stata tenuta per quante sedute la scheda ne chiede.

    Dice soltanto che **si può** sancire: chi sancisce lo decide `level_up`, e
    una scheda già superata non si supera una seconda volta.

    ``sedute`` arriva dalla più recente (come le dà ``closed_sessions``); chi
    non le ha in mano le lascia fuori e se le fa cercare — ma chi disegna un
    elenco di venti allievi le ha già, e non può permettersi una query a testa.
    """
    if sheet.is_passed or sheet.threshold is None or sheet.level is None:
        return False
    if sedute is None:
        streak = TrainingSessionService.above_threshold_streak(sheet, sheet.owner_id)
    else:
        streak = streak_above_threshold(sheet, sedute)
    return streak >= (sheet.threshold_streak or 1)


class GradinoService:
    """Timbrare il passaggio di livello: da soli, o con una conferma."""

    @staticmethod
    @transactional(domain="training_sheet")
    def conferma(sheet_id: int, actor: User) -> TrainingSheet:
        """Un istruttore che legge la scheda sancisce il gradino.

        Tre condizioni, e ciascuna è una frase di questo lavoro: deve
        **leggere** la scheda (ADR-069: il permesso l'ha dato l'allievo), la
        scheda deve chiedere una **conferma** — con `auto` non c'è niente da
        confermare, l'ha già fatto la soglia — e la soglia deve essere stata
        davvero tenuta. Un istruttore non promuove chi non è arrivato: il
        gradino è un fatto, e questo è il posto in cui resta tale.
        """
        from .services import TrainingSheetService

        sheet = TrainingSheetService.get_sheet(sheet_id)
        if not getattr(actor, "is_instructor", False) or not (
            TrainingSheetService.can_read(sheet, actor)
        ):
            raise PermissionDeniedError(_("Non leggi questa scheda"))
        if sheet.level_up_kind is not LevelUp.INSTRUCTOR:
            raise ConflictError(
                _("Questa scheda non aspetta la conferma di un istruttore")
            )
        if sheet.is_passed:
            raise ConflictError(_("Questo livello è già superato"))
        if not gradino_raggiunto(sheet):
            raise ConflictError(_("La soglia non è ancora stata tenuta abbastanza"))

        return GradinoService._timbra(sheet, actor)

    @staticmethod
    def timbra_alla_soglia(sheet: TrainingSheet) -> bool:
        """Chiamata a fine seduta: timbra da sé se la scheda dice `auto`.

        Torna se ha timbrato. Non è `@transactional` di suo: gira **dentro** la
        chiusura della seduta, e deve essere salvata o annullata con lei — una
        seduta persa che lascia dietro un livello superato sarebbe un fatto
        senza il fatto che lo giustifica.
        """
        if sheet.level_up_kind is not LevelUp.AUTO or not gradino_raggiunto(sheet):
            return False
        GradinoService._timbra(sheet, None)
        return True

    # ────────────────────────────────────────────────────────────────────
    # Dentro
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _timbra(sheet: TrainingSheet, da: Optional[User]) -> TrainingSheet:
        sheet.passed_at = utc_now()
        sheet.passed_by_id = da.id if da is not None else None
        db.session.flush()
        GradinoService._avvisa(sheet, da)
        return sheet

    @staticmethod
    def _avvisa(sheet: TrainingSheet, da: Optional[User]) -> None:
        """Lo dice a chi la scheda è: è una notizia sua, non di chi l'ha data.

        Chi conferma lo sa già — l'ha appena premuto — e con `auto` non c'è
        nessuno da avvisare dall'altra parte (ADR-062: testo da comporre, che
        `create_notification` risolve nella lingua di chi riceve).
        """
        from flask_babel import lazy_gettext as _l

        from ..notification.models import NotificationPriority, NotificationType
        from ..notification.services import NotificationService

        if da is not None:
            testo = _l(
                "%(chi)s ha confermato: «%(scheda)s» è superata.",
                chi=da.username,
                scheda=sheet.name,
            )
        else:
            testo = _l(
                "Hai tenuto la soglia di «%(scheda)s»: livello superato.",
                scheda=sheet.name,
            )

        NotificationService.create_notification(
            user_id=sheet.owner_id,
            notification_type=NotificationType.SHEET_LEVEL_PASSED,
            title=_l("Livello superato"),
            message=testo,
            priority=NotificationPriority.NORMAL,
            action_url=f"/schede/{sheet.id}",
            action_text=_l("Apri la scheda"),
            related_entities={"sheet_id": sheet.id},
        )


__all__ = ["GradinoService", "gradino_raggiunto"]
