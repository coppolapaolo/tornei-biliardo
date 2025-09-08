"""Director routes for campionato and standalone competition management."""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from functools import wraps

from app import db
from models.competition.models import Gara, WithdrawPolicy
from models.competition.services import GaraService
from models.campionato.models import Campionato, TournamentDirector


director_bp = Blueprint("director", __name__, url_prefix="/director")


def director_required(f):
    """Decorator to require director role."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_director and not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


