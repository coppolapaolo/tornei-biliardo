# utils/route_helpers.py
"""
Standard response helpers for Flask route handlers.

Reduces boilerplate for common patterns:
- try/except with flash + redirect
- AJAX vs regular request detection and response formatting
"""

from typing import Any, Callable, Optional

from flask import flash, jsonify, redirect, request


def is_ajax_request() -> bool:
    """Check if the current request is an AJAX request."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def ajax_success(
    message: Optional[str] = None, data: Optional[dict[str, Any]] = None, status: int = 200
) -> tuple[Any, int]:
    """Return a standard JSON success response for AJAX requests."""
    response: dict[str, Any] = {"success": True}
    if message:
        response["message"] = message
    if data:
        response.update(data)
    return jsonify(response), status


def ajax_error(error: str, status: int = 400) -> tuple[Any, int]:
    """Return a standard JSON error response for AJAX requests."""
    return jsonify({"success": False, "error": error}), status


def handle_service_action(
    action: Callable[[], Any],
    redirect_url: str,
    success_message: str,
    error_prefix: str = "Errore",
):
    """Execute a service action with standard error handling and redirect.

    Usage:
        return handle_service_action(
            action=lambda: GaraService.open_inscriptions(gara_id, start, end),
            redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
            success_message="Iscrizioni aperte!",
        )
    """
    try:
        action()
        flash(success_message, "success")
    except ValueError as ve:
        flash(f"{error_prefix}: {str(ve)}", "error")
    except Exception as e:
        flash(f"Errore imprevisto: {str(e)}", "error")
    return redirect(redirect_url)
