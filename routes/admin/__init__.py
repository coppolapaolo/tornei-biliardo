# routes/admin/__init__.py
"""Admin blueprint registration and URL mapping."""

from flask import Blueprint

# Import domain-specific blueprints
from .campionato import campionato_bp
from .competition import competition_bp
from .match import match_bp
from .user import user_bp
from .venue import venue_bp
# from .dashboard import dashboard_bp  # Removed - admin dashboard deprecated, using unified dashboard

# Main admin blueprint (parent)
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Register sub-blueprints with preserved URLs
# Campionato domain: /admin/campionato/*
admin_bp.register_blueprint(campionato_bp, url_prefix="/campionato")

# Competition domain: /admin/gara/*
admin_bp.register_blueprint(competition_bp, url_prefix="/gara")

# Match domain: /admin/match/*, /admin/rack/*
admin_bp.register_blueprint(match_bp, url_prefix="/match")

# User domain: /admin/users, /admin/user/*, /admin/director_requests
admin_bp.register_blueprint(user_bp)

# Venue domain: /admin/venues, /admin/venue/*
admin_bp.register_blueprint(venue_bp)

# Dashboard domain: /admin/ (root) - REMOVED
# admin_bp.register_blueprint(dashboard_bp)  # Deprecated - using unified dashboard

# Export the main blueprint for registration in the app
__all__ = ["admin_bp"]
