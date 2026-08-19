# routes/admin/competition/categorie.py
"""Elenco categorie della competizione e categoria degli iscritti (ADR-049).

Le regole — finestra di modifica, permessi, doppioni — stanno tutte in
``CategoriaService``: qui c'è solo la traduzione fra richiesta e servizio.

Due forme diverse, per due gesti diversi:

- **assegnare** è JSON, perché il combo salva sul posto mentre si scende
  l'elenco degli iscritti. Con una gara da 32 persone il salvataggio a form
  significherebbe 32 ricariche che riportano ogni volta in cima alla pagina;
- **gestire l'elenco** (rinomina, disattiva, elimina) resta form + redirect:
  sono gesti rari e di riparazione, e il messaggio di errore conta più della
  fluidità.

Il combo manda un **nome**, non un id: è ciò che rende «definire l'elenco» e
«assegnare» un gesto solo. Chi organizza scrive «B» sul primo iscritto e la
categoria nasce lì; sul secondo la trova già in tendina.
"""

from flask import jsonify, request, url_for
from flask_babel import _
from flask_login import current_user, login_required

from models import db, Gara, Inscription
from models.categoria.service import CategoriaService
from models.exceptions import DomainError, http_status_for_exception
from utils import gara_manager_required
from utils.route_helpers import get_or_ajax_404, handle_service_action

from . import competition_bp


def _back_to_gara(gara_id: int) -> str:
    return url_for("admin.competition.gara_detail", gara_id=gara_id)


# ── Assegnazione: JSON, salvataggio sul posto ────────────────────────────


@competition_bp.route(
    "/<int:gara_id>/inscription/<int:inscription_id>/categoria", methods=["POST"]
)
@login_required
@gara_manager_required
def set_inscription_categoria(gara_id: int, inscription_id: int):
    """Assegna la categoria di un iscritto dal nome, creandola se manca.

    Body JSON: ``{"name": "B"}``. Nome vuoto = togli la categoria.

    Risponde 409 quando il primo turno è già partito: da lì in poi le
    categorie hanno già deciso quali partite contano per l'Elo, e cambiarle
    darebbe un rating che non corrisponde più a ciò che si vede.
    """
    gara = get_or_ajax_404(Gara, gara_id, "Gara")
    inscription = get_or_ajax_404(Inscription, inscription_id, "Iscrizione")

    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "")

    try:
        categoria = CategoriaService.set_inscription_categoria_by_name(
            gara, inscription, name, actor=current_user
        )
    except DomainError as exc:
        return (
            jsonify({"success": False, "error": str(exc)}),
            http_status_for_exception(exc),
        )

    return jsonify(
        {
            "success": True,
            "categoria": (
                {"id": categoria.id, "name": categoria.name} if categoria else None
            ),
            # L'elenco aggiornato: il combo appena usato può aver creato una
            # voce nuova, e le altre righe devono trovarla in tendina senza
            # che la pagina venga ricaricata.
            "elenco": [c.name for c in CategoriaService.list_for_gara(gara)],
            "senza_categoria": CategoriaService.count_senza_categoria(gara.id),
        }
    )


# ── Gestione dell'elenco: form + redirect ────────────────────────────────


@competition_bp.route(
    "/<int:gara_id>/categorie/<int:categoria_id>/rename", methods=["POST"]
)
@login_required
@gara_manager_required
def rename_categoria(gara_id: int, categoria_id: int):
    gara = db.get_or_404(Gara, gara_id)

    return handle_service_action(
        action=lambda: CategoriaService.rename(
            gara, categoria_id, request.form.get("name", ""), current_user
        ),
        redirect_url=_back_to_gara(gara_id),
        success_message=_("Categoria rinominata"),
        error_prefix=None,
    )


@competition_bp.route(
    "/<int:gara_id>/categorie/<int:categoria_id>/toggle", methods=["POST"]
)
@login_required
@gara_manager_required
def toggle_categoria(gara_id: int, categoria_id: int):
    """Toglie (o rimette) una categoria dalle scelte, senza toccare lo storico."""
    gara = db.get_or_404(Gara, gara_id)
    attiva = request.form.get("active") == "1"

    return handle_service_action(
        action=lambda: CategoriaService.set_active(
            gara, categoria_id, attiva, current_user
        ),
        redirect_url=_back_to_gara(gara_id),
        success_message=(
            _("Categoria riattivata") if attiva else _("Categoria disattivata")
        ),
        error_prefix=None,
    )


@competition_bp.route(
    "/<int:gara_id>/categorie/<int:categoria_id>/delete", methods=["POST"]
)
@login_required
@gara_manager_required
def delete_categoria(gara_id: int, categoria_id: int):
    """Cancella una voce inutilizzata: è il rimedio al refuso appena creato."""
    gara = db.get_or_404(Gara, gara_id)

    return handle_service_action(
        action=lambda: CategoriaService.elimina(gara, categoria_id, current_user),
        redirect_url=_back_to_gara(gara_id),
        success_message=_("Categoria eliminata"),
        error_prefix=None,
    )
