# routes/admin/__init__.py
"""Admin blueprint registration and URL mapping."""

from flask import Blueprint

# Import domain-specific blueprints
from .tournament import tournament_bp
from .competition import competition_bp
from .match import match_bp
from .user import user_bp
from .dashboard import dashboard_bp

# Main admin blueprint (parent)
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Register sub-blueprints with preserved URLs
# Tournament domain: /admin/tournament/*
admin_bp.register_blueprint(tournament_bp, url_prefix="/tournament")

# Competition domain: /admin/prova/*
admin_bp.register_blueprint(competition_bp, url_prefix="/prova")

# Match domain: /admin/match/*, /admin/rack/*
admin_bp.register_blueprint(match_bp, url_prefix="/match")

# User domain: /admin/users, /admin/user/*, /admin/director_requests
admin_bp.register_blueprint(user_bp)

# Dashboard domain: /admin/ (root)
admin_bp.register_blueprint(dashboard_bp)

# Export the main blueprint for registration in the app
__all__ = ["admin_bp"]
