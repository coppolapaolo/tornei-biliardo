"""Production endpoint allowlist (ADR-028).

Deny-by-default visibility matrix mapping Flask endpoints to user roles
allowed to see them in production. In development (DEBUG_MODE=true) this
module is pass-through: every endpoint is visible regardless of role.
Admins always bypass the matrix.

Roles: "anonimo" (not logged in), "player", "director". Admin = bypass.

Endpoint not present in ``ENDPOINT_ROLES`` and not in
``INFRASTRUCTURE_ALLOWLIST`` is visible only to admins. To expose a new
endpoint to non-admins, add an entry here. Visibility is orthogonal to
authorization (the existing decorators @login_required, @admin_required,
etc. still apply once the endpoint is reached).
"""
from __future__ import annotations

from flask import current_app


Role = str  # "anonimo" | "player" | "director"


# ---------------------------------------------------------------------------
# MVP allowlist: starting set covering registration → login → inscription →
# play → profile (for player/director) and gara/campionato creation (for
# director). All non-listed endpoints are admin-only in production.
# ---------------------------------------------------------------------------

ENDPOINT_ROLES: dict[str, set[Role]] = {
    # === Anonymous-only (not logged in) ===
    "auth.login":                                 {"anonimo"},
    "auth.register":                              {"anonimo"},
    "auth.forgot_password":                       {"anonimo"},
    "auth.reset_password":                        {"anonimo"},
    "auth.verify_email":                          {"anonimo"},

    # === Public (polymorphic: every role sees, template adapts) ===
    "main.index":                                 {"anonimo", "player", "director"},
    "main.public_garas_list":                     {"anonimo", "player", "director"},
    "main.public_campionatos_list":               {"anonimo", "player", "director"},
    "main.gara_detail_public":                    {"anonimo", "player", "director"},
    "main.campionato_detail_public":              {"anonimo", "player", "director"},
    "admin.competition.gara_detail":              {"anonimo", "player", "director"},
    "i18n.set_language":                          {"anonimo", "player", "director"},

    # === Logged-in (player or director) ===
    "auth.logout":                                {"player", "director"},
    "dashboard.dashboard":                        {"player", "director"},
    # Player-side dashboard at /player/ (the "back to dashboard" target from
    # several profile/list pages — also reached by the dashboard router).
    "player.dashboard":                           {"player", "director"},

    # Profile
    "player.profile":                             {"player", "director"},
    "player.view_profile":                        {"player", "director"},
    "player.edit_profile":                        {"player", "director"},
    "player.change_password":                     {"player", "director"},
    "player.request_verification_email":          {"player", "director"},

    # Notifications
    "player.notifications":                       {"player", "director"},
    "player.mark_notification_read":              {"player", "director"},
    "player.mark_all_notifications_read":         {"player", "director"},
    "player.delete_selected_notifications":       {"player", "director"},
    "player.update_auto_delete":                  {"player", "director"},

    # Inscriptions and play (a director can also play in someone else's gara).
    # main.public_*_list lists gare; player.gara_detail shows a gara from the
    # player's perspective (with inscription/unsubscribe controls); the
    # polymorphic admin.competition.gara_detail above shows the same gara
    # with admin/director management UI.
    "player.history":                             {"player", "director"},
    "player.gara_detail":                         {"player", "director"},
    "player.inscribe_to_gara":                    {"player", "director"},
    "player.unsubscribe_from_gara":               {"player", "director"},

    # Match scoring (player side, for matches the user is playing)
    "player.add_rack_simplified":                 {"player", "director"},
    "player.remove_rack_simplified":              {"player", "director"},
    "player.confirm_match_result":                {"player", "director"},
    "player.reject_match_result":                 {"player", "director"},
    "player.forfeit_match":                       {"player", "director"},
    "player.add_trio_rack":                       {"player", "director"},
    "player.remove_trio_rack":                    {"player", "director"},
    "player.confirm_trio_result":                 {"player", "director"},
    "player.forfeit_trio":                        {"player", "director"},

    # === Director only: campionato/gara creation and management ===
    "admin.campionato.create_campionato":         {"director"},
    "admin.campionato.edit_campionato":           {"director"},
    "admin.campionato.campionato_detail":         {"director"},
    "admin.campionato.wizard_start":              {"director"},
    "admin.campionato.wizard_create":             {"director"},
    "admin.campionato.wizard_step2":              {"director"},
    "admin.campionato.wizard_cancel":             {"director"},
    "admin.competition.create_gara_standalone":   {"director"},
    "admin.competition.create_gara":              {"director"},
    "admin.competition.edit_gara":                {"director"},
    "admin.competition.cancel_gara":              {"director"},

    # Inscription management
    "admin.competition.open_inscriptions":        {"director"},
    "admin.competition.close_inscriptions":       {"director"},
    "admin.competition.modify_inscription_dates": {"director"},
    "admin.competition.admin_inscribe_user":      {"director"},
    "admin.competition.admin_uninscribe_user":    {"director"},

    # Round management
    "admin.competition.start_first_round":        {"director"},
    "admin.competition.start_round_generic":      {"director"},
    "admin.competition.cancel_first_round":       {"director"},
    "admin.competition.cancel_current_round":     {"director"},
    "admin.competition.terminate_gara":           {"director"},
    "admin.competition.round_management_overview": {"director"},
    "admin.competition.get_round_status":         {"director"},
    "admin.competition.list_round_configs":       {"director"},
    "admin.competition.upsert_round_config":      {"director"},
    "admin.competition.delete_round_config":      {"director"},
    "admin.competition.amalfi_classification":    {"director"},
    "admin.competition.get_strategy_constraints": {"director"},
    "admin.competition.check_match_modification": {"director"},

    # Match scoring (admin side, for the director managing the gara)
    "admin.match.match_detail":                   {"director"},
    "admin.match.update_match_times":             {"director"},
    "admin.match.assign_table":                   {"director"},
    "admin.match.start_next_set":                 {"director"},
    "admin.match.add_set_rack":                   {"director"},
    "admin.match.remove_set_rack":                {"director"},
    "admin.competition.trio_add_rack":            {"director"},
    "admin.competition.trio_remove_rack":         {"director"},
    "admin.competition.trio_confirm":             {"director"},
    "admin.competition.trio_forfeit":             {"director"},

    # User listing (so a director can find players to enroll manually)
    "admin.user.users_list":                      {"director"},
    "admin.user.user_detail":                     {"director"},
}


# ---------------------------------------------------------------------------
# Infrastructure: always reachable, regardless of role. Real-time polling
# endpoints for MVP features, plus Flask built-ins. Endpoints listed here
# should still rely on @login_required for actual access control where
# applicable — this set governs only allowlist visibility, not authorization.
# ---------------------------------------------------------------------------

INFRASTRUCTURE_ALLOWLIST: set[str] = {
    "static",
    "health",
    # MVP polling
    "sse.poll_gara",
    "sse.poll_match",
    "sse.poll_trio",
    "sse.poll_user",
    # Legacy SSE streams kept for backward compat (ADR-021)
    "sse.gara_stream",
    "sse.user_stream",
    "sse.trio_stream",
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _is_production() -> bool:
    """True when the allowlist must be enforced.

    Pass-through during testing (so existing tests don't need migration) and
    in development (DEBUG_MODE=true).
    """
    if current_app.config.get("TESTING", False):
        return False
    return not current_app.config.get("DEBUG_MODE", False)


def _user_role(user) -> Role:
    """Role string for the current user, used to look up the matrix.

    Admins are handled by the bypass branch in ``is_endpoint_visible`` and
    must not reach this function.
    """
    if not user.is_authenticated:
        return "anonimo"
    if getattr(user, "is_director", False):
        return "director"
    return "player"


def is_endpoint_visible(endpoint: str | None, user) -> bool:
    """Return True if ``endpoint`` should be reachable for ``user``.

    Order of checks:
    1. ``endpoint is None``: pass-through (Flask raises 404 itself).
    2. Pass-through in dev/test (``_is_production()`` is False).
    3. ``endpoint in INFRASTRUCTURE_ALLOWLIST``: True for every role.
    4. Admin user: True (global bypass).
    5. ``user`` role is in ``ENDPOINT_ROLES[endpoint]``: True.
    6. Otherwise: False.

    Endpoints absent from ``ENDPOINT_ROLES`` (and not in infrastructure)
    are visible only to admins by default.
    """
    if endpoint is None:
        return True
    if not _is_production():
        return True
    if endpoint in INFRASTRUCTURE_ALLOWLIST:
        return True
    if user.is_authenticated and getattr(user, "is_admin", False):
        return True
    return _user_role(user) in ENDPOINT_ROLES.get(endpoint, set())
