# routes/player.py - AGGIORNATO dashboard per multi-torneo
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
)
from flask_login import login_required, current_user, logout_user
from datetime import datetime

from models import (
    db,
    Prova,
    Inscription,
    Match,
    Rack,
    User,
)
from models.status_enum import (
    MatchStatus,
    ProvaStatus,
    DirectorRequestStatus,
)
from models.tournament.models import Tournament
from models.classification.models import Classification
from models.user.models import DirectorRequest
from models.notification.services import NotificationService
from models.notification.models import NotificationType, NotificationPriority
from models.user.services import UserDeletionService, UserService
from utils import (
    player_only,
    player_required,
    match_player_required,
    rack_player_required,
)
from models.match.services import MatchService, RackService

player_bp = Blueprint("player", __name__)


# Individual Match Proposal Routes
@player_bp.route("/match-proposals")
@login_required
@player_only
def match_proposals():
    """View and manage individual match proposals"""
    from models.individual_match.services import IndividualMatchService

    proposals = IndividualMatchService.get_user_proposals(current_user.id)
    return render_template("player/match_proposals.html", proposals=proposals)


@player_bp.route("/match-proposals/create", methods=["GET", "POST"])
@login_required
@player_only
def create_match_proposal():
    """Create a new match proposal"""
    if request.method == "POST":
        from models.individual_match.services import IndividualMatchService
        from datetime import datetime

        try:
            proposal_type = request.form.get("proposal_type")
            location = request.form.get("location")
            if not location:
                flash("Location is required", "error")
                raise ValueError("Location is required")
            scheduled_str = request.form.get("scheduled_at")
            if not scheduled_str:
                flash("Scheduled time is required", "error")
                raise ValueError("Scheduled time is required")
            scheduled_at = datetime.fromisoformat(scheduled_str.replace("Z", "+00:00"))
            discipline = request.form.get("discipline", "palla_8")
            distance = int(request.form.get("distance", 5))
            best_of = "best_of" in request.form
            break_rule = request.form.get("break_rule", "alternate")
            description = request.form.get("description")
            entry_fee = (
                float(request.form.get("entry_fee", 0))
                if request.form.get("entry_fee")
                else None
            )

            if proposal_type == "direct":
                invited_ids = [
                    int(x) for x in request.form.getlist("invited_users") if x
                ]
                proposal = IndividualMatchService.create_direct_proposal(
                    proposer_id=current_user.id,
                    invited_user_ids=invited_ids,
                    location=location,
                    scheduled_at=scheduled_at,
                    discipline=discipline,
                    distance=distance,
                    best_of=best_of,
                    break_rule=break_rule,
                    description=description,
                    entry_fee=entry_fee,
                )
            else:  # open
                proposal = IndividualMatchService.create_open_proposal(
                    proposer_id=current_user.id,
                    location=location,
                    scheduled_at=scheduled_at,
                    discipline=discipline,
                    distance=distance,
                    best_of=best_of,
                    break_rule=break_rule,
                    description=description,
                    entry_fee=entry_fee,
                )

            flash(f"Match proposal created successfully! ID: {proposal.id}")
            return redirect(url_for("player.match_proposals"))

        except Exception as e:
            flash(f"Error creating proposal: {str(e)}", "error")

    # Get available users and locations for the form
    from models.location.models import BilliardHall

    users = User.query.filter(User.id != current_user.id).all()
    locations = BilliardHall.query.all()

    return render_template(
        "player/create_match_proposal.html", users=users, locations=locations
    )


@player_bp.route("/match-proposals/<int:proposal_id>/accept", methods=["POST"])
@login_required
@player_only
def accept_match_proposal(proposal_id):
    """Accept a match proposal"""
    from models.individual_match.services import IndividualMatchService

    try:
        match = IndividualMatchService.accept_proposal(current_user.id, proposal_id)
        flash(f"Match proposal accepted! Match ID: {match.id}")
    except Exception as e:
        flash(f"Error accepting proposal: {str(e)}", "error")

    return redirect(url_for("player.match_proposals"))


@player_bp.route("/match-proposals/<int:proposal_id>/reject", methods=["POST"])
@login_required
@player_only
def reject_match_proposal(proposal_id):
    """Reject a match proposal"""
    from models.individual_match.services import IndividualMatchService

    try:
        IndividualMatchService.reject_invitation(current_user.id, proposal_id)
        flash("Match proposal rejected.")
    except Exception as e:
        flash(f"Error rejecting proposal: {str(e)}", "error")

    return redirect(url_for("player.match_proposals"))


@player_bp.route("/match-proposals/<int:proposal_id>/cancel", methods=["POST"])
@login_required
@player_only
def cancel_match_proposal(proposal_id):
    """Cancel a match proposal"""
    from models.individual_match.services import MatchProposalService

    try:
        MatchProposalService.cancel_proposal(proposal_id, current_user.id)
        flash("Match proposal cancelled.")
    except Exception as e:
        flash(f"Error cancelling proposal: {str(e)}", "error")

    return redirect(url_for("player.match_proposals"))


@player_bp.route("/")
@login_required
def dashboard():
    return redirect(url_for("dashboard.dashboard"))


# Il resto delle route rimane uguale...
@player_bp.route("/prova/<int:prova_id>")
@login_required
@player_required
def prova_detail(prova_id):
    """Dettaglio prova con iscrizioni e partite dell'utente"""
    prova = db.session.get(Prova, prova_id)
    if prova is None:
        abort(404)

    # Verifica che l'utente sia iscritto alla prova
    inscription = Inscription.query.filter_by(
        prova_id=prova_id, user_id=current_user.id
    ).first()

    if not inscription:
        flash("Non sei iscritto a questa prova.", "error")
        return redirect(url_for("dashboard.dashboard"))

    matches = (
        Match.query.filter_by(prova_id=prova_id)
        .filter(
            db.or_(
                Match.player1_id == current_user.id,
                Match.player2_id == current_user.id,
            )
        )
        .order_by(Match.round_number, Match.id)
        .all()
    )

    return render_template(
        "player/prova_detail.html",
        prova=prova,
        inscription=inscription,
        matches=matches,
    )


@player_bp.route("/prova/<int:prova_id>/inscribe", methods=["POST"])
@login_required
@player_only
def inscribe_to_prova(prova_id):
    """Iscriviti a una prova"""
    prova = Prova.query.get_or_404(prova_id)

    # Verifica che le iscrizioni siano aperte
    now = datetime.utcnow()
    if (
        prova.status != ProvaStatus.INSCRIPTION.value
        or now < prova.inscription_start
        or now > prova.inscription_end
    ):
        flash("Le iscrizioni non sono disponibili.")
        return redirect(url_for("main.index"))

    # Verifica che non sia già iscritto
    existing = Inscription.query.filter_by(
        user_id=current_user.id, prova_id=prova_id
    ).first()
    if existing:
        flash("Sei già iscritto a questa prova.")
        return redirect(url_for("player.dashboard"))

    inscription = Inscription(user_id=current_user.id, prova_id=prova_id)
    db.session.add(inscription)
    db.session.commit()

    flash(f"Iscrizione alla Prova {prova.number} completata!")
    # Redirect mantenendo il torneo selezionato
    return redirect(url_for("player.dashboard", tournament_id=prova.tournament_id))


@player_bp.route("/match/<int:match_id>")
@login_required
@match_player_required
def match_detail(match_id):
    """Dettaglio partita per giocatore"""
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)

    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()

    return render_template("player/match_detail.html", match=match, racks=racks)


@player_bp.route("/match/<int:match_id>/report_rack", methods=["POST"])
@login_required
@match_player_required
def report_rack_result(match_id):
    """Segnala risultato rack"""
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)

    winner_id = int(request.form["winner_id"])

    # Verifica che il vincitore sia uno dei giocatori della partita
    if winner_id not in [match.player1_id, match.player2_id]:
        flash("Giocatore non valido.", "error")
        return redirect(url_for("player.match_detail", match_id=match_id))

    # Usa il service layer invece del direct database access
    try:
        result = RackService.add_rack_with_score_update(
            match_id=match_id,
            winner_id=winner_id,
            reported_by_id=current_user.id,
            validated_by_admin=False,  # Player report, needs admin validation
        )
        return jsonify(result)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Errore durante aggiunta rack: {str(e)}"}), 500


# ============ PROFILO UTENTE E GESTIONE ACCOUNT ============


@player_bp.route("/profile")
@login_required
@player_only
def profile():
    """Profilo personale del giocatore"""

    # Iscrizioni dell'utente
    inscriptions = (
        Inscription.query.filter_by(user_id=current_user.id)
        .join(Prova)
        .join(Tournament)
        .order_by(Tournament.created_at.desc(), Prova.number.desc())
        .all()
    )

    # Partite giocate
    matches = (
        Match.query.filter(
            db.or_(
                Match.player1_id == current_user.id, Match.player2_id == current_user.id
            )
        )
        .join(Prova)
        .join(Tournament)
        .order_by(
            Tournament.created_at.desc(), Prova.number.desc(), Match.round_number.desc()
        )
        .all()
    )

    # Statistiche generali
    total_matches = len([m for m in matches if m.status == MatchStatus.COMPLETED.value])
    won_matches = len(
        [
            m
            for m in matches
            if m.status == MatchStatus.COMPLETED.value
            and m.winner_id == current_user.id
        ]
    )
    win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0

    # Classifiche per torneo
    classifications = (
        Classification.query.filter_by(user_id=current_user.id)
        .join(Tournament)
        .order_by(Tournament.created_at.desc())
        .all()
    )

    # Partite recenti (ultime 10)
    recent_matches = [m for m in matches if m.status == MatchStatus.COMPLETED.value][
        :10
    ]

    stats = {
        "total_inscriptions": len(inscriptions),
        "total_matches": total_matches,
        "won_matches": won_matches,
        "lost_matches": total_matches - won_matches,
        "win_percentage": round(win_percentage, 1),
        "tournaments_played": len(
            set([insc.prova.tournament_id for insc in inscriptions])
        ),
    }

    return render_template(
        "player/profile.html",
        user=current_user,
        inscriptions=inscriptions,
        matches=recent_matches,
        classifications=classifications,
        stats=stats,
    )


@player_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
@player_only
def edit_profile():
    """Modifica email e telefono dell'utente corrente."""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        phone = (request.form.get("phone") or "").strip() or None

        try:
            UserService.update_user(current_user.id, email=email, phone=phone)
            flash("Informazioni aggiornate correttamente.", "success")
            return redirect(url_for("player.profile"))
        except ValueError as e:
            flash(str(e), "error")
        except Exception:
            flash("Si è verificato un errore durante l'aggiornamento.", "error")

    # GET o POST fallito → ripresenta il form
    return render_template("player/profile_edit.html", user=current_user)


@player_bp.route("/profile/change_password", methods=["POST"])
@login_required
@player_only
def change_password():
    """Cambia la password dell'utente corrente."""
    current = request.form.get("current_password") or ""
    new = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    if new != confirm:
        flash("La nuova password e la conferma non coincidono.", "error")
        return redirect(url_for("player.profile"))

    ok = UserService.change_password(current_user.id, current, new)
    if ok:
        flash("Password aggiornata correttamente.", "success")
    else:
        flash("Password attuale errata o nuova password non valida.", "error")

    return redirect(url_for("player.profile"))


@player_bp.route("/request_director", methods=["POST"])
@login_required
@player_only
def request_director():
    """Richiede la promozione a direttore di gara"""
    if current_user.role != "player":
        flash("Solo i giocatori possono richiedere di diventare direttori.")
        return redirect(url_for("player.profile"))
    if current_user.director_request:
        flash("Hai già una richiesta in sospeso o è stata valutata.")
        return redirect(url_for("player.profile"))

    req = DirectorRequest(
        user_id=current_user.id, status=DirectorRequestStatus.PENDING.value
    )
    db.session.add(req)
    db.session.commit()

    # Invia notifica all'admin
    admin = User.query.filter_by(role="admin").first()
    if admin:
        NotificationService.create_notification(
            user_id=admin.id,
            notification_type=NotificationType.ACCOUNT_UPDATE,
            title="Nuova richiesta Director",
            message=(
                f"L'utente {current_user.username} ha richiesto di "
                "diventare direttore di gara."
            ),
            priority=NotificationPriority.HIGH,
            action_url=url_for("admin.user.director_requests"),
            action_text="Gestisci richieste",
        )

    flash("Richiesta inviata. Sarai contattato dall'amministratore.")
    return redirect(url_for("player.profile"))


@player_bp.route("/notifications")
@login_required
def notifications():
    """Mostra le notifiche dell'utente"""
    from models.notification.models import Notification, NotificationStatus

    # Get all notifications for current user
    user_notifications = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )

    # Mark PENDING notifications as SENT
    for notif in user_notifications:
        if notif.status == NotificationStatus.PENDING:
            notif.status = NotificationStatus.SENT
            notif.sent_at = datetime.utcnow()

    db.session.commit()

    return render_template(
        "player/notifications.html", notifications=user_notifications
    )


@player_bp.route("/notifications/<int:notification_id>/mark_read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    """Segna una notifica come letta"""
    from models.notification.models import Notification, NotificationStatus

    notification = Notification.query.filter_by(
        id=notification_id, user_id=current_user.id
    ).first_or_404()

    notification.status = NotificationStatus.READ
    notification.read_at = datetime.utcnow()
    db.session.commit()

    # If there's an action URL, redirect to it
    if notification.action_url:
        return redirect(notification.action_url)

    return redirect(url_for("player.notifications"))


@player_bp.route("/notifications/mark_all_read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    """Segna tutte le notifiche come lette"""
    from models.notification.models import Notification, NotificationStatus

    Notification.query.filter_by(user_id=current_user.id).filter(
        Notification.status != NotificationStatus.READ
    ).update({"status": NotificationStatus.READ, "read_at": datetime.utcnow()})

    db.session.commit()
    flash("Tutte le notifiche sono state segnate come lette.")
    return redirect(url_for("player.notifications"))


@player_bp.route("/delete_account", methods=["GET", "POST"])
@login_required
@player_only
def delete_account():
    """Cancellazione account utente (self-service).
    Conserva lo storico tramite soft delete."""
    if request.method == "GET":
        return render_template("player/delete_account.html")

    password = request.form.get("password", "")
    confirmation = request.form.get("confirmation", "").strip()

    # Verifica password
    if not current_user.check_password(password):
        flash("Password errata!", "danger")
        return render_template("player/delete_account.html")

    # Verifica conferma
    if confirmation != "ELIMINA IL MIO ACCOUNT":
        flash("Conferma non corretta!", "warning")
        return render_template("player/delete_account.html")

    try:
        # Ensure current_user is properly typed as User
        user_to_delete = db.session.get(User, current_user.id)
        if not user_to_delete:
            flash("Errore: utente non trovato.", "danger")
            return render_template("player/delete_account.html")

        UserDeletionService.delete_user(user_to_delete)
        logout_user()  # Disconnette l'utente dopo la cancellazione
        flash(
            "Account eliminato. I tuoi dati restano anonimizzati nei registri.",
            "success",
        )
        return redirect(url_for("main.index"))
    except Exception:
        db.session.rollback()
        flash("Errore durante l'eliminazione dell'account.", "danger")
        raise


# ============ DISISCRIZIONE TORNEI ============


@player_bp.route("/prova/<int:prova_id>/unsubscribe", methods=["POST"])
@login_required
@player_only
def unsubscribe_from_prova(prova_id):
    """Disiscrizione da una prova"""
    prova = Prova.query.get_or_404(prova_id)

    # Verifica che l'utente sia iscritto
    inscription = Inscription.query.filter_by(
        user_id=current_user.id, prova_id=prova_id
    ).first()
    if not inscription:
        flash("Non sei iscritto a questa prova.")
        return redirect(url_for("player.dashboard"))

    # Verifica che la prova non sia ancora iniziata
    if prova.status not in [ProvaStatus.SETUP.value, ProvaStatus.INSCRIPTION.value]:
        flash("Impossibile disiscreversi: la prova è già iniziata!")
        return redirect(url_for("player.dashboard"))

    # Verifica che non ci siano partite già create
    existing_matches = Match.query.filter(
        db.or_(
            Match.player1_id == current_user.id, Match.player2_id == current_user.id
        ),
        Match.prova_id == prova_id,
    ).first()

    if existing_matches:
        flash("Impossibile disiscreversi: ci sono già partite programmate!")
        return redirect(url_for("player.dashboard"))

    # Procedi con la disiscrizione
    db.session.delete(inscription)
    db.session.commit()

    flash(f"Disiscrizione dalla Prova {prova.number} completata!")
    # Redirect mantenendo il torneo selezionato
    return redirect(url_for("player.dashboard", tournament_id=prova.tournament_id))


# ============ SISTEMA CONFERMA/RIMOZIONE PUNTI ============


@player_bp.route("/rack/<int:rack_id>/remove", methods=["POST"])
@login_required
def remove_rack(rack_id):
    """Rimuovi un rack inserito per errore"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match

    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({"error": "Non autorizzato"}), 403

    # Verifica che possa essere rimosso
    if not rack.can_be_removed(current_user.id):
        return jsonify({"error": "Impossibile rimuovere questo rack"}), 400

    # Salva il vincitore per aggiornare il punteggio
    winner_id = rack.winner_id

    # Rimuovi il rack
    db.session.delete(rack)

    # Aggiorna il punteggio del match
    if winner_id == match.player1_id:
        match.player1_score = max(0, match.player1_score - 1)
    else:
        match.player2_score = max(0, match.player2_score - 1)

    # Se il match era completato, rimettilo in playing
    if match.status == MatchStatus.COMPLETED.value:
        MatchService.to_playing(match.id)
        match.winner_id = None

    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": "Rack rimosso",
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }
    )


@player_bp.route("/rack/<int:rack_id>/confirm", methods=["POST"])
@login_required
def confirm_rack(rack_id):
    """Conferma un rack inserito dall'altro giocatore"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match

    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({"error": "Non autorizzato"}), 403

    # Verifica che possa essere confermato
    if not rack.can_be_confirmed(current_user.id):
        return jsonify({"error": "Impossibile confermare questo rack"}), 400

    # Conferma il rack
    rack.confirmed_by_player = True
    db.session.commit()

    return jsonify({"success": True, "message": "Rack confermato"})


@player_bp.route("/rack/<int:rack_id>/unconfirm", methods=["POST"])
@login_required
def unconfirm_rack(rack_id):
    """Rimuovi conferma da un rack"""
    rack = Rack.query.get_or_404(rack_id)
    match = rack.match

    # Verifica autorizzazioni
    if current_user.id not in [match.player1_id, match.player2_id]:
        return jsonify({"error": "Non autorizzato"}), 403

    # Verifica che possa rimuovere la conferma
    if not rack.can_remove_confirmation(current_user.id):
        return jsonify({"error": "Impossibile rimuovere la conferma"}), 400

    # Rimuovi la conferma
    rack.confirmed_by_player = False
    db.session.commit()

    return jsonify({"success": True, "message": "Conferma rimossa"})


@player_bp.route("/rack/<int:rack_id>")
@login_required
@rack_player_required
def rack_detail(rack_id):
    """Dettaglio rack"""
    rack = db.session.get(Rack, rack_id)
    if rack is None:
        abort(404)

    return render_template("player/rack_detail.html", rack=rack)
