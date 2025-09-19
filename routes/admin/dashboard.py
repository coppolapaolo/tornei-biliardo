# routes/admin/dashboard.py
"""Dashboard management blueprint for admin interface."""

from flask import Blueprint, redirect, url_for

from utils import admin_required

# Dashboard management blueprint
dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@admin_required
def admin_index():
    """Admin dashboard root"""
    return "Admin Dashboard - OK"


@dashboard_bp.route("/dashboard")
@admin_required
def dashboard():
    """Admin dashboard"""
    return "Admin Dashboard - OK"
