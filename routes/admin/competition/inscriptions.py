# routes/admin/competition/inscriptions.py
"""Inscription management routes for competitions."""

from flask import (
    request,
    redirect,
    url_for,
    flash,
)
from flask_babel import _
from flask_login import login_required, current_user

from models import (
    db,
    Gara,
)
from models.status_enum import GaraStatus
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.state_service import StateService
from utils import gara_manager_required
from utils.local_time import format_local_input, parse_local_datetime
from utils.route_helpers import handle_service_action

from . import competition_bp


def _inscription_window():
    """Legge la finestra di iscrizione dal form, in ora italiana.

    I due campi sono ``<input type="datetime-local">``: il browser li manda in
    **ora locale**, il DB tiene i naive come **UTC** e ``|datetime_local`` in
    lettura risomma il fuso. Passare il valore grezzo al service significa
    aprire le iscrizioni due ore dopo l'ora scritta — senza un errore da
    nessuna parte.

    Le etichette dicono «ora italiana» ed è quello che il parser assume: il
    fuso è fissato in ``utils/local_time``, unico posto che lo sa insieme al
    filtro di lettura.
    """
    start = parse_local_datetime(request.form.get("inscription_start"))
    end = parse_local_datetime(request.form.get("inscription_end"))
    if not start or not end:
        raise ValueError("Date di inizio o fine iscrizioni mancanti o non valide")
    return start, end


def _intero(valore, vuoto=None):
    """Un intero dal form; `None` se il campo manca, `vuoto` se e' vuoto.

    I due numeri del foglio leggono il vuoto in modo diverso: un massimo
    vuoto vuol dire «senza limite» (0 per il servizio), un minimo vuoto vuol
    dire «lascia quello che c'e'» (`None`). Rilievo della revisione
    automatica sulla PR #345.
    """
    if valore is None:
        return None
    valore = valore.strip()
    if valore == "":
        return vuoto
    try:
        return int(valore)
    except ValueError as errore:
        raise ValueError("Minimo e massimo devono essere numeri interi") from errore


@competition_bp.route("/<int:gara_id>/open_inscriptions", methods=["POST"])
@login_required
@gara_manager_required
def open_inscriptions(gara_id):
    """Apri iscrizioni per una gara"""

    def action():
        inscription_start, inscription_end = _inscription_window()
        gara = InscriptionService.open_inscriptions(
            gara_id,
            inscription_start,
            inscription_end,
            min_participants=_intero(request.form.get("min_participants")),
            max_participants=_intero(request.form.get("max_participants"), vuoto=0),
        )

        # Il service accorcia la finestra all'inizio della gara. È un
        # aggiustamento ragionevole ma non richiesto, quindi va detto — *dopo*
        # averlo fatto, con le iscrizioni ormai aperte. Annunciarlo sollevando
        # significava perderlo nel rollback e lasciare la gara chiusa.
        if gara.inscription_end and gara.inscription_end < inscription_end:
            flash(
                _(
                    "Le iscrizioni non possono restare aperte oltre l'inizio "
                    "della gara: la chiusura è stata anticipata al %(quando)s.",
                    quando=format_local_input(gara.inscription_end).replace("T", " "),
                ),
                "warning",
            )

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
        success_message="Iscrizioni aperte!",
    )


@competition_bp.route("/<int:gara_id>/modify_inscription_dates", methods=["POST"])
@login_required
@gara_manager_required
def modify_inscription_dates(gara_id):
    """Modifica date di iscrizione per una gara"""

    def action():
        inscription_start, inscription_end = _inscription_window()
        InscriptionService.modify_inscription_dates(
            gara_id, inscription_start, inscription_end
        )

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
        success_message="Date di iscrizione aggiornate con successo!",
        error_prefix=None,
    )


@competition_bp.route("/<int:gara_id>/close_inscriptions", methods=["POST"])
@login_required
@gara_manager_required
def close_inscriptions(gara_id):
    """Chiude le iscrizioni e torna la gara allo stato setup se non ci sono iscritti"""

    def action():
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError("Gara non trovata.")

        if gara.status != GaraStatus.INSCRIPTION.value:
            raise ValueError("La gara non è in stato di iscrizione.")

        active_count = gara.get_active_inscriptions_count()
        if active_count > 0:
            raise ValueError(
                "Non è possibile chiudere le iscrizioni quando ci sono già "
                "degli iscritti."
            )

        StateService.reopen_setup(gara)

    return handle_service_action(
        action=action,
        redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
        success_message=(
            "Iscrizioni chiuse con successo! La gara è tornata allo stato di setup."
        ),
    )


@competition_bp.route("/<int:gara_id>/admin_inscribe", methods=["POST"])
@login_required
@gara_manager_required
def admin_inscribe_user(gara_id):
    """Iscrive un utente alla gara (solo admin/direttori)."""
    from models.competition.inscription_service import InscriptionService
    from models.notification.factory import NotificationFactory
    from models.user.models import User
    from models.competition.models import Gara

    try:
        # Verifica che la gara esista
        gara = db.session.get(Gara, gara_id)
        if not gara:
            flash("Gara non trovata.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Verifica che la gara sia ancora in fase di iscrizioni
        if gara.status != GaraStatus.INSCRIPTION.value:
            flash(
                (
                    "Non è possibile iscrivere utenti quando la gara non è in fase di "
                    "iscrizione."
                ),
                "error",
            )
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Valida user_id dal form
        user_id_str = request.form.get("user_id")
        if not user_id_str:
            flash("Nessun utente selezionato.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        user_id = int(user_id_str)

        # Verifica che l'utente esista
        user = db.session.get(User, user_id)
        if not user:
            flash("Utente non trovato.", "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # In una prova si iscrivono solo i fittizi (ADR-058): un utente vero
        # riceverebbe notifiche e comparirebbe in una gara che nessuno vede.
        if gara.is_prova and not user.is_fittizio:
            flash(
                _(
                    "In una competizione di prova si iscrivono solo "
                    "i giocatori fittizi."
                ),
                "error",
            )
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))
        if user.is_fittizio and not gara.is_prova:
            flash(
                _("Un giocatore fittizio gioca solo nella sua prova."),
                "error",
            )
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Esegui l'iscrizione usando il service layer
        inscription = InscriptionService.inscribe_user(user_id, gara_id)

        if inscription:
            # Formatta la data per la notifica
            gara_date_str = (
                gara.date.strftime("%d/%m/%Y") if gara.date else "data da definire"
            )
            gara_name = gara.name or f"Gara {gara.number}"

            # Crea notifica per l'utente iscritto
            NotificationFactory.create_gara_inscription_notification(
                user_id=user_id,
                gara_id=gara_id,
                gara_name=gara_name,
                gara_date=gara_date_str,
                enrolled_by=current_user.username,
            )

            if inscription.is_waitlist:
                flash(
                    (
                        f"Utente {user.username} aggiunto alla lista d'attesa "
                        f"(posizione {inscription.waitlist_position})."
                    ),
                    "warning",
                )
            else:
                flash(f"Utente {user.username} iscritto con successo.", "success")
        else:
            flash(f"Utente {user.username} già iscritto a questa gara.", "warning")

    except ValueError as ve:
        flash(f"Errore: {str(ve)}", "error")
    except Exception as e:
        flash(f"Errore durante l'iscrizione: {str(e)}", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/admin_uninscribe/<int:user_id>", methods=["POST"])
@login_required
@gara_manager_required
def admin_uninscribe_user(gara_id, user_id):
    """Disiscrive un utente dalla gara (solo admin/direttori)."""
    from models.competition.inscription_service import InscriptionService
    from models.user.models import User
    from models.competition.models import Gara

    try:
        # Verifica che l'utente esista
        user = db.session.get(User, user_id)
        if not user:
            flash(_("Utente non trovato."), "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Verifica che la gara esista
        gara = db.session.get(Gara, gara_id)
        if not gara:
            flash(_("Gara non trovata."), "error")
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Verifica che la gara sia ancora in fase di iscrizioni. A gara in
        # corso chi se ne va si ritira: e' `ritira_iscritto`, qui sotto.
        if gara.status != GaraStatus.INSCRIPTION.value:
            flash(
                _(
                    "Non è possibile disiscrivere utenti quando il primo turno "
                    "è già iniziato."
                ),
                "error",
            )
            return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))

        # Esegui la disiscrizione
        success = InscriptionService.admin_uninscribe_user(
            user_id, gara_id, current_user.id
        )

        if success:
            flash(
                _("%(username)s non è più iscritto.", username=user.username),
                "success",
            )
        else:
            flash(_("Errore: utente non iscritto a questa gara."), "error")

    except Exception as e:
        flash(_("Errore durante la disiscrizione: %(errore)s", errore=str(e)), "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/ritira/<int:user_id>", methods=["POST"])
@login_required
@gara_manager_required
def ritira_iscritto(gara_id, user_id):
    """Il direttore ritira un iscritto a gara in corso.

    Per il giocatore che se ne va senza dirlo all'app: la cancellazione a gara
    in corso *e'* il suo forfait, con la regola della gara sui ritiri, e il
    giocatore riceve una notifica (`WithdrawPolicyService.ritira_iscritto`).
    Prima dell'avvio la strada resta `admin_uninscribe_user`.
    """
    from models.competition.withdraw_policy_service import WithdrawPolicyService
    from models.user.models import User
    from routes.sse import emit_gara_event

    destinazione = url_for("admin.competition.gara_detail", gara_id=gara_id)
    try:
        WithdrawPolicyService.ritira_iscritto(gara_id, user_id, current_user.id)
    except ValueError as errore:
        flash(str(errore), "danger")
        return redirect(destinazione)

    # Le pagine aperte sulla gara si rifanno: partite chiuse, iscritto barrato.
    emit_gara_event(
        gara_id,
        "match_completed",
        {"forfeit": True, "user_id": user_id, "autore": current_user.id},
    )
    user = db.session.get(User, user_id)
    flash(
        _(
            "Ritiro di %(username)s registrato: gli è arrivata una notifica.",
            username=user.username if user else user_id,
        ),
        "success",
    )
    return redirect(destinazione)


# ────────────────────────────────────────────────────────────────────────────────
# DIRECTOR MANAGEMENT
# ────────────────────────────────────────────────────────────────────────────────


@competition_bp.route("/<int:gara_id>/add_director", methods=["POST"])
@login_required
@gara_manager_required
def add_director(gara_id):
    """Aggiunge un co‑direttore alla gara"""
    new_director_id = int(request.form["user_id"])

    try:
        success = GaraService.add_director(
            gara_id=gara_id,
            user_id=new_director_id,
            assigned_by_id=current_user.id,
        )

        if success:
            flash("Direttore aggiunto con successo.")
        else:
            flash("Utente già presente come direttore.", "warning")

    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"Errore durante l'aggiunta del direttore: {str(e)}", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))


@competition_bp.route("/<int:gara_id>/remove_director", methods=["POST"])
@login_required
@gara_manager_required
def remove_director(gara_id):
    """Rimuove un co‑direttore dalla gara"""
    director_id = int(request.form["user_id"])

    success = GaraService.remove_director(gara_id=gara_id, user_id=director_id)

    if success:
        flash("Direttore rimosso con successo.")
    else:
        flash("Errore: direttore non trovato.", "error")

    return redirect(url_for("admin.competition.gara_detail", gara_id=gara_id))
