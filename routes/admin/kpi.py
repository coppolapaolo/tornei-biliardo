"""
Module: routes/admin/kpi.py
Purpose: Admin KPI dashboard routes
"""

from datetime import date, datetime
from typing import Optional

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from flask_babel import _

from utils import admin_required
from models.kpi import KpiService, DateRange, KpiNotificationService

kpi_bp = Blueprint("kpi", __name__)


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse date string from form input (YYYY-MM-DD)."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _get_date_range_from_request() -> tuple[Optional[DateRange], Optional[int], bool]:
    """Parse date range from request parameters.

    Returns: (date_range, days_preset, is_custom)
    """
    # Check for custom date range first
    start_date = _parse_date(request.args.get("start_date"))
    end_date = _parse_date(request.args.get("end_date"))

    if start_date is not None or end_date is not None:
        # Custom range - at least one date specified
        return DateRange.custom(start_date, end_date), None, True

    # Fall back to preset days
    days = request.args.get("days", 30, type=int)
    if days not in [1, 7, 30, 90]:
        days = 30
    return DateRange.last_n_days(days), days, False


@kpi_bp.route("/")
@login_required
@admin_required
def index():
    """KPI dashboard main page."""
    tab = request.args.get("tab", "overview")

    # Get date range (preset or custom)
    date_range, days, is_custom = _get_date_range_from_request()

    # Get data based on active tab
    context = {
        "active_tab": tab,
        "days": days,
        "date_range": date_range,
        "is_custom": is_custom,
        "start_date": (
            date_range.start.strftime("%Y-%m-%d")
            if date_range and date_range.start
            else ""
        ),
        "end_date": (
            date_range.end.strftime("%Y-%m-%d") if date_range and date_range.end else ""
        ),
    }

    if tab == "overview":
        context["metrics"] = KpiService.get_overview_metrics(date_range)
        context["daily_users"] = KpiService.get_daily_registrations(date_range)
        context["daily_matches"] = KpiService.get_daily_matches(date_range)

    elif tab == "acquisition":
        context["total_users"] = KpiService.get_total_users()
        context["new_users"] = KpiService.get_new_users_trend(date_range)
        context["daily_registrations"] = KpiService.get_daily_registrations(date_range)

    elif tab == "retention":
        context["dau"] = KpiService.get_dau()
        context["wau"] = KpiService.get_wau()
        context["mau"] = KpiService.get_mau()
        context["retention_7d"] = KpiService.get_retention_rate(7)
        context["retention_30d"] = KpiService.get_retention_rate(30)
        context["dormant_users"] = KpiService.get_dormant_users_count()

    elif tab == "engagement":
        context["total_matches"] = KpiService.get_total_matches()
        context["matches"] = KpiService.get_matches_trend(date_range)
        context["active_gare"] = KpiService.get_active_gare_count()
        context["completed_gare"] = KpiService.get_completed_gare_count(date_range)
        context["avg_level"] = KpiService.get_avg_user_level()
        context["xp_awarded"] = KpiService.get_total_xp_in_period(date_range)
        context["matches_per_user"] = KpiService.get_matches_per_active_user(date_range)
        context["daily_matches"] = KpiService.get_daily_matches(date_range)

    elif tab == "features":
        context["feature_usage"] = KpiService.get_feature_usage(date_range)

    elif tab == "business":
        context["directors"] = KpiService.get_director_performance()
        context["community"] = KpiService.get_community_health()
        context["power_users"] = KpiService.get_power_users()

    return render_template("admin/kpi.html", **context)


@kpi_bp.route("/api/overview")
@login_required
@admin_required
def api_overview():
    """API endpoint for overview data (AJAX)."""
    days = request.args.get("days", 30, type=int)
    date_range = DateRange.last_n_days(days)

    metrics = KpiService.get_overview_metrics(date_range)

    # Convert MetricWithTrend to dict
    return jsonify(
        {
            "success": True,
            "data": {
                "total_users": metrics["total_users"],
                "new_users": {
                    "current": metrics["new_users"].current,
                    "previous": metrics["new_users"].previous,
                    "trend_percent": metrics["new_users"].trend_percent,
                    "trend_direction": metrics["new_users"].trend_direction,
                },
                "matches_played": {
                    "current": metrics["matches_played"].current,
                    "previous": metrics["matches_played"].previous,
                    "trend_percent": metrics["matches_played"].trend_percent,
                    "trend_direction": metrics["matches_played"].trend_direction,
                },
                "active_gare": metrics["active_gare"],
                "activation_rate": metrics["activation_rate"],
                "mau": metrics["mau"],
            },
        }
    )


@kpi_bp.route("/api/chart-data")
@login_required
@admin_required
def api_chart_data():
    """API endpoint for chart data (AJAX)."""
    days = request.args.get("days", 30, type=int)
    chart_type = request.args.get("type", "registrations")
    date_range = DateRange.last_n_days(days)

    if chart_type == "registrations":
        data = KpiService.get_daily_registrations(date_range)
    elif chart_type == "matches":
        data = KpiService.get_daily_matches(date_range)
    else:
        data = []

    return jsonify({"success": True, "data": data})


@kpi_bp.route("/api/feature-usage")
@login_required
@admin_required
def api_feature_usage():
    """API endpoint for feature usage data (AJAX)."""
    days = request.args.get("days", 30, type=int)
    date_range = DateRange.last_n_days(days)

    data = KpiService.get_feature_usage(date_range)

    return jsonify({"success": True, "data": data})


@kpi_bp.route("/api/check-alerts")
@login_required
@admin_required
def api_check_alerts():
    """API endpoint to check for activity alerts."""
    alerts = KpiService.check_activity_alerts()

    alert_messages = []
    for alert in alerts:
        if alert.value == "no_match_3_days":
            alert_messages.append(
                {
                    "type": "warning",
                    "message": _("Nessun match giocato negli ultimi 3 giorni"),
                }
            )
        elif alert.value == "no_match_7_days":
            alert_messages.append(
                {
                    "type": "danger",
                    "message": _("Nessun match giocato negli ultimi 7 giorni"),
                }
            )
        elif alert.value == "no_registration_7_days":
            alert_messages.append(
                {
                    "type": "warning",
                    "message": _("Nessuna nuova registrazione negli ultimi 7 giorni"),
                }
            )

    return jsonify({"success": True, "alerts": alert_messages})


@kpi_bp.route("/api/check-milestones", methods=["POST"])
@login_required
@admin_required
def api_check_milestones():
    """API endpoint to check and record new milestones."""
    newly_reached = KpiService.check_and_record_milestones()

    # Send notifications for new milestones
    if newly_reached:
        KpiNotificationService.notify_milestones_batch(newly_reached)

    milestone_messages = []
    for milestone_type, value in newly_reached:
        if milestone_type.value == "users_total":
            milestone_messages.append(
                {
                    "type": "success",
                    "message": _("Milestone raggiunta: %(value)s utenti!", value=value),
                }
            )
        elif milestone_type.value == "matches_total":
            milestone_messages.append(
                {
                    "type": "success",
                    "message": _(
                        "Milestone raggiunta: %(value)s match giocati!", value=value
                    ),
                }
            )
        elif milestone_type.value == "gare_completed":
            milestone_messages.append(
                {
                    "type": "success",
                    "message": _(
                        "Milestone raggiunta: %(value)s gare completate!", value=value
                    ),
                }
            )

    return jsonify({"success": True, "milestones": milestone_messages})
