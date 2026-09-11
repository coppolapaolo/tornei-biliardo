# routes/admin/competition/prova.py
"""Le azioni della competizione di prova (ADR-058).

Tre, e nessuna esiste in una gara vera: popolare la gara di giocatori
fittizi — nella misura che il pulsante dice: il minimo, fino al massimo, uno
in più — simulare i risultati — una partita, il turno, tutta la gara — ed
eliminare la prova in qualunque stato. Tutto il resto — aprire le
iscrizioni, avviare i turni, segnare i punti — passa dalle route vere,
perché la prova **è** una gara vera con un flag.

Le regole stanno in `models/prova/service.py`; qui c'è solo la traduzione fra
richiesta e servizio, come in `vetrina.py`.
"""

from flask import abort, flash, redirect, url_for
from flask_babel import _, ngettext
from flask_login import login_required

from models import db, Gara
from models.exceptions import DomainError
from models.prova.service import MODALITA_ISCRIZIONE, ProvaService
from models.prova.simulation_service import AZIONI_SIMULAZIONE, SimulationService
from utils import gara_manager_required

from . import competition_bp


def _torna_alla_gara(gara_id: int) -> str:
    return url_for("admin.competition.gara_detail", gara_id=gara_id)


@competition_bp.route("/<int:gara_id>/prova/iscrivi/<modalita>", methods=["POST"])
@login_required
@gara_manager_required
def prova_iscrivi_fittizi(gara_id: int, modalita: str):
    """Crea e iscrive giocatori fittizi: il minimo, fino al massimo, uno."""
    gara = db.get_or_404(Gara, gara_id)
    if not gara.is_prova or modalita not in MODALITA_ISCRIZIONE:
        abort(404)
    try:
        quanti = ProvaService.iscrivi_fittizi(gara_id, modalita)
    except DomainError as errore:
        flash(str(errore), "danger")
        return redirect(_torna_alla_gara(gara_id))

    if quanti == 0:
        flash(_("Niente da aggiungere: gli iscritti sono già quelli."), "info")
    else:
        flash(
            _("Iscritti %(quanti)s giocatori fittizi.", quanti=quanti),
            "success",
        )
    return redirect(_torna_alla_gara(gara_id))


@competition_bp.route("/<int:gara_id>/prova/simula/<azione>", methods=["POST"])
@login_required
@gara_manager_required
def prova_simula(gara_id: int, azione: str):
    """Simula i risultati: una partita, il turno, tutta la gara.

    Le partite si chiudono nei due modi che il direttore deve imparare: le
    pari con la doppia conferma dei giocatori, le dispari restano da validare
    (`models/prova/simulation_service.py`). Il messaggio lo dice, perché è la
    prima cosa che deve capire guardando la pagina dopo il clic.
    """
    gara = db.get_or_404(Gara, gara_id)
    if not gara.is_prova or azione not in AZIONI_SIMULAZIONE:
        abort(404)
    try:
        esito = getattr(SimulationService, f"simula_{azione}")(gara_id)
    except DomainError as errore:
        flash(str(errore), "danger")
        return redirect(_torna_alla_gara(gara_id))

    if esito.partite_chiuse == 0 and esito.turni_avviati == 0:
        flash(_("Nessuna partita da simulare."), "info")
    elif azione == "gara":
        flash(
            ngettext(
                "Simulata %(quante)s partita fino alla fine della gara: le pari "
                "chiuse dai giocatori, le dispari validate come le avresti "
                "validate tu.",
                "Simulate %(quante)s partite fino alla fine della gara: le pari "
                "chiuse dai giocatori, le dispari validate come le avresti "
                "validate tu.",
                esito.partite_chiuse,
                quante=esito.partite_chiuse,
            ),
            "success",
        )
        if esito.fermata:
            flash(
                _("La simulazione si è fermata %(dove)s.", dove=esito.fermata),
                "warning",
            )
    else:
        flash(
            ngettext(
                "Simulata %(quante)s partita del turno %(turno)s. Se ha la "
                "doppia conferma è chiusa; altrimenti aspetta che tu la validi "
                "dal segnapunti.",
                "Simulate %(quante)s partite del turno %(turno)s. Quelle con la "
                "doppia conferma sono chiuse; le altre aspettano che tu le "
                "validi dal segnapunti.",
                esito.partite_chiuse,
                quante=esito.partite_chiuse,
                turno=esito.turno,
            ),
            "success",
        )
    return redirect(_torna_alla_gara(gara_id))


@competition_bp.route("/<int:gara_id>/prova/elimina", methods=["POST"])
@login_required
@gara_manager_required
def prova_elimina(gara_id: int):
    """Elimina la prova, in qualunque stato, con tutto ciò che le appartiene."""
    gara = db.get_or_404(Gara, gara_id)
    if not gara.is_prova:
        abort(404)
    nome = gara.display_name
    campionato_id = gara.campionato_id
    try:
        if campionato_id:
            ProvaService.elimina_prova(campionato_id=campionato_id)
        else:
            ProvaService.elimina_prova(gara_id=gara_id)
    except DomainError as errore:
        flash(str(errore), "danger")
        return redirect(_torna_alla_gara(gara_id))

    flash(_("Prova «%(nome)s» eliminata.", nome=nome), "success")
    return redirect(url_for("dashboard.dashboard"))
