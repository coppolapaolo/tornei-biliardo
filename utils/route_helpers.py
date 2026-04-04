# utils/route_helpers.py
"""
Standard response helpers for Flask route handlers.

Reduces boilerplate for common patterns:
- try/except with flash + redirect
- AJAX vs regular request detection and response formatting
"""

import logging
from typing import Any, Callable, Optional

from flask import abort, flash, jsonify, make_response, redirect, request

from models.base import db

logger = logging.getLogger(__name__)

_GENERIC_ERROR = "Errore interno del server"


def get_or_ajax_404(model_class: type, entity_id: int, entity_name: str = "Risorsa") -> Any:
    """Fetch an entity by PK or abort with a JSON 404 response (for AJAX routes).

    Usage:
        match = get_or_ajax_404(Match, match_id, "Match")
    """
    entity = db.session.get(model_class, entity_id)
    if entity is None:
        abort(make_response(
            jsonify({"success": False, "error": f"{entity_name} non trovato/a"}), 404
        ))
    return entity


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


def handle_ajax_service_action(
    action: Callable[[], Any],
    redirect_url: str,
    success_message: str,
    error_prefix: Optional[str] = "Errore",
):
    """Execute a service action with AJAX-aware error handling.

    For AJAX/JSON requests: returns JSON response.
    For regular requests: flashes message and redirects.

    If the action returns a dict, its contents are merged into
    the JSON success response (useful for returning IDs, etc.).

    Args:
        action: Callable to execute. May return a dict for AJAX response data.
        redirect_url: URL to redirect to (non-AJAX requests).
        success_message: Message for flash (non-AJAX) or JSON (AJAX).
        error_prefix: Prefix for business error messages.
            Use None to flash the raw error message without prefix.

    Usage:
        return handle_ajax_service_action(
            action=lambda: ChallengeService.delete_challenge(challenge_id),
            redirect_url=url_for("challenge.challenge_catalog"),
            success_message="Challenge eliminata con successo",
        )
    """
    is_json = is_ajax_request() or request.is_json
    try:
        result = action()
        if is_json:
            data = result if isinstance(result, dict) else None
            return ajax_success(message=success_message, data=data)
        flash(success_message, "success")
    except (ValueError, PermissionError) as e:
        msg = f"{error_prefix}: {e}" if error_prefix else str(e)
        if is_json:
            return ajax_error(msg)
        flash(msg, "error")
    except Exception as e:
        logger.error("Unexpected error in AJAX service action: %s", e, exc_info=True)
        if is_json:
            return ajax_error(_GENERIC_ERROR, status=500)
        flash(_GENERIC_ERROR, "error")
    return redirect(redirect_url)


def handle_service_action(
    action: Callable[[], Any],
    redirect_url: str,
    success_message: str,
    error_prefix: Optional[str] = "Errore",
):
    """Execute a service action with standard error handling and redirect.

    Catches ValueError and PermissionError as expected business errors,
    and Exception as unexpected errors.

    Args:
        action: Callable to execute (typically a service method call).
        redirect_url: URL to redirect to after success or error.
        success_message: Flash message on success.
        error_prefix: Prefix for business error messages.
            Use None to flash the raw error message without prefix.

    Usage:
        return handle_service_action(
            action=lambda: InscriptionService.open_inscriptions(gara_id, start, end),
            redirect_url=url_for("admin.competition.gara_detail", gara_id=gara_id),
            success_message="Iscrizioni aperte!",
        )
    """
    try:
        action()
        flash(success_message, "success")
    except (ValueError, PermissionError) as e:
        msg = f"{error_prefix}: {e}" if error_prefix else str(e)
        flash(msg, "error")
    except Exception as e:
        logger.error("Unexpected error in service action: %s", e, exc_info=True)
        flash(_GENERIC_ERROR, "error")
    return redirect(redirect_url)


def safe_json_error(e: Exception, context: str = "") -> tuple[Any, int]:
    """Log an unexpected exception and return a generic JSON 500 response.

    Use this in inline except Exception blocks that return jsonify.

    Args:
        e: The caught exception
        context: Optional context string for the log message

    Usage:
        except Exception as e:
            return safe_json_error(e, "adding rack")
    """
    log_msg = f"Unexpected error{f' ({context})' if context else ''}: {e}"
    logger.error(log_msg, exc_info=True)
    return jsonify({"error": _GENERIC_ERROR}), 500
