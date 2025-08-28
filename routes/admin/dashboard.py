# routes/admin/dashboard.py
"""Dashboard management blueprint for admin interface."""

from flask import Blueprint, redirect, url_for

from utils import admin_required

# Dashboard management blueprint
dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@admin_required
def dashboard():
    """Redirect to main dashboard"""
    return redirect(url_for("dashboard.dashboard"))
