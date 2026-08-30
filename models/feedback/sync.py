"""Il giro giornaliero: rispedisce, rilegge, notifica.

Un solo punto in cui l'app parla con GitHub in scrittura *e* in lettura, e
un solo punto in cui nascono le notifiche delle segnalazioni. Il job in
`scripts/daily_jobs.py` è un guscio: chiama `giro_completo()` e stampa il
riepilogo.

Due proprietà che vanno lette insieme, perché è per esse che il codice ha
questa forma:

* **un guasto non ferma il giro.** Se GitHub risponde male, le rispedizioni
  già riuscite restano, il polling salta e il prossimo giro riprova. Un job
  che solleva a metà lascerebbe lo stato peggiore di quello di partenza;
* **il segnaposto avanza solo dopo un giro riuscito.** Spostare
  `ultimo_controllo` dopo un errore vorrebbe dire non rileggere mai più le
  issue cambiate in quella finestra — un guasto silenzioso che si scopre mesi
  dopo, quando qualcuno chiede perché non è mai stato avvisato.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from flask_babel import gettext as _

from models.base import db, utc_now
from models.transaction.manager import transactional

from .github_client import GitHubClient, IssueRemota
from .models import FeedbackReport, FeedbackStatus, FeedbackSyncState
from .service import ETICHETTA_SEGNALAZIONE, FeedbackService

logger = logging.getLogger(__name__)

#: Quante rispedizioni per giro. Oltre questo, un guasto prolungato
#: trasformerebbe il job notturno in una raffica di chiamate: meglio
#: recuperare l'arretrato in qualche notte che farsi limitare da GitHub.
MAX_RISPEDIZIONI_PER_GIRO = 25


class FeedbackSync:
    """Rispedizione, polling e notifiche delle segnalazioni."""

    @staticmethod
    def giro_completo() -> Dict[str, Any]:
        """Le tre cose, in quest'ordine. Torna il riepilogo per il job."""
        cliente = GitHubClient.dalla_configurazione()
        if not cliente.configurato:
            # Il job deve **dirlo forte**: senza token le segnalazioni si
            # accumulano tutte in attesa, e un giro che tace sembra riuscito.
            in_attesa = len(FeedbackService.in_attesa_di_invio())
            return {
                "spedite": 0,
                "aggiornate": 0,
                "notificate": 0,
                "nota": (
                    "GITHUB_FEEDBACK_TOKEN non impostato: "
                    f"{in_attesa} segnalazioni restano in attesa"
                ),
            }

        spedite = FeedbackSync.rispedisci_le_rimaste()
        aggiornate, notificate, nota = FeedbackSync.rileggi_da_github(cliente)

        return {
            "spedite": spedite,
            "aggiornate": aggiornate,
            "notificate": notificate,
            "nota": nota,
        }

    # ── 1. Rispedizione ────────────────────────────────────────────────────

    @staticmethod
    def rispedisci_le_rimaste() -> int:
        """Le segnalazioni senza issue riprovano, le più vecchie per prime.

        Prima del polling, di proposito: una segnalazione nata stamattina può
        così diventare issue *e* ricevere il suo stato nello stesso giro.
        """
        in_attesa = FeedbackService.in_attesa_di_invio()[:MAX_RISPEDIZIONI_PER_GIRO]
        riuscite = 0
        for segnalazione in in_attesa:
            if FeedbackService.spedisci(segnalazione.id):
                riuscite += 1
        return riuscite

    # ── 2 e 3. Rilettura e notifiche ───────────────────────────────────────

    @staticmethod
    def rileggi_da_github(cliente: GitHubClient):
        """Chiede le issue toccate, aggiorna, notifica. `(agg, notif, nota)`."""
        stato = FeedbackSyncState.corrente()
        db.session.commit()

        da_quando = (
            stato.ultimo_controllo.replace(microsecond=0).isoformat() + "Z"
            if stato.ultimo_controllo
            else None
        )
        inizio_giro = utc_now()

        esito = cliente.issue_toccate(
            etichetta=ETICHETTA_SEGNALAZIONE,
            da_quando=da_quando,
            etag=stato.etag,
        )

        if not esito.ok:
            # Il segnaposto NON si sposta: la finestra va riletta domani.
            logger.warning("Polling delle segnalazioni fallito: %s", esito.errore)
            return 0, 0, f"polling fallito: {esito.errore}"

        if esito.non_modificato:
            FeedbackSync._segna_giro_riuscito(stato, inizio_giro, esito.etag)
            return 0, 0, None

        issue = [
            IssueRemota.da_json(dato)
            for dato in (esito.corpo or [])
            # Le pull request arrivano nella stessa lista delle issue e non
            # sono segnalazioni di nessuno: si riconoscono da questa chiave.
            if isinstance(dato, dict) and "pull_request" not in dato
        ]
        aggiornate, notificate = FeedbackSync._applica(cliente, issue)
        FeedbackSync._segna_giro_riuscito(stato, inizio_giro, esito.etag)
        return aggiornate, notificate, None

    @staticmethod
    @transactional(domain="feedback")
    def _applica(cliente: GitHubClient, issue: List[IssueRemota]):
        """Scrive gli stati nuovi e crea le notifiche. Una transazione sola.

        `@transactional` sta **qui** e non nei metodi chiamati: sono decine di
        righe per giro, e un commit per riga moltiplicherebbe le scritture su
        un SQLite che vive su NFS.
        """
        per_numero = FeedbackService.per_numero_issue([i.numero for i in issue])
        aggiornate = notificate = 0

        for remota in issue:
            segnalazione = per_numero.get(remota.numero)
            if segnalazione is None:
                # Una issue con l'etichetta ma senza segnalazione dietro: l'ha
                # scritta un umano a mano. Non è un errore, non è roba nostra.
                continue

            nota = FeedbackSync._nota_se_serve(cliente, remota)
            stato_cambiato, nota_cambiata = FeedbackService.applica_aggiornamento(
                segnalazione,
                FeedbackService.stato_da_issue(remota),
                nota,
            )
            if not (stato_cambiato or nota_cambiata):
                continue

            aggiornate += 1
            if FeedbackSync._notifica(segnalazione):
                notificate += 1

        return aggiornate, notificate

    @staticmethod
    def _nota_se_serve(cliente: GitHubClient, remota: IssueRemota) -> Optional[str]:
        """I commenti si chiedono solo per le issue che sono cambiate.

        Sono una chiamata per issue: farla per tutte, a ogni giro, sarebbe il
        contrario di quello che ci siamo ripromessi con l'`ETag`. Qui la
        lista è già ristretta a ciò che GitHub ha segnalato come toccato.
        """
        esito = cliente.commenti(remota.numero)
        if not esito.ok:
            # La nota è un di più: senza, lo stato si aggiorna lo stesso.
            return None
        return FeedbackService.nota_pubblica(esito.corpo or [])

    @staticmethod
    def _notifica(segnalazione: FeedbackReport) -> bool:
        """Avvisa chi ha scritto. `False` se la notifica non è partita.

        L'errore si cattura: la segnalazione è **già** aggiornata, e far
        fallire il giro per una notifica vorrebbe dire perdere anche gli
        aggiornamenti delle altre. Ma finisce nel log — e quindi in GlitchTip
        — perché un utente che non viene avvisato è un guasto senza sintomi.
        """
        from models.notification.models import NotificationPriority, NotificationType
        from models.notification.services import NotificationService

        etichette = {
            FeedbackStatus.PRESA_IN_CARICO.value: _(
                "La tua segnalazione è stata presa in considerazione"
            ),
            FeedbackStatus.RISOLTA.value: _("La tua segnalazione è stata risolta"),
            FeedbackStatus.NON_PREVISTA.value: _(
                "Sulla tua segnalazione abbiamo deciso di non intervenire"
            ),
            FeedbackStatus.RICEVUTA.value: _("Ci sono novità sulla tua segnalazione"),
        }

        try:
            NotificationService.create_notification(
                user_id=segnalazione.user_id,
                notification_type=NotificationType.FEEDBACK_UPDATE,
                title=etichette.get(
                    segnalazione.stato, _("Novità sulla tua segnalazione")
                ),
                message=segnalazione.nota_pubblica or segnalazione.titolo,
                priority=NotificationPriority.NORMAL,
                action_url="/segnalazioni/",
                action_text=_("Vedi le tue segnalazioni"),
                related_entities={"feedback_report_id": segnalazione.id},
            )
            return True
        except Exception:
            logger.error(
                "Notifica di aggiornamento segnalazione non inviata "
                "(utente=%s, segnalazione=%s)",
                segnalazione.user_id,
                segnalazione.id,
                exc_info=True,
            )
            return False

    @staticmethod
    @transactional(domain="feedback")
    def _segna_giro_riuscito(
        stato: FeedbackSyncState, momento, etag: Optional[str]
    ) -> None:
        """Sposta il segnaposto. Solo dopo che il giro è andato a buon fine.

        Il momento è quello **d'inizio** del giro, non della fine: fra le due
        cose GitHub può aver ricevuto una modifica, e datare alla fine la
        renderebbe invisibile per sempre.
        """
        stato.ultimo_controllo = momento
        stato.etag = etag
