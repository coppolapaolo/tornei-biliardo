"""
Module: routes/istruttore.py
Purpose: «I miei allievi» e i gruppi dell'istruttore (ADR-069, D12, issue #173).
Requirements: fase 8c del redesign «TPA ed esercizi».

Un blueprint suo, e non una stanza delle schede, perché queste pagine sono
dell'**altro lato**: chi le apre non si allena, guarda allenarsi. «Chi legge le
mie schede» sta sotto `/schede` perché è una cosa che si fa alle proprie
schede; «I miei allievi» non ha una scheda a cui appartenere.

Tutte le route di qui dentro pretendono il ruolo, e rispondono **404** a chi
non ce l'ha: una pagina che dice «non sei un istruttore» racconta a chi passa
di lì che esiste un mestiere che non ha, e non serve a niente.
"""

from datetime import date
from typing import Optional

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required

from models.exceptions import DomainError
from models.istruttore import GruppoService, build_allievi
from utils.route_helpers import handle_service_action

istruttore_bp = Blueprint("istruttore", __name__, url_prefix="/istruttore")


def _solo_istruttori() -> None:
    if not getattr(current_user, "is_instructor", False):
        abort(404)


def _mio_gruppo(group_id: int):
    """Il gruppo, se è di chi sta guardando. Altrimenti non esiste."""
    try:
        gruppo = GruppoService.get_gruppo(group_id)
    except DomainError:
        abort(404)
    if gruppo.instructor_id != current_user.id:
        abort(404)
    return gruppo


def _data(campo: str) -> Optional[date]:
    """Una data da un `<input type="date">`: nessun fuso, solo un giorno.

    Al contrario di un `datetime-local`, qui non c'è niente da convertire — è
    il giorno che comincia il corso, non un istante.
    """
    grezzo = (request.form.get(campo) or "").strip()
    if not grezzo:
        return None
    try:
        return date.fromisoformat(grezzo)
    except ValueError:
        return None


# ── I miei allievi ──────────────────────────────────────────────────────────


@istruttore_bp.route("/allievi", methods=["GET"])
@login_required
def allievi():
    """Chi ti ha aperto una scheda, diviso in tre, filtrabile per gruppo."""
    _solo_istruttori()
    gruppo = None
    chiesto = request.args.get("gruppo", type=int)
    if chiesto:
        gruppo = _mio_gruppo(chiesto)

    return render_template(
        "istruttore/allievi.html",
        pagina=build_allievi(current_user, gruppo),
        gruppo=gruppo,
    )


@istruttore_bp.route("/allievi/<int:user_id>/gruppo", methods=["POST"])
@login_required
def assegna_gruppo(user_id):
    """Mette l'allievo in un gruppo, lo sposta, o lo toglie.

    Un gesto solo per tre cose, perché nel dominio sono la stessa: in due
    gruppi non ci sta, quindi «sposta» è «aggiungi» e basta. Il campo vuoto
    vuol dire «fuori da tutti».
    """
    _solo_istruttori()
    group_id = request.form.get("group_id", type=int)

    # Si torna da dove si è partiti, e «dove» è un numero di gruppo, non un
    # indirizzo: un URL preso dal modulo sarebbe un open redirect, e qui non
    # serve — i posti da cui si può premere sono due.
    torna = request.form.get("torna", type=int)
    dove = (
        url_for("istruttore.gruppo", group_id=torna)
        if torna
        else url_for("istruttore.allievi")
    )

    if not group_id:
        corrente = GruppoService.iscrizioni_correnti(current_user.id).get(user_id)
        if corrente is None:
            return redirect(dove)
        return handle_service_action(
            lambda: GruppoService.togli(corrente.group_id, current_user, user_id),
            success_message=_("Non fa più parte del gruppo."),
            redirect_url=dove,
        )

    return handle_service_action(
        lambda: GruppoService.aggiungi(group_id, current_user, user_id),
        success_message=_("Adesso è nel gruppo."),
        redirect_url=dove,
    )


# ── I gruppi ────────────────────────────────────────────────────────────────


@istruttore_bp.route("/gruppi", methods=["GET"])
@login_required
def gruppi():
    """I corsi in corso, quelli passati, e come farne uno nuovo."""
    _solo_istruttori()
    return render_template(
        "istruttore/gruppi.html",
        aperti=GruppoService.gruppi_di(current_user.id, aperti=True),
        passati=GruppoService.gruppi_di(current_user.id, aperti=False),
    )


@istruttore_bp.route("/gruppi/nuovo", methods=["POST"])
@login_required
def crea_gruppo():
    """Un gruppo nuovo, vuoto: gli allievi si mettono dentro dopo."""
    _solo_istruttori()
    nome = request.form.get("name") or ""
    dal, al = _data("started_on"), _data("ended_on")

    try:
        corso = GruppoService.crea(current_user, nome, dal, al)
    except DomainError as errore:
        # Non `handle_service_action`: qui la destinazione dipende dall'esito
        # — fatto il gruppo, si va dentro a riempirlo.
        flash(str(errore), "error")
        return redirect(url_for("istruttore.gruppi"))
    return redirect(url_for("istruttore.gruppo", group_id=corso.id))


@istruttore_bp.route("/gruppi/<int:group_id>", methods=["GET"])
@login_required
def gruppo(group_id):
    """Un corso: a che punto è, chi ne fa parte, chi ne è uscito."""
    _solo_istruttori()
    corso = _mio_gruppo(group_id)

    # Una lettura sola per le due liste: chi è dentro e chi è ancora libero.
    # Chiamare `build_allievi` due volte rifarebbe la query delle sedute, che
    # è la cosa più cara di questa pagina.
    tutti = build_allievi(current_user)

    return render_template(
        "istruttore/gruppo.html",
        gruppo=corso,
        dentro=[r for r in tutti.righe if r.gruppo and r.gruppo.id == corso.id],
        fuori=[r for r in tutti.righe if r.iscrizione is None],
        passati=GruppoService.membri_passati(corso),
    )


@istruttore_bp.route("/gruppi/<int:group_id>/modifica", methods=["POST"])
@login_required
def modifica_gruppo(group_id):
    """Nome e periodo. Rimettere la data di fine a vuoto riapre il corso."""
    _solo_istruttori()
    _mio_gruppo(group_id)
    nome = request.form.get("name") or ""
    dal, al = _data("started_on"), _data("ended_on")

    return handle_service_action(
        lambda: GruppoService.aggiorna(
            group_id, current_user, nome=nome, dal=dal, al=al
        ),
        success_message=_("Gruppo aggiornato."),
        redirect_url=url_for("istruttore.gruppo", group_id=group_id),
    )


@istruttore_bp.route("/gruppi/<int:group_id>/chiudi", methods=["POST"])
@login_required
def chiudi_gruppo(group_id):
    """Chiude il corso oggi. Chi c'era resta scritto, con la data d'uscita."""
    _solo_istruttori()
    _mio_gruppo(group_id)

    return handle_service_action(
        lambda: GruppoService.chiudi(group_id, current_user),
        success_message=_("Corso chiuso. Resta nello storico."),
        redirect_url=url_for("istruttore.gruppo", group_id=group_id),
    )


__all__ = ["istruttore_bp"]
