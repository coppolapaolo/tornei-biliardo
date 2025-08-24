# routes/admin/user.py
"""User management blueprint for admin interface."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import func, desc, case

from models import (
    db,
    User,
    Inscription,
    Match,
    Prova,
    Tournament,
    Classification,
    DirectorRequest,
)
from utils import admin_required
from models.status_enum import DirectorRequestStatus, MatchStatus

# User management blueprint
user_bp = Blueprint("user", __name__)


@user_bp.route("/users")
@admin_required
def users_list():
    """Lista di tutti gli utenti con statistiche"""

    users = (
        db.session.query(
            User,
            func.count(Inscription.id).label("total_inscriptions"),
            func.count(Match.id).label("total_matches"),
            func.sum(case((Match.winner_id == User.id, 1), else_=0)).label(
                "matches_won"
            ),
        )
        .outerjoin(Inscription, User.id == Inscription.user_id)
        .outerjoin(
            Match, db.or_(Match.player1_id == User.id, Match.player2_id == User.id)
        )
        .filter(User.role != "admin")
        .group_by(User.id)
        .order_by(desc("total_inscriptions"), User.username)
        .all()
    )

    return render_template("admin/users_list.html", users=users)


@user_bp.route("/user/<int:user_id>")
@admin_required
def user_detail(user_id):
    """Scheda dettagliata utente"""
    user = User.query.get_or_404(user_id)

    # se l'utente è admin, ritorna alla lista utenti
    if user.role == "admin":
        return redirect(url_for("admin.user.users_list"))

    # Iscrizioni dell'utente
    inscriptions = (
        Inscription.query.filter_by(user_id=user_id)
        .join(Prova)
        .join(Tournament)
        .order_by(Tournament.created_at.desc(), Prova.number.desc())
        .all()
    )

    # Partite giocate
    matches = (
        Match.query.filter(
            db.or_(Match.player1_id == user_id, Match.player2_id == user_id)
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
            if m.status == MatchStatus.COMPLETED.value and m.winner_id == user_id
        ]
    )
    win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0

    # Classifiche per torneo
    classifications = (
        Classification.query.filter_by(user_id=user_id)
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
        "admin/user_detail.html",
        user=user,
        inscriptions=inscriptions,
        matches=recent_matches,
        classifications=classifications,
        stats=stats,
    )


@user_bp.route("/director_requests")
@admin_required
def director_requests():
    """Lista richieste di promozione a direttore"""
    pending = DirectorRequest.query.filter_by(
        status=DirectorRequestStatus.PENDING.value
    ).all()
    return render_template("admin/director_requests.html", requests=pending)


@user_bp.route("/director_requests/<int:req_id>/approve", methods=["POST"])
@admin_required
def approve_director_request(req_id):
    """Approva richiesta di promozione a direttore"""
    req = DirectorRequest.query.get_or_404(req_id)
    req.status = DirectorRequestStatus.APPROVED.value
    req.user.role = "director"
    db.session.commit()
    flash("Richiesta approvata.")
    return redirect(url_for("admin.user.director_requests"))


@user_bp.route("/director_requests/<int:req_id>/reject", methods=["POST"])
@admin_required
def reject_director_request(req_id):
    """Rifiuta richiesta di promozione a direttore"""
    req = DirectorRequest.query.get_or_404(req_id)
    req.status = DirectorRequestStatus.REJECTED.value
    db.session.commit()
    flash("Richiesta rifiutata.")
    return redirect(url_for("admin.user.director_requests"))