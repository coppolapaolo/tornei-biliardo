# routes/feedback.py
"""Segnalare un problema dall'app (issue #255).

Prefix ``/segnalazioni`` e non ``/admin``: chi segnala è un giocatore. L'unica
voce riservata è l'elenco completo, che sta sotto ``/segnalazioni/tutte`` con
il suo ``@admin_required``.

Il repo del backlog è **privato**, quindi da qui non esce mai un link a
github.com: l'utente vedrebbe un 404. Quello che sa di GitHub è zero — legge
uno stato in italiano e, quando c'è, la frase che gli abbiamo scritto.
"""

from __future__ import annotations

import logging

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import _
from flask_login import current_user, login_required

from models.exceptions import ValidationError
from models.feedback.models import FeedbackStatus, FeedbackType
from models.feedback.service import FeedbackService
from utils.permissions import admin_required
from utils.rate_limiter import limiter

logger = logging.getLogger(__name__)

feedback_bp = Blueprint("feedback", __name__, url_prefix="/segnalazioni")

#: Quanto del contesto tecnico si tiene. Lo user agent è lungo e verboso, e
#: oltre questa soglia non aggiunge niente a chi legge la issue.
MAX_USER_AGENT = 300


def _contesto_tecnico() -> dict:
    """Ciò che l'utente non saprebbe dare e che serve sempre.

    Nessun dato personale: niente email, niente indirizzo IP. Il ruolo e
    l'username bastano a inquadrare la segnalazione, e chi ha scritto lo dice
    già il legame nel nostro DB.
    """
    return {
        "pagina di provenienza": request.referrer or "—",
        "versione": current_app.config.get("VERSION", "?"),
        "ruolo": getattr(current_user, "role", "?"),
        "browser": (request.user_agent.string or "—")[:MAX_USER_AGENT],
        "lingua": request.accept_languages.best or "—",
    }


@feedback_bp.route("/", methods=["GET"])
@login_required
def le_mie_segnalazioni():
    """Le sue segnalazioni e, in fondo, le novità che le riguardano."""
    return render_template(
        "feedback/index.html",
        segnalazioni=FeedbackService.mie_segnalazioni(current_user.id),
        novita=FeedbackService.novita(current_user.id),
        etichette_stato=etichette_stato(),
    )


@feedback_bp.route("/nuova", methods=["GET"])
@login_required
def nuova_segnalazione():
    """Il modulo. Tre campi, non uno di più."""
    return render_template(
        "feedback/nuova.html",
        tipi=list(FeedbackType),
        etichette_tipo=etichette_tipo(),
        descrizioni_tipo=descrizioni_tipo(),
    )


@feedback_bp.route("/nuova", methods=["POST"])
@login_required
@limiter.limit("5/hour", methods=["POST"])
def invia_segnalazione():
    """Salva, poi prova a spedire.

    La spedizione può fallire — token assente, GitHub in 5xx, rete muta — e
    l'utente vede «ricevuta» lo stesso, perché lo è: la riga è sul nostro DB e
    il job giornaliero la rispedisce. Mostrargli un errore vorrebbe dire
    buttare via il testo che ha appena scritto.
    """
    try:
        segnalazione = FeedbackService.registra(
            user_id=current_user.id,
            tipo=request.form.get("tipo", ""),
            titolo=request.form.get("titolo", ""),
            corpo=request.form.get("corpo", ""),
            contesto=_contesto_tecnico(),
        )
    except ValidationError as errore:
        flash(str(errore), "error")
        return redirect(url_for("feedback.nuova_segnalazione"))

    FeedbackService.spedisci(segnalazione.id)

    flash(
        _("Segnalazione ricevuta. Ti avvisiamo qui quando ci sono novità."),
        "success",
    )
    return redirect(url_for("feedback.le_mie_segnalazioni"))


@feedback_bp.route("/tutte", methods=["GET"])
@login_required
@admin_required
def tutte_le_segnalazioni():
    """Vista dell'admin: tutte, col numero della issue e l'ultimo errore."""
    return render_template(
        "feedback/tutte.html",
        segnalazioni=FeedbackService.tutte(),
        etichette_stato=etichette_stato(),
        etichette_tipo=etichette_tipo(),
    )


# ── Il vocabolario che legge l'utente ──────────────────────────────────────
#
# Gli stati interni hanno nomi da database; questi sono i nomi da persona. La
# traduzione sta qui e non nei template perché la usano tre schermate, e due
# frasi diverse per lo stesso stato sarebbero un difetto invisibile.
#
# Sono funzioni e non costanti perché `_()` si valuta alla chiamata: un
# dizionario costruito all'import parlerebbe per sempre la lingua del primo
# worker avviato, e chi legge in inglese vedrebbe l'italiano.


def etichette_stato() -> dict:
    return {
        FeedbackStatus.RICEVUTA.value: _("Ricevuta, la guarderemo presto"),
        FeedbackStatus.PRESA_IN_CARICO.value: _("Presa in considerazione"),
        FeedbackStatus.RISOLTA.value: _("Fatto"),
        FeedbackStatus.NON_PREVISTA.value: _("Per ora non la faremo"),
    }


def etichette_tipo() -> dict:
    return {
        FeedbackType.BUG.value: _("Qualcosa non funziona"),
        FeedbackType.IDEA.value: _("Ho un'idea"),
        FeedbackType.DOMANDA.value: _("Non ho capito come si fa"),
    }


def descrizioni_tipo() -> dict:
    return {
        FeedbackType.BUG.value: _("Una cosa che dovrebbe funzionare e non va"),
        FeedbackType.IDEA.value: _("Qualcosa che vorresti trovare nell'app"),
        FeedbackType.DOMANDA.value: _("Cerchi una funzione e non la trovi"),
    }


__all__ = [
    "feedback_bp",
    "etichette_stato",
    "etichette_tipo",
    "descrizioni_tipo",
]
