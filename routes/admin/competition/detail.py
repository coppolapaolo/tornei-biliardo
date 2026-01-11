# routes/admin/competition/detail.py
"""Gara detail view - unified for all user roles."""

from flask import (
    render_template,
    abort,
)
from flask_login import current_user

from models import (
    db,
    Gara,
    Inscription,
    Match,
)
from models.status_enum import (
    MatchStatus,
    Discipline,
)
from models.classification.models import RoundClassification
from models.classification.services import RoundClassificationService

from . import competition_bp


@competition_bp.route("/<int:gara_id>")
def gara_detail(gara_id):
    """
    Vista unificata per dettaglio gara.
    Si adatta automaticamente in base ai permessi dell'utente:
    - Admin/Director con permessi → Vista gestionale completa
    - Player iscritto → Vista personale con le sue partite
    - Guest/Player non iscritto → Vista pubblica read-only
    """
    gara = db.session.get(Gara, gara_id)
    if gara is None:
        abort(404)

    # Forza un refresh per assicurarsi di avere i dati più aggiornati
    db.session.refresh(gara)

    # Determina permessi e contesto utente
    user_can_manage = False
    user_inscription = None

    if current_user.is_authenticated:
        # Check se può gestire questa gara
        user_can_manage = current_user.can_manage_competition(gara_id)

        # Check iscrizione (solo per non-admin)
        if not current_user.is_admin:
            user_inscription = Inscription.query.filter_by(
                gara_id=gara_id,
                user_id=current_user.id
            ).first()

    # Carica dati in base al contesto utente
    if user_can_manage:
        # ADMIN/DIRECTOR VIEW: Carica tutto per gestione
        matches = (
            Match.query.filter_by(gara_id=gara_id)
            .order_by(Match.round_number, Match.id)
            .all()
        )
        all_matches = matches  # Needed for _round_management.html round completion check

    elif user_inscription:
        # PLAYER VIEW: Solo le sue partite
        matches = (
            Match.query.filter_by(gara_id=gara_id)
            .filter(
                db.or_(
                    Match.player1_id == current_user.id,
                    Match.player2_id == current_user.id
                )
            )
            .order_by(Match.round_number, Match.id)
            .all()
        )
        all_matches = (
            Match.query.filter_by(gara_id=gara_id)
            .order_by(Match.round_number, Match.id)
            .all()
        )
    else:
        # GUEST VIEW: Tutte le partite (read-only)
        matches = None
        all_matches = (
            Match.query.filter_by(gara_id=gara_id)
            .order_by(Match.round_number, Match.id)
            .all()
        )

    # Carica dati admin solo se può gestire
    users = None
    can_manage_directors = False
    show_admin_management = False
    show_director_management = False
    match_can_modify = {}

    # Carica iscrizioni per TUTTI gli utenti (visibili nel template)
    from models.user.models import User, DirectorAssignment

    inscriptions = (
        Inscription.query.filter_by(gara_id=gara_id)
        .join(User, Inscription.user_id == User.id)
        .order_by(User.username)
        .all()
    )

    if user_can_manage:

        # Get already assigned directors for this gara
        assigned_director_ids = (
            db.session.query(DirectorAssignment.user_id)
            .filter(
                DirectorAssignment.entity_type == "gara",
                DirectorAssignment.entity_id == gara.id,
            )
            .all()
        )
        assigned_director_ids = [d[0] for d in assigned_director_ids]

        # Also add the principal director if it's a standalone gara
        if gara.is_standalone and gara.director_id:
            assigned_director_ids.append(gara.director_id)

        # Get available users for director selection
        query = (
            User.query.filter(User.role == "director")
            .filter(User.deleted_at.is_(None))
            .filter(User.id != current_user.id)
        )

        if assigned_director_ids:
            query = query.filter(~User.id.in_(assigned_director_ids))

        users = query.order_by(User.username).all()

        # Permission checks for director management
        is_gara_director = (
            db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "gara",
                DirectorAssignment.entity_id == gara.id,
                DirectorAssignment.user_id == current_user.id,
            )
            .first()
            is not None
        )

        is_campionato_director = False
        if not gara.is_standalone and gara.campionato_id:
            is_campionato_director = (
                db.session.query(DirectorAssignment)
                .filter(
                    DirectorAssignment.entity_type == "campionato",
                    DirectorAssignment.entity_id == gara.campionato_id,
                    DirectorAssignment.user_id == current_user.id,
                )
                .first()
                is not None
            )

        can_manage_directors = current_user.is_admin or (
            current_user.is_director
            and (
                is_gara_director
                or is_campionato_director
                or (gara.is_standalone and gara.director_id == current_user.id)
            )
        )
        show_admin_management = current_user.is_admin
        show_director_management = current_user.is_director and can_manage_directors

        # Add match modification permissions
        from models.competition.round_manager import AdvancedRoundManager

        for match in matches:
            can_modify, _ = AdvancedRoundManager.can_modify_match(match.id)
            match_can_modify[match.id] = can_modify

    # Ottieni l'ultima classificazione disponibile per turni completati
    current_round_classification = None
    latest_round_with_classification = None

    if gara.current_round > 0:
        # For Random strategy: show overall classification if ANY matches are completed
        # For other strategies: show classification only for completed rounds
        if gara.matchmaking_strategy == "random":
            # Random: calcola classifica complessiva da tutti i match completati
            completed_count = Match.query.filter_by(
                gara_id=gara_id, status=MatchStatus.COMPLETED.value
            ).count()

            if completed_count > 0:
                # Usa il numero massimo di turni (query dal database) per la classifica complessiva
                from sqlalchemy import func
                max_round = db.session.query(func.max(Match.round_number)).filter(
                    Match.gara_id == gara_id
                ).scalar() or gara.current_round
                RoundClassification.calculate_classification_after_round(
                    gara_id, max_round
                )
                classification = (
                    RoundClassification.query.filter_by(
                        gara_id=gara_id, round_number=max_round
                    )
                    .order_by(RoundClassification.position)
                    .all()
                )
                if classification:
                    current_round_classification = classification
                    # For Random, use 0 to indicate overall classification
                    latest_round_with_classification = 0
        else:
            # Amalfi/other strategies: classification per completed round
            def is_round_completed(round_number):
                round_matches = Match.query.filter_by(
                    gara_id=gara_id, round_number=round_number
                ).all()
                if not round_matches:
                    return False
                # Exclude bye matches from completion check
                return all(
                    match.status == MatchStatus.COMPLETED.value or match.is_bye
                    for match in round_matches
                )

            # Cerca la classificazione del turno completato più recente
            for round_num in range(gara.current_round, 0, -1):
                if is_round_completed(round_num):
                    # SEMPRE ricalcola la classificazione per garantire dati
                    # aggiornati. Necessario perché i risultati potrebbero essere
                    # stati modificati dopo il calcolo iniziale
                    RoundClassification.calculate_classification_after_round(
                        gara_id, round_num
                    )

                    # Carica la classificazione appena ricalcolata
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

    # Get challenge data
    challenge_classification = None
    gara_challenges = None
    user_challenge_data = None

    if gara.matchmaking_strategy == "random":
        from models.challenge import GaraChallengeService

        if GaraChallengeService.has_active_challenges(gara_id):
            if user_can_manage:
                # Admin view: challenge classification
                challenge_classification = (
                    GaraChallengeService.update_gara_classification(gara_id)
                )
            gara_challenges = GaraChallengeService.get_gara_challenges(gara_id)

    # Per player iscritto: carica challenge personali
    if user_inscription and gara_challenges:
        user_challenge_data = []
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

    # Get available tables for gara (for table assignment UI)
    available_tables = []
    if user_can_manage:
        from models.match.table_assignment_service import TableAssignmentService

        available_tables = TableAssignmentService.get_table_names_for_gara(gara.id)

    # Get forfeit user IDs for visual indication
    forfeit_user_ids = set(
        insc.user_id for insc in inscriptions if insc.is_forfeit
    )

    return render_template(
        "gara_detail.html",  # Template unificato
        gara=gara,
        user_can_manage=user_can_manage,
        user_inscription=user_inscription,
        inscriptions=inscriptions,
        matches=matches,
        all_matches=all_matches,
        users=users,
        can_manage_directors=can_manage_directors,
        show_admin_management=show_admin_management,
        show_director_management=show_director_management,
        current_round_classification=current_round_classification,
        latest_round_with_classification=latest_round_with_classification,
        challenge_classification=challenge_classification,
        gara_challenges=gara_challenges,
        user_challenge_data=user_challenge_data,
        match_can_modify=match_can_modify,
        discipline_choices=Discipline.get_choices(),
        available_tables=available_tables,
        forfeit_user_ids=forfeit_user_ids,
    )
