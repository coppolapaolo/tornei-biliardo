"""Le regole delle segnalazioni: cosa si spedisce, e cosa si dice a chi legge.

Tre decisioni stanno qui e in nessun altro posto.

**Salvare prima, spedire poi.** `registra` scrive la riga e *poi* prova a
creare la issue; se la creazione non riesce, la segnalazione resta con
`issue_number` NULL e l'utente vede comunque «ricevuta». Il rinvio è compito
del job giornaliero. Chiamare GitHub dentro la richiesta e mostrare un errore
perderebbe il testo appena scritto.

**Cosa vuol dire «presa in considerazione».** È la domanda centrale, perché è
ciò che l'utente legge, e la risposta è una funzione sola —
`stato_da_issue`. Non basta l'etichetta che ci ha messo l'app aprendo la
issue: quella non è una lettura umana. Serve un segno che qualcuno l'abbia
guardata davvero — un'etichetta d'area, un assegnatario, una milestone.

**Cosa dell'issue arriva all'utente.** Solo un commento che comincia con il
marcatore `@utente:`. Sulla issue si deve poter ragionare — scrivere «forse è
lo stesso bug della #212», sbagliarsi, cambiare idea — senza che ogni parola
finisca sotto gli occhi di chi ha segnalato.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from flask_babel import gettext as _

from models.base import db, utc_now
from models.exceptions import ValidationError
from models.transaction.manager import transactional

from .github_client import GitHubClient, IssueRemota
from .models import (
    MAX_BODY_LENGTH,
    MAX_TITLE_LENGTH,
    FeedbackReport,
    FeedbackStatus,
    FeedbackType,
)

logger = logging.getLogger(__name__)

#: L'etichetta che distingue ciò che arriva da fuori da ciò che scriviamo noi.
#: È anche il filtro con cui il job interroga GitHub: una sola chiamata.
ETICHETTA_SEGNALAZIONE = "segnalazione"

#: Un commento arriva all'utente **solo** se comincia così.
MARCATORE_PUBBLICO = "@utente:"

#: Etichette che dichiarano «non la faremo», anche a issue ancora aperta.
ETICHETTE_NON_PREVISTA = {"wontfix", "duplicate", "invalid"}

#: Le etichette che l'app mette da sola aprendo la issue: trovarle non
#: significa che qualcuno l'abbia letta.
ETICHETTE_AUTOMATICHE = {ETICHETTA_SEGNALAZIONE} | {t.value for t in FeedbackType}


class FeedbackService:
    """Segnalazioni: registrazione, spedizione, e ritorno degli stati."""

    # ── Registrazione ──────────────────────────────────────────────────────

    @staticmethod
    @transactional(domain="feedback")
    def registra(
        user_id: int,
        tipo: str,
        titolo: str,
        corpo: str,
        contesto: Optional[Dict[str, Any]] = None,
    ) -> FeedbackReport:
        """Salva la segnalazione. La spedizione è un secondo momento.

        Solleva `ValidationError` se il modulo è incompleto: sono i tre campi
        che l'utente ha compilato, e un errore qui glielo si dice subito.
        """
        tipo_enum = FeedbackType.parse(tipo)
        if tipo_enum is None:
            raise ValidationError(_("Scegli di cosa si tratta."))

        titolo = (titolo or "").strip()
        corpo = (corpo or "").strip()
        if not titolo:
            raise ValidationError(_("Serve un titolo, anche breve."))
        if not corpo:
            raise ValidationError(_("Racconta cosa è successo."))
        if len(titolo) > MAX_TITLE_LENGTH:
            raise ValidationError(
                _(
                    "Il titolo è troppo lungo: al massimo %(max)s caratteri.",
                    max=MAX_TITLE_LENGTH,
                )
            )
        if len(corpo) > MAX_BODY_LENGTH:
            raise ValidationError(
                _(
                    "Il racconto è troppo lungo: al massimo %(max)s caratteri.",
                    max=MAX_BODY_LENGTH,
                )
            )

        segnalazione = FeedbackReport(
            user_id=user_id,
            tipo=tipo_enum.value,
            titolo=titolo,
            corpo=corpo,
            contesto=json.dumps(contesto or {}, ensure_ascii=False),
            stato=FeedbackStatus.RICEVUTA.value,
            stato_cambiato_il=utc_now(),
        )
        db.session.add(segnalazione)
        return segnalazione

    # ── Spedizione ─────────────────────────────────────────────────────────

    @staticmethod
    @transactional(domain="feedback")
    def spedisci(segnalazione_id: int) -> bool:
        """Prova a far nascere la issue. `False` se non ci è riuscita.

        Non solleva mai per un guasto di GitHub: l'errore si annota sulla
        riga e il prossimo giro riprova. Chi chiama — la route dopo il
        salvataggio, o il job — non deve avere un modo di rompersi qui.
        """
        segnalazione = db.session.get(FeedbackReport, segnalazione_id)
        if segnalazione is None or segnalazione.issue_number is not None:
            return False

        cliente = GitHubClient.dalla_configurazione()
        tipo = segnalazione.tipo_enum
        esito = cliente.crea_issue(
            titolo=segnalazione.titolo,
            corpo=FeedbackService.corpo_issue(segnalazione),
            etichette=[ETICHETTA_SEGNALAZIONE] + ([tipo.label_github] if tipo else []),
        )

        segnalazione.tentativi_invio = (segnalazione.tentativi_invio or 0) + 1
        if not esito.ok:
            segnalazione.ultimo_errore = (esito.errore or "")[:500]
            return False

        segnalazione.issue_number = (esito.corpo or {}).get("number")
        # Un errore vecchio accanto a una issue creata racconterebbe un guasto
        # che non c'è più.
        segnalazione.ultimo_errore = None
        return segnalazione.issue_number is not None

    @staticmethod
    def corpo_issue(segnalazione: FeedbackReport) -> str:
        """Il testo dell'utente più il contesto tecnico, in fondo e separato.

        **Niente email né dati personali**: username e id bastano a risalire a
        chi ha scritto, e il legame vive nel nostro DB.
        """
        utente = segnalazione.user
        chi = utente.username if utente else f"utente {segnalazione.user_id}"
        righe = [
            segnalazione.corpo,
            "",
            "---",
            "",
            "<!-- Aperta da Tornei Biliardo. Rispondere all'utente: un "
            f"commento che comincia con `{MARCATORE_PUBBLICO}` gli arriva "
            "in notifica; ogni altro commento resta fra noi. -->",
            "",
            f"**Segnalata da** `{chi}` (id {segnalazione.user_id}) · "
            f"segnalazione #{segnalazione.id}",
        ]

        contesto = FeedbackService.contesto_dizionario(segnalazione)
        if contesto:
            righe += ["", "<details><summary>Contesto tecnico</summary>", ""]
            righe += [f"- **{k}**: {v}" for k, v in contesto.items() if v]
            righe += ["", "</details>"]
        return "\n".join(righe)

    @staticmethod
    def contesto_dizionario(segnalazione: FeedbackReport) -> Dict[str, Any]:
        """Il contesto salvato, o vuoto se illeggibile.

        Un JSON storto non deve impedire la spedizione: il testo dell'utente
        vale più del contesto, che è un di più raccolto dall'app.
        """
        if not segnalazione.contesto:
            return {}
        try:
            dato = json.loads(segnalazione.contesto)
        except (ValueError, TypeError):
            logger.warning(
                "Contesto illeggibile sulla segnalazione %s", segnalazione.id
            )
            return {}
        return dato if isinstance(dato, dict) else {}

    # ── Ritorno degli stati ────────────────────────────────────────────────

    @staticmethod
    def stato_da_issue(issue: IssueRemota) -> FeedbackStatus:
        """La regola che decide cosa legge l'utente. Unica, e qui.

        L'ordine dei controlli conta: una issue chiusa dice già tutto, e va
        letta prima delle etichette. Fra le aperte, «non la faremo» è più
        specifico di «l'abbiamo guardata», quindi viene prima.
        """
        etichette = {e.lower() for e in issue.etichette}

        if issue.stato == "closed":
            if issue.motivo_chiusura == "not_planned":
                return FeedbackStatus.NON_PREVISTA
            if etichette & ETICHETTE_NON_PREVISTA:
                return FeedbackStatus.NON_PREVISTA
            return FeedbackStatus.RISOLTA

        if etichette & ETICHETTE_NON_PREVISTA:
            return FeedbackStatus.NON_PREVISTA

        # «Presa in carico» vuol dire che una persona l'ha letta. Le etichette
        # che ci ha messo l'app aprendola non contano: sono nostre.
        if issue.ha_assegnatario or issue.ha_milestone:
            return FeedbackStatus.PRESA_IN_CARICO
        if etichette - ETICHETTE_AUTOMATICHE:
            return FeedbackStatus.PRESA_IN_CARICO

        return FeedbackStatus.RICEVUTA

    @staticmethod
    def nota_pubblica(commenti: List[Dict[str, Any]]) -> Optional[str]:
        """L'ultima frase scritta **per l'utente**, se c'è.

        L'ultima e non la prima: se il maintainer torna sulla issue e corregge
        quello che aveva detto, all'utente deve arrivare la versione buona.
        """
        marcate = [
            c.get("body", "")
            for c in commenti
            if (c.get("body") or "").lstrip().startswith(MARCATORE_PUBBLICO)
        ]
        if not marcate:
            return None
        testo = marcate[-1].lstrip()[len(MARCATORE_PUBBLICO) :].strip()
        return testo or None

    # ── Letture per le schermate ───────────────────────────────────────────

    @staticmethod
    def mie_segnalazioni(user_id: int) -> List[FeedbackReport]:
        """Le sue, la più recente in cima."""
        return (
            FeedbackReport.query.filter_by(user_id=user_id)
            .order_by(FeedbackReport.created_at.desc())
            .all()
        )

    @staticmethod
    def novita(user_id: int, limite: int = 5) -> List[FeedbackReport]:
        """Le sue segnalazioni che hanno cambiato stato, la più fresca in cima.

        Una segnalazione ancora «ricevuta» non è una novità: è lo stato in cui
        nasce, e mostrarla qui riempirebbe la sezione di non-notizie.
        """
        return (
            FeedbackReport.query.filter(
                FeedbackReport.user_id == user_id,
                FeedbackReport.stato != FeedbackStatus.RICEVUTA.value,
                FeedbackReport.stato_cambiato_il.isnot(None),
            )
            .order_by(FeedbackReport.stato_cambiato_il.desc())
            .limit(limite)
            .all()
        )

    @staticmethod
    def tutte(limite: int = 200) -> List[FeedbackReport]:
        """Vista dell'admin: tutte, la più recente in cima."""
        return (
            FeedbackReport.query.order_by(FeedbackReport.created_at.desc())
            .limit(limite)
            .all()
        )

    @staticmethod
    def in_attesa_di_invio() -> List[FeedbackReport]:
        """Salvate ma mai diventate una issue: le rispedisce il job."""
        return (
            FeedbackReport.query.filter(FeedbackReport.issue_number.is_(None))
            .order_by(FeedbackReport.created_at.asc())
            .all()
        )

    @staticmethod
    def per_numero_issue(numeri: List[int]) -> Dict[int, FeedbackReport]:
        """Le segnalazioni legate a quei numeri di issue, indicizzate.

        Una query sola invece di una per issue: il job ne aggiorna decine per
        volta.
        """
        if not numeri:
            return {}
        righe = FeedbackReport.query.filter(
            FeedbackReport.issue_number.in_(numeri)
        ).all()
        return {r.issue_number: r for r in righe if r.issue_number is not None}

    # ── Aggiornamento ──────────────────────────────────────────────────────

    @staticmethod
    def applica_aggiornamento(
        segnalazione: FeedbackReport,
        nuovo_stato: FeedbackStatus,
        nota: Optional[str],
    ) -> Tuple[bool, bool]:
        """Scrive stato e nota. Torna `(stato cambiato, nota cambiata)`.

        Chi chiama decide se notificare: cambia lo stato **o** compare una
        frase nuova. Senza questa distinzione un giro del job che non trova
        nulla di nuovo manderebbe comunque una notifica a tutti.

        Non `@transactional`: il job ne aggiorna molte e committa una volta
        sola — annidare i decoratori farebbe rollback (ADR-012).
        """
        stato_cambiato = segnalazione.stato != nuovo_stato.value
        nota_cambiata = nota is not None and nota != segnalazione.nota_pubblica

        if stato_cambiato:
            segnalazione.stato = nuovo_stato.value
            segnalazione.stato_cambiato_il = utc_now()
        if nota_cambiata:
            segnalazione.nota_pubblica = nota
            if not stato_cambiato:
                # La sezione «Novità» ordina per questa data: una frase nuova
                # è una novità quanto un cambio di stato.
                segnalazione.stato_cambiato_il = utc_now()

        return stato_cambiato, nota_cambiata
