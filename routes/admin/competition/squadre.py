# routes/admin/competition/squadre.py
"""Elenco squadre della competizione e squadra degli iscritti (US-2, 3, 8, 9).

Le regole (finestra di modifica, permessi, doppioni) stanno tutte in
``SquadraService``: qui c'e' solo la traduzione fra form e servizio, piu'
l'unica decisione che e' davvero di schermata — mostrare i nomi simili prima
di creare una voce nuova, invece di lasciar nascere il doppione e chiedere di
unirlo dopo (US-2).
"""

from flask import flash, redirect, request, url_for
from flask_babel import _
from flask_login import current_user, login_required

from models import db, Gara, Inscription
from models.exceptions import DomainError
from models.squadra.service import SquadraService
from utils import gara_manager_required
from utils.safe_redirect import safe_next_url
from utils.route_helpers import handle_service_action

from . import competition_bp

# Valore del select che significa "aggiungi una voce nuova all'elenco".
NEW_SQUADRA = "__new__"


def _back_to_gara(gara_id: int) -> str:
    """Dove tornare: la pagina da cui si e' partiti, altrimenti la gara.

    I fogli di squadre e categorie stanno sia nella pagina della gara sia in
    «Impostazioni gara»: chi invia un form da li' manda `next` (con l'ancora
    che riapre il foglio). Solo percorsi interni (`safe_next_url`).
    """
    return safe_next_url(request.form.get("next")) or url_for(
        "admin.competition.gara_detail", gara_id=gara_id
    )


@competition_bp.route("/<int:gara_id>/squadre/create", methods=["POST"])
@login_required
@gara_manager_required
def create_squadra(gara_id):
    """Aggiunge una voce all'elenco della competizione (US-3)."""
    gara = db.get_or_404(Gara, gara_id)

    return handle_service_action(
        action=lambda: SquadraService.create(
            gara, request.form.get("name", ""), current_user
        ),
        redirect_url=_back_to_gara(gara_id),
        success_message=_("Squadra aggiunta all'elenco"),
        error_prefix=None,
    )


@competition_bp.route(
    "/<int:gara_id>/squadre/<int:squadra_id>/rename", methods=["POST"]
)
@login_required
@gara_manager_required
def rename_squadra(gara_id, squadra_id):
    gara = db.get_or_404(Gara, gara_id)

    return handle_service_action(
        action=lambda: SquadraService.rename(
            gara, squadra_id, request.form.get("name", ""), current_user
        ),
        redirect_url=_back_to_gara(gara_id),
        success_message=_("Squadra rinominata"),
        error_prefix=None,
    )


@competition_bp.route("/<int:gara_id>/squadre/<int:squadra_id>/merge", methods=["POST"])
@login_required
@gara_manager_required
def merge_squadra(gara_id, squadra_id):
    """Unisce due doppioni: le iscrizioni passano alla voce che resta (US-3)."""
    gara = db.get_or_404(Gara, gara_id)
    target_raw = request.form.get("target_id", "")

    def action():
        if not target_raw.isdigit():
            raise ValueError(_("Scegli la squadra in cui unire questa voce"))
        SquadraService.merge(gara, squadra_id, int(target_raw), current_user)

    return handle_service_action(
        action=action,
        redirect_url=_back_to_gara(gara_id),
        success_message=_("Squadre unite: le iscrizioni sono state riassegnate"),
        error_prefix=None,
    )


@competition_bp.route(
    "/<int:gara_id>/squadre/<int:squadra_id>/toggle", methods=["POST"]
)
@login_required
@gara_manager_required
def toggle_squadra(gara_id, squadra_id):
    """Toglie (o rimette) una voce fra quelle scegliibili."""
    gara = db.get_or_404(Gara, gara_id)
    attiva = request.form.get("active") == "on"

    return handle_service_action(
        action=lambda: SquadraService.set_active(
            gara, squadra_id, attiva, current_user
        ),
        redirect_url=_back_to_gara(gara_id),
        success_message=(
            _("Squadra riattivata") if attiva else _("Squadra disattivata")
        ),
        error_prefix=None,
    )


@competition_bp.route(
    "/<int:gara_id>/inscription/<int:inscription_id>/squadra", methods=["POST"]
)
@login_required
def set_inscription_squadra(gara_id, inscription_id):
    """La squadra con cui un iscritto gioca **questa** gara (US-8, US-9).

    Nessun ``gara_manager_required``: qui scrivono sia il giocatore titolare
    dell'iscrizione sia chi dirige la gara, e la distinzione la fa il
    servizio, che e' anche il posto in cui vale per tutte le strade.
    """
    gara = db.get_or_404(Gara, gara_id)
    inscription = db.get_or_404(Inscription, inscription_id)
    if inscription.gara_id != gara.id:
        flash(_("Iscrizione non trovata in questa gara"), "error")
        return redirect(_back_to_gara(gara_id))

    scelta = (request.form.get("squadra_id") or "").strip()
    nuovo_nome = (request.form.get("new_name") or "").strip()
    conferma_nuova = request.form.get("confirm_new") == "on"

    try:
        squadra_id = None

        if scelta == NEW_SQUADRA or (not scelta and nuovo_nome):
            if not nuovo_nome:
                raise ValueError(_("Scrivi il nome della squadra da aggiungere"))

            # Se il nome esiste gia' si sceglie quella voce: creare un
            # doppione esatto sarebbe un errore, non una scelta.
            esistente = SquadraService.find_by_name(gara, nuovo_nome)
            if esistente:
                squadra_id = esistente.id
            else:
                simili = SquadraService.similar_names(gara, nuovo_nome)
                if simili and not conferma_nuova:
                    # US-2: i nomi simili si mostrano *prima* di creare. Non e'
                    # un errore — e' l'unica occasione per accorgersi che il
                    # circolo e' gia' in elenco scritto in un altro modo.
                    flash(
                        _(
                            "In elenco ci sono già nomi simili: %(nomi)s. "
                            "Scegli la voce giusta, oppure conferma di volerne "
                            "creare una nuova.",
                            nomi=", ".join(s.name for s in simili),
                        ),
                        "warning",
                    )
                    return redirect(_back_to_gara(gara_id))
                squadra_id = SquadraService.create(gara, nuovo_nome).id

        elif scelta.isdigit():
            squadra_id = int(scelta)

        SquadraService.set_inscription_squadra(
            gara, inscription, squadra_id, current_user
        )
        if squadra_id:
            messaggio = _("Squadra aggiornata")
        elif current_user.id == inscription.user_id:
            messaggio = _("Giocherai senza squadra in questa gara")
        else:
            # Chi dirige non gioca: la frase parla del giocatore, non a lui.
            messaggio = _(
                "%(username)s gioca senza squadra in questa gara",
                username=inscription.user.username,
            )
        flash(messaggio, "success")
    except DomainError as errore:
        flash(str(errore), "error")
    except ValueError as errore:
        flash(str(errore), "error")

    return redirect(_back_to_gara(gara_id))
