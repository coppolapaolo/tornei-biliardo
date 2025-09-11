# routes/player.py - AGGIORNATO dashboard per multi-campionato
from flask.blueprints import Blueprint
from flask.templating import render_template        # funzione reale
from flask.globals import request                   # LocalProxy -> request
from flask.helpers import redirect, url_for, flash  # helper ufficiali Flask
from flask.json import jsonify                      # funzione ufficiale Flask
from werkzeug.exceptions import abort               # più specifico e stabile
from flask_login import login_required, current_user, logout_user

from datetime import datetime

from models import (
    db,
    Gara,
    Inscription,
    Match,
    Rack,
    User,
)
from models.status_enum import (
    MatchStatus,
    GaraStatus,
    DirectorRequestStatus,
)
from models.campionato.models import Campionato
from models.classification.models import Classification
from models.user.models import DirectorRequest
from models.notification.services import NotificationService
from models.notification.models import NotificationType, NotificationPriority
from models.user.services import UserDeletionService, UserService, VenueManagerRequestService, VenueManagementService
from models.user.models import VenueManagerRequest
from utils import (
    player_only,
    player_required,
    match_player_required,
    rack_player_required,
)
from models.match.services import MatchService, RackService
from models.location.models import BilliardHall
from models.location.services import LocationService

player_bp = Blueprint("player", __name__)


def _handle_venue_creation_player(location: str) -> str:
    """
    Handle venue creation/validation for match proposals.
    If location doesn't match verified venues, create as non-verified.
    Returns the location string to use.
    """
    if not location or not location.strip():
        return location
    
    location = location.strip()
    
    # Check if location matches existing verified venue
    existing_venue = BilliardHall.query.filter_by(
        name=location, 
        is_active=True, 
        verified=True
    ).first()
    
    if existing_venue:
        return location
    
    # Check if location matches existing non-verified venue
    existing_unverified = BilliardHall.query.filter_by(
        name=location, 
        is_active=True
    ).first()
    
    if existing_unverified:
        return location
    
    # Create new non-verified venue
    try:
        new_venue = LocationService.create_billiard_hall(
            name=location,
            added_by_id=current_user.id,
            # Set as non-verified (verified=False is default)
            # Note: number_of_tables is None, so it cannot be verified yet
        )
        flash(f"Nuovo luogo '{location}' aggiunto. Per la verifica serve anche il numero di tavoli.", "info")
    except Exception as e:
        # If creation fails, continue with original location
        flash(f"Errore nella creazione del luogo: {str(e)}", "warning")
    
    return location


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
            
            # Handle venue auto-creation
            location = _handle_venue_creation_player(location)
            scheduled_str = request.form.get("scheduled_at")
            if not scheduled_str:
                flash("Scheduled time is required", "error")
                raise ValueError("Scheduled time is required")
            scheduled_at = datetime.fromisoformat(scheduled_str.replace("Z", "+00:00"))
            discipline = request.form.get("discipline") or None
            distance_str = request.form.get("distance")
            distance = int(distance_str) if distance_str else None
            best_of = "best_of" in request.form
            break_rule = request.form.get("break_rule") or None
            description = request.form.get("description")
            # I match individuali sono sempre gratuiti
            entry_fee = None

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
    from models.user.role_enum import UserRole
    
    # Escludi admin e current user dai giocatori invitabili
    users = User.query.filter(
        User.id != current_user.id,
        User.role != UserRole.ADMIN.value
    ).all()
    
    # Get verified venues instead of recent locations
    from models.location.models import BilliardHall
    verified_venues = BilliardHall.query.filter_by(is_active=True, verified=True).order_by(BilliardHall.name).all()

    return render_template(
        "player/create_match_proposal.html", users=users, verified_venues=verified_venues
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
@player_bp.route("/gara/<int:gara_id>")
@login_required
@player_required
def gara_detail(gara_id):
    """Dettaglio gara con iscrizioni e partite dell'utente"""
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        abort(404)

    # Verifica che l'utente sia iscritto alla gara
    inscription = Inscription.query.filter_by(
        gara_id=gara_id, user_id=current_user.id
    ).first()

    # Se l'utente è iscritto, mostra solo le sue partite
    # Se non è iscritto, può comunque vedere la gara ma senza le sue partite
    if inscription:
        matches = (
            Match.query.filter_by(gara_id=gara_id)
            .filter(
                db.or_(
                    Match.player1_id == current_user.id,
                    Match.player2_id == current_user.id,
                )
            )
            .order_by(Match.round_number, Match.id)
            .all()
        )
    else:
        # Utente non iscritto: nessuna partita personale
        matches = []
    
    # Per gli utenti non iscritti, recupera tutte le partite per mostrare l'andamento della gara
    all_matches = None
    if not inscription:
        all_matches = (
            Match.query.filter_by(gara_id=gara_id)
            .order_by(Match.round_number, Match.id)
            .all()
        )

    # Ottieni l'ultima classificazione disponibile (copiato dalla logica admin)
    current_round_classification = None
    latest_round_with_classification = None
    
    if gara.current_round > 0:
        # Cerca la classificazione più recente disponibile
        from models.classification.models import RoundClassification
        for round_num in range(gara.current_round, 0, -1):
            classification = RoundClassification.query.filter_by(
                gara_id=gara_id, round_number=round_num
            ).order_by(RoundClassification.position).all()
            
            if classification:
                current_round_classification = classification
                latest_round_with_classification = round_num
                break
    
    return render_template(
        "player/gara_detail.html",
        gara=gara,
        inscription=inscription,
        matches=matches,
        all_matches=all_matches,
        current_round_classification=current_round_classification,
        latest_round_with_classification=latest_round_with_classification,
    )


@player_bp.route("/gara/<int:gara_id>/inscribe", methods=["POST"])
@login_required
@player_only
def inscribe_to_gara(gara_id):
    """Iscriviti a una gara"""
    gara = Gara.query.get_or_404(gara_id)

    # Verifica che le iscrizioni siano aperte
    now = datetime.utcnow()
    if (
        gara.status != GaraStatus.INSCRIPTION.value
        or now < gara.inscription_start
        or now > gara.inscription_end
    ):
        flash("Le iscrizioni non sono disponibili.")
        return redirect(url_for("main.index"))

    # Verifica che non sia già iscritto
    existing = Inscription.query.filter_by(
        user_id=current_user.id, gara_id=gara_id
    ).first()
    if existing:
        flash("Sei già iscritto a questa gara.")
        return redirect(url_for("player.dashboard"))

    # Usa il service per gestire automaticamente la logica waitlist
    from models.competition.services import InscriptionService
    
    inscription = InscriptionService.inscribe_user(
        user_id=current_user.id, 
        gara_id=gara_id
    )
    
    if inscription:
        if inscription.is_waitlist:
            flash(f"Aggiunto alla lista d'attesa per Gara {gara.number} (posizione {inscription.waitlist_position})!")
        else:
            flash(f"Iscrizione alla Gara {gara.number} completata!")
    else:
        flash("Errore durante l'iscrizione.", "error")
    # Redirect alla dashboard appropriata
    return redirect(url_for("dashboard.dashboard"))


@player_bp.route("/match/<int:match_id>")
@login_required
@match_player_required
def match_detail(match_id):
    """Dettaglio partita per giocatore"""
    match = db.session.get(Match, match_id)
    if match is None:
        abort(404)

    racks = Rack.query.filter_by(match_id=match_id).order_by(Rack.rack_number).all()

    return render_template("match_detail.html", match=match, racks=racks)


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


@player_bp.route("/match/<int:match_id>/add_rack", methods=["POST"])
@login_required
@match_player_required
def add_rack(match_id):
    """Aggiunge un rack alla partita (stessa logica di report_rack_result)"""
    match = db.session.get(Match, match_id)
    if match is None:
        return jsonify({"error": "Partita non trovata"}), 404

    winner_id = int(request.form["winner_id"])

    # Verifica che il vincitore sia uno dei giocatori della partita
    if winner_id not in [match.player1_id, match.player2_id]:
        return jsonify({"error": "Giocatore non valido"}), 400

    # Usa il service layer
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

    # Iscrizioni dell'utente (incluse gare standalone)
    inscriptions = (
        Inscription.query.filter_by(user_id=current_user.id)
        .join(Gara)
        .outerjoin(Campionato)  # LEFT JOIN per includere gare standalone
        .order_by(Campionato.created_at.desc().nullslast(), Gara.date.desc())
        .all()
    )

    # Partite giocate (incluse gare standalone)
    matches = (
        Match.query.filter(
            db.or_(
                Match.player1_id == current_user.id, Match.player2_id == current_user.id
            )
        )
        .join(Gara)
        .outerjoin(Campionato)  # LEFT JOIN per includere gare standalone
        .order_by(
            Campionato.created_at.desc().nullslast(), Gara.date.desc(), Match.round_number.desc()
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

    # Classifiche per campionato
    classifications = (
        Classification.query.filter_by(user_id=current_user.id)
        .join(Campionato)
        .order_by(Campionato.created_at.desc())
        .all()
    )

    # Partite recenti (ultime 10)
    recent_matches = [m for m in matches if m.status == MatchStatus.COMPLETED.value][
        :10
    ]

    # Conta solo i campionati con gare completate dove l'utente ha partecipato
    completed_tournaments = set([
        insc.gara.campionato_id 
        for insc in inscriptions 
        if insc.gara.campionato_id is not None and insc.gara.status == 'completed'
    ])
    
    # Conta solo le gare completate
    completed_provas = len([
        insc for insc in inscriptions 
        if insc.gara.status == 'completed'
    ])

    stats = {
        "total_inscriptions": len(inscriptions),
        "total_matches": total_matches,
        "won_matches": won_matches,
        "lost_matches": total_matches - won_matches,
        "win_percentage": round(win_percentage, 1),
        "tournaments_played": len(completed_tournaments),
        "provas_played": completed_provas,
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


# ────────────────────────────────────────────────────────────────────────────────
# VENUE MANAGER REQUESTS (venue listing moved to unified admin.venue controller)
# ────────────────────────────────────────────────────────────────────────────────
# NOTE: Main venue listing and details now handled by admin.venue.venues_list() and admin.venue.venue_detail()
# with role-based content negotiation pattern


@player_bp.route("/request_venue_manager", methods=["POST"])
@login_required
def request_venue_manager():
    """Richiesta per diventare gestore di una sala specifica"""
    if current_user.is_admin:
        flash("Gli amministratori non hanno bisogno di richiedere il ruolo di gestore sala.", "info")
        return redirect(url_for("admin.venue.venues_list"))
    
    venue_id = request.form.get("venue_id")
    notes = request.form.get("notes", "").strip()
    
    if not venue_id:
        flash("Errore: Sala non specificata.", "error")
        return redirect(url_for("admin.venue.venues_list"))
    
    try:
        from models.user.services import VenueManagerRequestService
        new_request = VenueManagerRequestService.create_request(current_user.id, int(venue_id), notes)
        
        # Get venue for flash message
        from models import BilliardHall
        venue = db.session.get(BilliardHall, venue_id)
        
        flash_message = f"Richiesta per gestire '{venue.name}' inviata con successo!"
        if new_request.is_contested:
            flash_message += " Nota: questa sala ha già un gestore, l'admin valuterà la tua richiesta."
        flash(flash_message, "success")
        
    except ValueError as e:
        flash(str(e), "error")
    
    return redirect(url_for("admin.venue.venues_list"))


@player_bp.route("/cancel_venue_manager_request/<int:request_id>", methods=["POST"])
@login_required
def cancel_venue_manager_request(request_id):
    """Annulla una richiesta per diventare gestore di sala"""
    try:
        from models.user.services import VenueManagerRequestService
        VenueManagerRequestService.cancel_request(request_id, current_user)
        flash("Richiesta annullata con successo.", "success")
    except Exception as e:
        flash(f"Errore nell'annullare la richiesta: {str(e)}", "error")
    
    return redirect(url_for("admin.venue.venues_list"))


@player_bp.route("/my_venue_requests")
@login_required
def my_venue_requests():
    """Visualizza le richieste di gestione venue dell'utente"""
    if current_user.is_admin:
        return redirect(url_for("admin.venue.venue_manager_requests"))
    
    from models.user.services import VenueManagerRequestService
    requests = VenueManagerRequestService.get_user_requests(current_user.id)
    
    return render_template("player/my_venue_requests.html", requests=requests)


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


@player_bp.route("/gara/<int:gara_id>/unsubscribe", methods=["POST"])
@login_required
@player_only
def unsubscribe_from_gara(gara_id):
    """Disiscrizione da una gara"""
    gara = Gara.query.get_or_404(gara_id)

    # Verifica che l'utente sia iscritto
    inscription = Inscription.query.filter_by(
        user_id=current_user.id, gara_id=gara_id
    ).first()
    if not inscription:
        flash("Non sei iscritto a questa gara.")
        return redirect(url_for("player.dashboard"))

    # Verifica che la gara non sia ancora iniziata
    if gara.status not in [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]:
        flash("Impossibile disiscreversi: la gara è già iniziata!")
        return redirect(url_for("player.dashboard"))

    # Verifica che non ci siano partite già create
    existing_matches = Match.query.filter(
        db.or_(
            Match.player1_id == current_user.id, Match.player2_id == current_user.id
        ),
        Match.gara_id == gara_id,
    ).first()

    if existing_matches:
        flash("Impossibile disiscreversi: ci sono già partite programmate!")
        return redirect(url_for("player.dashboard"))

    # Procedi con la disiscrizione usando il servizio
    from models.competition.services import InscriptionService
    success = InscriptionService.uninscribe_user(current_user.id, gara_id)
    
    if success:
        flash(f"Disiscrizione dalla Gara {gara.number} completata!")
    else:
        flash("Errore durante la disiscrizione.", "error")
    
    # Redirect mantenendo il campionato selezionato
    return redirect(url_for("player.dashboard", campionato_id=gara.campionato_id))


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
