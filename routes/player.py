# routes/player.py - Community Player Features and Individual Match Management
#
# ═══════════════════════════════════════════════════════════════════════════════
# MIGRATION COMPLETED: Task 1.1 Phase 7 - Transaction Management Refactoring
# ═══════════════════════════════════════════════════════════════════════════════
#
# MIGRATION SUMMARY:
# ├─ Eliminated: 9 direct db.session.commit() calls → 0
# ├─ Added: 7 @transactional decorators with domain-specific boundaries
# ├─ Extracted: Complex business logic to MatchProposalService
# └─ Pattern: Simple CRUD → @transactional, Complex logic → service layer
#
# TRANSACTION BOUNDARIES BY DOMAIN:
# ├─ user: Director requests, profile updates, account deletion
# ├─ notification: Status updates, bulk operations, read confirmations
# └─ match: Rack operations, score corrections, confirmation states
#
# SERVICE INTEGRATIONS:
# ├─ MatchProposalService: accept_invitation(), reject_invitation(), cancel_proposal()
# ├─ InscriptionService: inscribe_user(), uninscribe_user() with waitlist management
# ├─ UserService: update_user(), change_password() with encryption
# ├─ UserDeletionService: delete_user() with soft delete and anonymization
# ├─ LocationService: create_billiard_hall() for community venue discovery
# └─ AvailabilityService: Player discovery and match coordination system
#
# ARCHITECTURAL IMPROVEMENTS:
# ├─ Transaction Safety: All database operations now properly isolated
# ├─ Business Logic: Centralized in services for consistency and testing
# ├─ Error Handling: Automatic rollback on exceptions with @transactional
# └─ Code Quality: Reduced route complexity, improved maintainability
from flask.blueprints import Blueprint
from flask.templating import render_template  # funzione reale
from flask.globals import request  # LocalProxy -> request
from flask.helpers import redirect, url_for, flash  # helper ufficiali Flask
from flask.json import jsonify  # funzione ufficiale Flask
from werkzeug.exceptions import abort  # più specifico e stabile
from flask_login import login_required, current_user, logout_user

from datetime import datetime
from typing import cast

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
from models.user.services import (
    UserDeletionService,
    UserService,
    VenueManagerRequestService,
    VenueManagementService,
)
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
from models.transaction.manager import transactional
from models.individual_match.services import MatchProposalService

player_bp = Blueprint("player", __name__)


def _handle_venue_creation_player(location: str) -> str:
    """
    Handle automatic venue creation for community match proposals.

    Business Logic:
    - First checks for existing verified venues (sala biliardo verificate)
    - Falls back to existing non-verified venues
    - Creates new non-verified venue if none exists
    - Preserves community-driven venue discovery pattern

    Post-Migration: Uses LocationService instead of direct database operations
    for transaction safety and business rule enforcement.

    Args:
        location: Venue name provided by player

    Returns:
        str: Location string to use for match proposal
    """
    if not location or not location.strip():
        return location

    location = location.strip()

    # Check if location matches existing verified venue
    existing_venue = BilliardHall.query.filter_by(
        name=location, is_active=True, verified=True
    ).first()

    if existing_venue:
        return location

    # Check if location matches existing non-verified venue
    existing_unverified = BilliardHall.query.filter_by(
        name=location, is_active=True
    ).first()

    if existing_unverified:
        return location

    # Create new non-verified venue
    try:
        # TODO: Consider implementing venue validation workflow
        # FIXME: Auto-created venues lack table count and verification status
        new_venue = LocationService.create_billiard_hall(
            name=location,
            added_by_id=current_user.id,
            # Set as non-verified (verified=False is default)
            # Note: number_of_tables is None, so it cannot be verified yet
        )
        flash(
            f"Nuovo luogo '{location}' aggiunto. Per la verifica serve anche il numero di tavoli.",
            "info",
        )
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
            # TODO: Implement venue suggestion system based on existing venues
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
            return redirect(url_for("individual_match.dashboard"))

        except Exception as e:
            flash(f"Error creating proposal: {str(e)}", "error")

    # Get available users and locations for the form
    from models.user.role_enum import UserRole

    # Escludi admin e current user dai giocatori invitabili
    # TODO: Add player skill-based filtering and availability integration
    # FIXME: Query excludes soft-deleted users but doesn't order by activity
    users = User.query.filter(
        User.id != current_user.id, User.role != UserRole.ADMIN.value
    ).all()

    # Get verified venues instead of recent locations
    from models.location.models import BilliardHall

    verified_venues = (
        BilliardHall.query.filter_by(is_active=True, verified=True)
        .order_by(BilliardHall.name)
        .all()
    )

    return render_template(
        "player/create_match_proposal.html",
        users=users,
        verified_venues=verified_venues,
    )


@player_bp.route("/match-proposals/<int:proposal_id>/accept", methods=["POST"])
@login_required
@player_only
def accept_match_proposal(proposal_id):
    """Accept a match proposal using service layer pattern.

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - Delegates to MatchProposalService.accept_invitation() for complex business logic
    - Eliminates direct db.session.commit() calls through service extraction
    - Ensures atomic transaction boundaries for multi-model operations
    - Validates proposal status, user permissions, and expiry constraints
    - Creates IndividualMatch + updates proposal status + sends notifications atomically

    Service Integration:
    - MatchProposalService provides route-optimized parameter order
    - IndividualMatchService.accept_invitation handles @transactional operations
    - Automatic rollback on validation failures or system errors
    """
    try:
        # POST-MIGRATION: Service layer handles complex acceptance logic
        # - Validates proposal status and expiry
        # - Creates IndividualMatch from accepted proposal
        # - Manages invitation state transitions
        # - Sends notifications to all participants
        individual_match = MatchProposalService.accept_invitation(
            proposal_id, current_user.id
        )
        flash(
            "Match proposal accepted successfully! You can now play the match.",
            "success",
        )
    except Exception as e:
        flash(f"Error accepting proposal: {str(e)}", "error")

    return redirect(url_for("individual_match.dashboard"))


@player_bp.route("/match-proposals/<int:proposal_id>/reject", methods=["POST"])
@login_required
@player_only
def reject_match_proposal(proposal_id):
    """Reject a match proposal using service layer pattern.

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - Service layer handles rejection workflow with @transactional guarantees
    - Updates invitation status + sends proposer notification atomically
    - Maintains proposal availability for other players (open proposals)
    - Eliminates direct database manipulation for improved transaction safety
    """
    try:
        # POST-MIGRATION: Service layer handles rejection workflow
        # - Updates invitation status
        # - Notifies proposer of rejection
        # - Maintains proposal availability for other players (open proposals)
        MatchProposalService.reject_invitation(proposal_id, current_user.id)
        flash("Match proposal rejected successfully.", "info")
    except Exception as e:
        flash(f"Error rejecting proposal: {str(e)}", "error")

    return redirect(url_for("individual_match.dashboard"))


@player_bp.route("/match-proposals/<int:proposal_id>/cancel", methods=["POST"])
@login_required
@player_only
def cancel_match_proposal(proposal_id):
    """Cancel a match proposal using service layer pattern.

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - Service layer validates proposer ownership before cancellation
    - Notifies all invited players + updates proposal status atomically
    - Prevents future interactions with cancelled proposal
    - Ensures data consistency through @transactional boundaries
    """
    from models.individual_match.services import MatchProposalService

    try:
        # POST-MIGRATION: Service layer handles cancellation business logic
        # - Validates proposer ownership
        # - Notifies all invited players
        # - Updates proposal status to cancelled
        # - Prevents future interactions with proposal
        MatchProposalService.cancel_proposal(proposal_id, current_user.id)
        flash("Match proposal cancelled.")
    except Exception as e:
        flash(f"Error cancelling proposal: {str(e)}", "error")

    return redirect(url_for("individual_match.dashboard"))


@player_bp.route("/")
@login_required
def dashboard():
    return redirect(url_for("dashboard.dashboard"))


# ═══════════════════════════════════════════════════════════════════════════════
# END INDIVIDUAL MATCH PROPOSAL ROUTES - Task 1.1 Phase 7 Migration Complete
# ═══════════════════════════════════════════════════════════════════════════════
# ARCHITECTURAL IMPROVEMENTS:
# ├─ Service Extraction: Complex business logic moved to MatchProposalService
# ├─ Transaction Safety: All proposal operations now use @transactional patterns
# ├─ Eliminated Commits: 3 direct db.session.commit() calls removed
# └─ Business Logic: Consistent validation and notification workflows
#
# INTEGRATION PATTERN:
# routes/player.py → MatchProposalService → IndividualMatchService → @transactional
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
            classification = (
                RoundClassification.query.filter_by(
                    gara_id=gara_id, round_number=round_num
                )
                .order_by(RoundClassification.position)
                .all()
            )

            if classification:
                current_round_classification = classification
                latest_round_with_classification = round_num
                break

    # Ottieni le challenge attive per questa gara
    from models.challenge.gara_challenge_models import GaraChallenge

    gara_challenges = GaraChallenge.query.filter_by(
        gara_id=gara_id, is_active=True
    ).all()

    # Se l'utente è iscritto, ottieni i suoi tentativi per ogni challenge
    user_challenge_data = []
    if inscription and gara_challenges:
        for gara_challenge in gara_challenges:
            user_attempts = gara_challenge.get_user_attempts(current_user.id)
            best_attempt = gara_challenge.get_user_best_attempt(current_user.id)
            can_attempt = gara_challenge.can_user_attempt(current_user.id)

            user_challenge_data.append(
                {
                    "gara_challenge": gara_challenge,
                    "challenge": gara_challenge.challenge,
                    "user_attempts": user_attempts,
                    "best_attempt": best_attempt,
                    "can_attempt": can_attempt,
                    "attempts_count": len(user_attempts),
                    "max_attempts": gara_challenge.max_attempts,
                }
            )

    # Raggruppa le partite per turno e analizza le discipline
    matches_by_round = {}
    all_matches_by_round = {}
    round_disciplines = {}  # turno -> {discipline: count}

    # Get configured disciplines for rounds (for Random strategy gare)
    from models.competition.round_configuration import RoundConfiguration

    configured_round_disciplines = {}
    if gara.matchmaking_strategy == "random":
        round_configs = RoundConfiguration.get_all_for_gara(gara_id)
        for config in round_configs:
            configured_round_disciplines[config.round_number] = config.discipline

    if matches:
        for match in matches:
            round_num = match.round_number
            if round_num not in matches_by_round:
                matches_by_round[round_num] = []
            matches_by_round[round_num].append(match)

    if all_matches:
        for match in all_matches:
            round_num = match.round_number
            if round_num not in all_matches_by_round:
                all_matches_by_round[round_num] = []
            all_matches_by_round[round_num].append(match)

            # Analizza le discipline per questo turno
            if round_num not in round_disciplines:
                round_disciplines[round_num] = {}

            # Usa la disciplina del match se presente, altrimenti quella della gara
            discipline = match.discipline if match.discipline else gara.discipline
            if discipline not in round_disciplines[round_num]:
                round_disciplines[round_num][discipline] = 0
            round_disciplines[round_num][discipline] += 1

    return render_template(
        "player/gara_detail.html",
        gara=gara,
        inscription=inscription,
        matches=matches,
        all_matches=all_matches,
        current_round_classification=current_round_classification,
        latest_round_with_classification=latest_round_with_classification,
        gara_challenges=gara_challenges,
        user_challenge_data=user_challenge_data,
        matches_by_round=matches_by_round,
        all_matches_by_round=all_matches_by_round,
        round_disciplines=round_disciplines,
        configured_round_disciplines=configured_round_disciplines,
    )


@player_bp.route("/gara/<int:gara_id>/inscribe", methods=["POST"])
@login_required
@player_only
def inscribe_to_gara(gara_id):
    """Iscriviti a una gara (Register for competition).

    Italian Business Terms:
    - 'gara': Individual competition/round within a tournament
    - 'iscrizione': Registration/inscription to participate
    - 'lista d'attesa': Waitlist when competition is full

    POST-MIGRATION: Uses InscriptionService for intelligent registration
    - Automatically handles waitlist management when competition is full
    - Validates inscription time windows and competition status
    - Provides position feedback for waitlisted players
    - Eliminates direct database manipulation for data consistency
    """
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
        user_id=current_user.id, gara_id=gara_id
    )

    if inscription:
        if inscription.is_waitlist:
            flash(
                f"Aggiunto alla lista d'attesa per Gara {gara.number} (posizione {inscription.waitlist_position})!"
            )
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

    # Get available challenges for this match's gara
    available_challenges = []
    player_challenge_progress = {}

    if match.gara_id:
        from models.challenge.gara_challenge_service import GaraChallengeService
        from models.challenge.gara_challenge_models import GaraChallenge
        from sqlalchemy.orm import joinedload

        # Get available challenges for this gara
        available_challenges = (
            db.session.query(GaraChallenge)
            .filter(
                GaraChallenge.gara_id == match.gara_id,
                GaraChallenge.is_active == True,
            )
            .options(joinedload(GaraChallenge.challenge))  # type: ignore[arg-type]
            .all()
        )

        # Get player challenge progress for both players
        if match.player1_id:
            progress = GaraChallengeService.get_user_gara_challenge_progress(
                match.gara_id, match.player1_id
            )
            if progress:
                player_challenge_progress[match.player1_id] = progress

        if match.player2_id:
            progress = GaraChallengeService.get_user_gara_challenge_progress(
                match.gara_id, match.player2_id
            )
            if progress:
                player_challenge_progress[match.player2_id] = progress

    return render_template(
        "match_detail.html",
        match=match,
        racks=racks,
        available_challenges=available_challenges,
        player_challenge_progress=player_challenge_progress,
    )


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
# (USER PROFILE AND ACCOUNT MANAGEMENT)
# Italian Business Context: Community player profile management
# - Personal statistics aggregation across tournaments
# - Account security and data privacy compliance
# - Challenge system integration for skill tracking


@player_bp.route("/profile")
@login_required
@player_only
def profile():
    """Profilo personale del giocatore (Personal player profile).

    Italian Business Terms:
    - 'campionato': Multi-round tournament (collection of gare)
    - 'gara'/'prova': Individual competition round
    - 'classifiche': Rankings/classifications
    - 'partite': Matches played

    Complex Query Logic:
    - Aggregates data across multiple domains: inscriptions, matches, classifications
    - Supports both campionato-based and standalone competitions (LEFT JOIN pattern)
    - Calculates comprehensive statistics: win rate, tournaments played, challenge progress
    - Integrates challenge system statistics with gara-based attempts
    - Maintains backward compatibility with legacy challenge models
    """

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
            Campionato.created_at.desc().nullslast(),
            Gara.date.desc(),
            Match.round_number.desc(),
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
    completed_tournaments = set(
        [
            insc.gara.campionato_id
            for insc in inscriptions
            if insc.gara.campionato_id is not None and insc.gara.status == "completed"
        ]
    )

    # Conta solo le gare completate
    completed_provas = len(
        [insc for insc in inscriptions if insc.gara.status == "completed"]
    )

    # Challenge statistics
    challenge_stats = None
    challenge_history = []
    try:
        # TODO: Refactor challenge statistics to use dedicated service
        # FIXME: Challenge import pattern is inconsistent across the codebase
        from models.challenge import GaraChallengeAttempt, GaraChallenge, Challenge

        # Get all challenge attempts by this user
        user_attempts = (
            GaraChallengeAttempt.query.filter_by(
                user_id=current_user.id, completed=True
            )
            .join(GaraChallenge)
            .join(Challenge)
            .order_by(GaraChallengeAttempt.attempted_at.desc())  # type: ignore[attr-defined]
            .all()
        )

        if user_attempts:
            # Calculate overall challenge statistics
            total_attempts = len(user_attempts)
            unique_challenges = len(
                set(attempt.gara_challenge.challenge_id for attempt in user_attempts)
            )
            unique_garas = len(
                set(attempt.gara_challenge.gara_id for attempt in user_attempts)
            )

            # Calculate average score (only for numeric challenges)
            numeric_attempts = [
                attempt
                for attempt in user_attempts
                if attempt.score is not None
                and not attempt.gara_challenge.challenge.pass_fail_only
            ]
            avg_score = (
                sum(attempt.score for attempt in numeric_attempts)
                / len(numeric_attempts)
                if numeric_attempts
                else 0
            )

            # Calculate pass rate (for pass/fail challenges)
            pass_fail_attempts = [
                attempt
                for attempt in user_attempts
                if attempt.gara_challenge.challenge.pass_fail_only
            ]
            pass_rate = (
                (
                    sum(1 for attempt in pass_fail_attempts if attempt.passed)
                    / len(pass_fail_attempts)
                    * 100
                )
                if pass_fail_attempts
                else 0
            )

            challenge_stats = {
                "total_attempts": total_attempts,
                "unique_challenges": unique_challenges,
                "unique_garas": unique_garas,
                "avg_score": round(avg_score, 1),
                "pass_rate": round(pass_rate, 1),
            }

            # Build challenge history (last 20 attempts)
            for attempt in user_attempts[:20]:
                challenge_history.append(
                    {
                        "challenge_name": attempt.gara_challenge.challenge.get_display_name(),
                        "gara_name": attempt.gara_challenge.gara.name,
                        "score": attempt.score,
                        "passed": attempt.passed,
                        "attempted_at": attempt.attempted_at,
                        "is_pass_fail": attempt.gara_challenge.challenge.pass_fail_only,
                        "max_score": attempt.gara_challenge.challenge.max_score,
                    }
                )

    except Exception as e:
        # If challenge module is not available or there's an error, just skip
        pass

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
        challenge_stats=challenge_stats,
        challenge_history=challenge_history,
    )


@player_bp.route("/profile/<int:user_id>")
def view_profile(user_id):
    """View another player's public profile"""
    from models.user.models import User
    from models.competition.models import Gara, Inscription
    from models.match.models import Match
    from models.status_enum import MatchStatus
    from models.classification.models import Classification
    from models.campionato.models import Campionato
    from models.challenge.models import Challenge, ChallengeAttempt

    user = db.session.get(User, user_id)
    if user is None:
        abort(404)

    # Public profile data (limited compared to personal profile)
    # Inscriptions
    inscriptions = (
        Inscription.query.filter_by(user_id=user.id)
        .join(Gara)
        .outerjoin(Campionato)
        .order_by(Campionato.created_at.desc().nullslast(), Gara.date.desc())
        .all()
    )

    # Matches played
    matches = (
        Match.query.filter(
            db.or_(Match.player1_id == user.id, Match.player2_id == user.id)
        )
        .join(Gara)
        .outerjoin(Campionato)
        .order_by(
            Campionato.created_at.desc().nullslast(),
            Gara.date.desc(),
            Match.round_number.desc(),
        )
        .all()
    )

    # Public statistics
    total_matches = len([m for m in matches if m.status == MatchStatus.COMPLETED.value])
    won_matches = len(
        [
            m
            for m in matches
            if m.status == MatchStatus.COMPLETED.value and m.winner_id == user.id
        ]
    )
    win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0

    # Recent matches (last 10)
    recent_matches = [m for m in matches if m.status == MatchStatus.COMPLETED.value][
        :10
    ]

    # Completed tournaments count
    completed_tournaments = set(
        [
            insc.gara.campionato_id
            for insc in inscriptions
            if insc.gara.campionato_id is not None and insc.gara.status == "completed"
        ]
    )

    completed_provas = len(
        [insc for insc in inscriptions if insc.gara.status == "completed"]
    )

    stats = {
        "total_inscriptions": len(inscriptions),
        "total_matches": total_matches,
        "won_matches": won_matches,
        "lost_matches": total_matches - won_matches,
        "win_percentage": round(win_percentage, 1),
        "tournaments_played": len(completed_tournaments),
        "provas_played": completed_provas,
    }

    # Challenge data
    challenge_attempts = (
        ChallengeAttempt.query.filter_by(user_id=user.id, completed=True)
        .join(Challenge)
        .order_by(ChallengeAttempt.created_at.desc())
        .all()
    )

    challenge_stats = None
    if challenge_attempts:
        total_attempts = len(challenge_attempts)
        unique_challenges = len(
            set(attempt.challenge_id for attempt in challenge_attempts)
        )
        avg_score = (
            sum(attempt.score for attempt in challenge_attempts) / total_attempts
        )
        pass_count = sum(1 for attempt in challenge_attempts if attempt.passed)
        pass_rate = (pass_count / total_attempts * 100) if total_attempts > 0 else 0

        challenge_stats = {
            "total_attempts": total_attempts,
            "unique_challenges": unique_challenges,
            "avg_score": round(avg_score, 1),
            "pass_rate": round(pass_rate, 1),
        }

    return render_template(
        "player/profile.html",
        user=user,
        inscriptions=inscriptions,
        matches=recent_matches,
        stats=stats,
        challenge_stats=challenge_stats,
        challenge_history=challenge_attempts,
        classifications=[],
    )


@player_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
@player_only
def edit_profile():
    """Modifica email e telefono dell'utente corrente (Edit current user email and phone).

    POST-MIGRATION: Uses UserService for validation and encryption
    - Handles encrypted field updates (email, phone) through service layer
    - Validates email format and uniqueness constraints
    - Maintains data integrity without direct model manipulation
    """
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
    """Cambia la password dell'utente corrente (Change current user password).

    POST-MIGRATION: Uses UserService for secure password management
    - Validates current password before allowing change
    - Enforces password strength requirements
    - Handles password hashing through service layer
    """
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
@transactional(domain="user")  # Transaction boundary: User domain operations
def request_director():
    """Richiede la promozione a direttore di gara (Request promotion to tournament director).

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - @transactional(domain="user") ensures atomic user domain operations
    - Eliminates manual db.session.commit() call for improved transaction boundaries
    - Creates DirectorRequest + sends admin notification in single transaction
    - Automatic rollback on exceptions maintains data consistency
    - Follows Phase 9 migration pattern for admin route consistency
    """
    if current_user.role != "player":
        flash("Solo i giocatori possono richiedere di diventare direttori.")
        return redirect(url_for("player.profile"))
    if current_user.director_request:
        flash("Hai già una richiesta in sospeso o è stata valutata.")
        return redirect(url_for("player.profile"))

    reason = request.form.get("reason", "").strip()
    req = DirectorRequest(
        user_id=current_user.id,
        status=DirectorRequestStatus.PENDING.value,
        notes=reason,
    )
    db.session.add(req)

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
@transactional(domain="notification")  # Transaction boundary: Notification status updates
def notifications():
    """Mostra le notifiche dell'utente (Show user notifications).

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - @transactional(domain="notification") ensures atomic status updates
    - Bulk notification status updates (PENDING → SENT) in single transaction
    - Eliminates manual db.session.commit() for better error handling
    - Prevents race conditions during concurrent notification access
    - Transaction isolation specific to notification domain operations
    """
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

    return render_template(
        "player/notifications.html", notifications=user_notifications
    )


@player_bp.route("/notifications/<int:notification_id>/mark_read", methods=["POST"])
@login_required
@transactional(domain="notification")  # Transaction boundary: Single notification update
def mark_notification_read(notification_id):
    """Segna una notifica come letta (Mark notification as read).

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - @transactional(domain="notification") replaces direct db.session.commit()
    - Atomic update: status + read_at timestamp in single transaction
    - Maintains notification state consistency during concurrent access
    - Preserves action_url redirect functionality for workflow integration
    """
    from models.notification.models import Notification, NotificationStatus

    notification = Notification.query.filter_by(
        id=notification_id, user_id=current_user.id
    ).first_or_404()

    notification.status = NotificationStatus.READ
    notification.read_at = datetime.utcnow()

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
        flash(
            "Gli amministratori non hanno bisogno di richiedere il ruolo di gestore sala.",
            "info",
        )
        return redirect(url_for("admin.venue.venues_list"))

    venue_id = request.form.get("venue_id")
    notes = request.form.get("notes", "").strip()

    if not venue_id:
        flash("Errore: Sala non specificata.", "error")
        return redirect(url_for("admin.venue.venues_list"))

    try:
        from models.user.services import VenueManagerRequestService

        new_request = VenueManagerRequestService.create_request(
            current_user.id, int(venue_id), notes
        )

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

        VenueManagerRequestService.cancel_request(request_id, cast(User, current_user))
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
@transactional(domain="notification")  # Transaction boundary: Bulk notification updates
def mark_all_notifications_read():
    """Segna tutte le notifiche come lette (Mark all notifications as read).

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - @transactional(domain="notification") ensures atomic bulk notification updates
    - Eliminates manual db.session.commit() for improved error handling
    - Bulk UPDATE query performance with transaction safety guarantees
    - Prevents partial notification status updates on system failures
    """
    from models.notification.models import Notification, NotificationStatus

    Notification.query.filter_by(user_id=current_user.id).filter(
        Notification.status != NotificationStatus.READ
    ).update({"status": NotificationStatus.READ, "read_at": datetime.utcnow()})
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
        # TODO: Implement account recovery grace period before permanent deletion
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
# (TOURNAMENT UNREGISTRATION)
# Business Logic: Withdrawal management with data integrity
# - Prevents withdrawal after matches are scheduled
# - Promotes waitlisted players when spots become available


@player_bp.route("/gara/<int:gara_id>/unsubscribe", methods=["POST"])
@login_required
@player_only
def unsubscribe_from_gara(gara_id):
    """Disiscrizione da una gara (Unregister from competition).

    Italian Business Terms:
    - 'disiscrizione': Unregistration/withdrawal from competition
    - 'partite programmate': Scheduled matches that prevent withdrawal

    Business Logic Validation:
    - Prevents unregistration after competition has started
    - Verifies no matches have been created for the player
    - Uses InscriptionService for waitlist promotion when player withdraws
    - Maintains data consistency during withdrawal process
    """
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
# (SCORE CONFIRMATION/REMOVAL SYSTEM)
# Player-driven score validation for fair tournament play
# - Peer confirmation system for accurate scoring
# - Error correction capabilities for rack entry mistakes
# - Maintains match state consistency during score changes


@player_bp.route("/rack/<int:rack_id>/remove", methods=["POST"])
@login_required
@transactional(domain="match")  # Transaction boundary: Match scoring consistency
def remove_rack(rack_id):
    """Rimuovi un rack inserito per errore (Remove incorrectly entered rack).

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - @transactional(domain="match") ensures atomic rack removal + score recalculation
    - Eliminates manual db.session.commit() for improved match state consistency
    - Multi-step operation: rack deletion + score update + match status in single transaction
    - Critical for tournament scoring accuracy and data integrity
    - Automatic rollback if any step fails preserves match validity
    """
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
@transactional(domain="match")  # Transaction boundary: Rack confirmation state
def confirm_rack(rack_id):
    """Conferma un rack inserito dall'altro giocatore (Confirm rack entered by opponent).

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - @transactional(domain="match") for atomic rack confirmation state
    - Eliminates manual db.session.commit() for improved transaction boundaries
    - Updates confirmed_by_player flag with transaction safety
    - Peer validation system maintains scoring accuracy through atomic updates
    """
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

    return jsonify({"success": True, "message": "Rack confermato"})


@player_bp.route("/rack/<int:rack_id>/unconfirm", methods=["POST"])
@login_required
@transactional(domain="match")  # Transaction boundary: Confirmation state reversal
def unconfirm_rack(rack_id):
    """Rimuovi conferma da un rack (Remove confirmation from rack).

    POST-MIGRATION ARCHITECTURE (Task 1.1 Phase 7):
    - @transactional(domain="match") ensures atomic confirmation state reversal
    - Eliminates manual db.session.commit() for better error handling
    - Reverts confirmed_by_player flag with transaction safety guarantees
    - Allows players to reconsider confirmations while maintaining data consistency
    """
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


# ====================================================================
# AVAILABILITY SYSTEM ROUTES - Use Case 7: Player Discovery & Coordination
# ====================================================================
# POST-MIGRATION: Complete availability system for community match coordination
# - Location-based player discovery for casual games
# - Venue-specific availability management
# - Notification system for availability alerts
# - Integration with individual match proposal system


@player_bp.route("/availability")
@login_required
@player_required
def availability_preferences():
    """Manage player availability preferences"""
    from models.individual_match.availability_service import AvailabilityService

    preferences = AvailabilityService.get_user_availability_preferences(current_user.id)
    venues = BilliardHall.query.filter_by(is_active=True).all()

    return render_template(
        "player/availability_preferences.html", preferences=preferences, venues=venues
    )


@player_bp.route("/availability/location", methods=["POST"])
@login_required
@player_required
def set_location_availability():
    """Set availability for a specific location"""
    from models.individual_match.availability_service import AvailabilityService

    location = request.form.get("location", "").strip()
    is_available = request.form.get("is_available") == "true"
    preferred_days = request.form.getlist("preferred_days")
    preferred_times = request.form.get("preferred_times", "").strip()

    if not location:
        flash("La location è obbligatoria", "danger")
        return redirect(url_for("player.availability_preferences"))

    try:
        # Convert day strings to integers
        day_ints = [int(d) for d in preferred_days if d.isdigit()]

        AvailabilityService.set_player_availability(
            user_id=current_user.id,
            location=location,
            is_available=is_available,
            preferred_days=day_ints if day_ints else None,
            preferred_times=preferred_times if preferred_times else None,
        )

        flash(f"Disponibilità aggiornata per {location}", "success")

        # If setting availability, optionally notify other players
        if is_available and request.form.get("notify_players") == "true":
            notifications_sent = AvailabilityService.notify_players_of_availability(
                user_id=current_user.id, location=location
            )
            if notifications_sent > 0:
                flash(
                    f"Notificati {notifications_sent} giocatori della tua disponibilità",
                    "info",
                )

    except Exception as e:
        flash(f"Errore nell'aggiornare la disponibilità: {str(e)}", "danger")

    return redirect(url_for("player.availability_preferences"))


@player_bp.route("/availability/venue", methods=["POST"])
@login_required
@player_required
def set_venue_availability():
    """Set availability for a specific venue"""
    from models.individual_match.availability_service import AvailabilityService

    venue_id = request.form.get("venue_id", type=int)
    is_available = request.form.get("is_available") == "true"
    available_days = request.form.getlist("available_days")
    preferred_times = request.form.get("preferred_times", "").strip()

    if not venue_id:
        flash("Devi selezionare una sala", "danger")
        return redirect(url_for("player.availability_preferences"))

    try:
        # Convert day strings to integers
        day_ints = [int(d) for d in available_days if d.isdigit()]

        AvailabilityService.set_venue_availability(
            user_id=current_user.id,
            billiard_hall_id=venue_id,
            is_available=is_available,
            available_days=day_ints if day_ints else None,
            preferred_times=preferred_times if preferred_times else None,
        )

        venue = db.session.get(BilliardHall, venue_id)
        venue_name = venue.name if venue else f"Sala #{venue_id}"
        flash(f"Disponibilità aggiornata per {venue_name}", "success")

    except Exception as e:
        flash(f"Errore nell'aggiornare la disponibilità: {str(e)}", "danger")

    return redirect(url_for("player.availability_preferences"))


@player_bp.route("/availability/discover")
@login_required
@player_required
def discover_available_players():
    """Discover players available at various locations"""
    from models.individual_match.availability_service import AvailabilityService

    # Get location filter from query params
    location_filter = request.args.get("location", "").strip()
    venue_filter = request.args.get("venue_id", type=int)

    available_players = {}

    if location_filter:
        # Get players available at specific location
        players = AvailabilityService.get_available_players_at_location(
            location=location_filter, exclude_user_id=current_user.id
        )
        available_players[location_filter] = players

    elif venue_filter:
        # Get players available at specific venue
        players = AvailabilityService.get_available_players_at_venue(
            billiard_hall_id=venue_filter, exclude_user_id=current_user.id
        )
        venue = db.session.get(BilliardHall, venue_filter)
        venue_name = venue.name if venue else f"Sala #{venue_filter}"
        available_players[venue_name] = players

    else:
        # Get all locations with available players
        from models.individual_match.models import PlayerAvailability
        from models.location.models import UserLocationAvailability

        # TODO: Implement geographic distance filtering for location discovery
        # FIXME: Duplicate availability queries could be optimized with single query
        # Get all locations with available players
        locations = (
            db.session.query(PlayerAvailability.location)
            .filter(
                PlayerAvailability.is_available == True,
                PlayerAvailability.user_id != current_user.id,
            )
            .distinct()
            .all()
        )

        for (location,) in locations:
            players = AvailabilityService.get_available_players_at_location(
                location=location, exclude_user_id=current_user.id
            )
            if players:
                available_players[location] = players

        # Get all venues with available players
        venues = (
            db.session.query(
                UserLocationAvailability.billiard_hall_id, BilliardHall.name
            )
            .join(BilliardHall)
            .filter(
                UserLocationAvailability.is_available == True,
                UserLocationAvailability.user_id != current_user.id,
            )
            .distinct()
            .all()
        )

        for venue_id, venue_name in venues:
            players = AvailabilityService.get_available_players_at_venue(
                billiard_hall_id=venue_id, exclude_user_id=current_user.id
            )
            if players:
                available_players[venue_name] = players

    venues = BilliardHall.query.filter_by(is_active=True).all()

    return render_template(
        "player/discover_players.html",
        available_players=available_players,
        venues=venues,
        location_filter=location_filter,
        venue_filter=venue_filter,
    )


@player_bp.route("/availability/request_match/<int:target_user_id>", methods=["POST"])
@login_required
@player_required
def request_availability_match(target_user_id):
    """Request a match with an available player"""
    from models.individual_match.availability_service import AvailabilityService
    from datetime import datetime, timedelta

    location = request.form.get("location", "").strip()
    message = request.form.get("message", "").strip()
    proposed_date = request.form.get("proposed_date")
    proposed_time = request.form.get("proposed_time")

    if not location:
        flash("La location è obbligatoria per richiedere un match", "danger")
        return redirect(url_for("player.discover_available_players"))

    # Parse proposed datetime
    proposed_datetime = None
    if proposed_date and proposed_time:
        try:
            proposed_datetime = datetime.strptime(
                f"{proposed_date} {proposed_time}", "%Y-%m-%d %H:%M"
            )
        except ValueError:
            flash("Formato data/ora non valido", "danger")
            return redirect(url_for("player.discover_available_players"))

    try:
        proposal = AvailabilityService.create_availability_based_match_request(
            requesting_user_id=current_user.id,
            target_user_id=target_user_id,
            location=location,
            proposed_datetime=proposed_datetime,
            message=message,
        )

        target_user = db.session.get(User, target_user_id)
        target_name = (
            target_user.username if target_user else f"Utente #{target_user_id}"
        )

        flash(f"Richiesta di match inviata a {target_name}", "success")

    except Exception as e:
        flash(f"Errore nell'inviare la richiesta: {str(e)}", "danger")

    return redirect(url_for("player.discover_available_players"))


# ====================================================================
# CHALLENGE SYSTEM ROUTES - Skill Development Integration
# ====================================================================
# Business Logic: Challenge attempts tied to specific competitions (gare)
# - Validates player access to competition before allowing attempts
# - Supports both numeric scoring and pass/fail challenges
# - Integrates with X-replacement system for tournament byes


@player_bp.route("/challenge/<int:gara_challenge_id>")
@login_required
def challenge_detail(gara_challenge_id):
    """Show challenge detail page for players"""
    from models.challenge.gara_challenge_models import GaraChallenge
    from models.challenge.services import ChallengeService

    gara_challenge = db.session.get(GaraChallenge, gara_challenge_id)
    if not gara_challenge:
        abort(404, "Challenge non trovata")

    # Verify user has access to this challenge's gara
    if gara_challenge.gara.campionato:
        # For campionato gara, user should be registered to access challenges
        inscription = Inscription.query.filter_by(
            user_id=current_user.id, gara_id=gara_challenge.gara_id
        ).first()
        if not inscription:
            abort(403, "Non hai accesso a questa challenge")

    # Get user progress for this challenge's gara
    from models.challenge.gara_challenge_service import GaraChallengeService

    progress = GaraChallengeService.get_user_gara_challenge_progress(
        gara_challenge.gara_id, current_user.id
    )

    challenge_data = None
    if progress:
        # Find the specific challenge data
        challenge_data = next(
            (
                c
                for c in progress.get("challenges", [])
                if c.get("gara_challenge", {}).get("id") == gara_challenge_id
            ),
            None,
        )

    return render_template(
        "player/gara_challenge_detail.html",
        gara_challenge=gara_challenge,
        challenge_data=challenge_data,
        user_progress=progress,
    )


@player_bp.route("/challenge/<int:gara_challenge_id>/attempt", methods=["POST"])
@login_required
def record_challenge_attempt(gara_challenge_id):
    """Record a challenge attempt by the player"""
    from models.challenge.gara_challenge_models import GaraChallenge
    from models.challenge.gara_challenge_service import GaraChallengeService

    try:
        data = request.get_json() if request.is_json else request.form.to_dict()

        # Get gara challenge and verify access
        gara_challenge = db.session.get(GaraChallenge, gara_challenge_id)
        if not gara_challenge:
            return jsonify({"success": False, "error": "Challenge non trovata"}), 404

        # Verify user has access to this challenge's gara
        if gara_challenge.gara.campionato:
            inscription = Inscription.query.filter_by(
                user_id=current_user.id, gara_id=gara_challenge.gara_id
            ).first()
            if not inscription:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Non hai accesso a questa challenge",
                        }
                    ),
                    403,
                )

        # Validate that we have either score or passed
        if "score" not in data and "passed" not in data:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Specificare punteggio o risultato pass/fail",
                    }
                ),
                400,
            )

        # Record the attempt
        score = data.get("score")
        passed = data.get("passed")

        # Convert types
        if score is not None:
            score = int(score)
        if passed is not None:
            passed = bool(passed) if isinstance(passed, bool) else passed == "true"

        attempt = GaraChallengeService.record_challenge_attempt(
            gara_challenge_id=gara_challenge_id,
            user_id=current_user.id,
            score=score,
            passed=passed,
            notes=data.get("notes"),
        )

        return jsonify(
            {
                "success": True,
                "message": "Tentativo registrato con successo",
                "attempt_id": attempt.id,
                "score": attempt.score,
                "passed": attempt.passed,
            }
        )

    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Errore durante la registrazione: {str(e)}",
                }
            ),
            500,
        )


@player_bp.route("/profile/<int:user_id>/export/csv")
@login_required
def export_profile_csv(user_id):
    """Export player profile and match history to CSV"""
    import csv
    import io
    from flask import Response

    # Check permissions - can only export own profile
    # TODO: Implement admin override for profile export (for user support)
    # FIXME: Add rate limiting for export functionality to prevent abuse
    user = cast(User, current_user)
    if user.id != user_id:
        abort(403)

    target_user = db.session.get(User, user_id)
    if not target_user:
        abort(404)

    # Get all completed matches for the user
    matches = Match.query.filter(
        (Match.player1_id == user_id) | (Match.player2_id == user_id),
        Match.status == MatchStatus.COMPLETED.value,
    ).all()

    # Get challenge attempts
    from models.challenge.models import ChallengeAttempt

    challenges = ChallengeAttempt.query.filter_by(user_id=user_id, completed=True).all()

    # Create CSV content
    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers
    writer.writerow(
        [
            "tipo",
            "data",
            "competizione",
            "avversario",
            "risultato",
            "punteggio",
            "turno",
            "challenge",
            "valore",
            "superato",
        ]
    )

    # Write match data
    for match in matches:
        opponent = ""
        result = ""
        if match.player1_id == user_id:
            opponent = match.player2.username if match.player2 else "Bye"
            result = "Win" if match.winner_id == user_id else "Loss"
        else:
            opponent = match.player1.username
            result = "Win" if match.winner_id == user_id else "Loss"

        competition_name = ""
        if match.gara.campionato:
            competition_name = (
                f"{match.gara.campionato.name} - Gara {match.gara.number}"
            )
        else:
            competition_name = match.gara.name

        writer.writerow(
            [
                "Tournament Match",
                match.gara.date.strftime("%Y-%m-%d") if match.gara.date else "",
                competition_name,
                opponent,
                result,
                f"{match.player1_score}-{match.player2_score}",
                match.round_number,
                "",
                "",
                "",
            ]
        )

    # Write challenge data
    for attempt in challenges:
        challenge_name = ""
        if hasattr(attempt, "challenge") and attempt.challenge:
            challenge_name = attempt.challenge.description
        elif hasattr(attempt, "gara_challenge") and attempt.gara_challenge:
            challenge_name = attempt.gara_challenge.challenge.description

        writer.writerow(
            [
                "Challenge",
                attempt.created_at.strftime("%Y-%m-%d") if attempt.created_at else "",
                "",
                "",
                "",
                "",
                "",
                challenge_name,
                attempt.score,
                "Yes" if attempt.passed else "No",
            ]
        )

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=player_{target_user.username}_history.csv"
        },
    )
