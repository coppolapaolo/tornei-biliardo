# app.py - Clean application factory pattern
from flask import Flask, abort, render_template, request, session, jsonify
from flask_babel import Babel
from flask_login import LoginManager, current_user
import os
import logging
from dotenv import load_dotenv

load_dotenv(".envrc")  # Load environment variables from .env file

# Import configurazioni e modelli (after load_dotenv so env vars are populated)
from config import config  # noqa: E402
from models import db, User  # noqa: E402
from utils import create_admin_if_not_exists, UserPermissions  # noqa: E402
from utils.database_utils import get_database_stats, get_quick_login_users  # noqa: E402
from models.gamification.ui_helpers import GamificationUIHelper  # noqa: E402

from utils.status_ui import register_status_filters  # noqa: E402

from sqlalchemy.orm import Session as SASession  # noqa: E402
from models.soft_delete import register_soft_delete_filters  # noqa: E402


def create_app(config_name=None):
    """Factory per creare l'app Flask"""

    # Determina configurazione
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    # Crea app Flask
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Validate critical config in production
    if config_name == "production":
        if not app.config.get("SECRET_KEY"):
            raise RuntimeError("SECRET_KEY env var must be set in production")

    # GlitchTip/Sentry error tracking
    dsn = app.config.get("GLITCHTIP_DSN")
    if dsn:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,
            environment=config_name,
        )

    # Configura logging per debug
    if config_name == "development":
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        # Abilita logging per i nostri moduli
        logging.getLogger(
            'models.match.table_assignment_service'
        ).setLevel(logging.INFO)
        logging.getLogger('routes.admin.match').setLevel(logging.INFO)

    # Inizializza estensioni
    db.init_app(app)
    from models.base import mail
    if mail:
        mail.init_app(app)

    # CSRF protection
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)  # noqa: F841

    # Rate limiting
    from utils.rate_limiter import limiter
    limiter.init_app(app)

    register_soft_delete_filters(SASession)

    # Setup Login Manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    setattr(login_manager, "login_view", "auth.login")

    # Setup Babel
    def get_locale():
        # 1. Try language from session
        if "language" in session:
            return session["language"]
        # 2. Try language from user profile (if logged in)
        if (
            current_user.is_authenticated
            and hasattr(current_user, "language")
            and current_user.language
        ):
            return current_user.language
        # 3. Best match from request headers
        return request.accept_languages.best_match(["it", "en"])

    babel = Babel(app, locale_selector=get_locale)  # noqa: F841

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, user_id)
        if user and user.is_deleted:
            return None
        return user

    # Context processor per debug info
    @app.context_processor
    def inject_debug():
        """Inietta variabili debug in tutti i template"""
        debug_info = {}
        if app.config.get("DEBUG_MODE", False):
            debug_info = {
                "debug_mode": True,
                "current_user_info": {
                    "id": current_user.id if current_user.is_authenticated else None,
                    "username": (
                        current_user.username
                        if current_user.is_authenticated
                        else "Anonymous"
                    ),
                    "is_admin": (
                        current_user.is_admin
                        if current_user.is_authenticated
                        else False
                    ),
                },
                "request_endpoint": request.endpoint,
                "request_method": request.method,
                "database_stats": (
                    get_database_stats() if current_user.is_authenticated else {}
                ),
                "quick_login_users": get_quick_login_users(),
            }
        return {"debug_info": debug_info}

    # Context processor per permissions
    @app.context_processor
    def inject_permissions():
        """Inject permission helpers into all Jinja2 templates"""
        # Get unread notifications count for current user
        # Cache in Flask's g object to avoid N+1 queries during request
        unread_count = 0
        if current_user.is_authenticated:
            from flask import g
            from models.notification.models import Notification, NotificationStatus

            # Check if already computed during this request
            if not hasattr(g, 'unread_notifications_count'):
                g.unread_notifications_count = Notification.query.filter_by(
                    user_id=current_user.id, status=NotificationStatus.PENDING
                ).count()

            unread_count = g.unread_notifications_count

        return {
            "can_inscribe": UserPermissions.can_inscribe_to_gara(),
            "can_view_profile": UserPermissions.can_view_profile(),
            "can_delete_account": UserPermissions.can_delete_account(),
            "show_admin_management": UserPermissions.show_admin_management(),
            "show_director_management": UserPermissions.show_director_management(),
            "is_player": current_user.is_authenticated and current_user.is_player,
            "is_director": current_user.is_authenticated and current_user.is_director,
            "is_admin": current_user.is_authenticated and current_user.is_admin,
            "unread_notifications_count": unread_count,
            "get_locale": get_locale,
            "can_view_ratings": GamificationUIHelper.can_view_ratings(current_user),
        }

    # Context processor per gamification
    @app.context_processor
    def inject_gamification():
        """Inject gamification stats into all templates for navbar badge."""
        stats = None
        if current_user.is_authenticated:
            from flask import g
            if not hasattr(g, '_gamification_progress'):
                try:
                    from models.gamification.level_service import LevelService
                    g._gamification_progress = LevelService.get_level_progress(
                        current_user.id
                    )
                except Exception:
                    g._gamification_progress = None
            stats = (
                {"progress": g._gamification_progress}
                if g._gamification_progress
                else None
            )
        return {"gamification_context": stats}

    # Context processor per enum
    @app.context_processor
    def inject_enums():
        """Inject enums into all Jinja2 templates"""
        from models.status_enum import GaraStatus, MatchStatus

        return {
            "GaraStatus": GaraStatus,
            "MatchStatus": MatchStatus,
        }

    # Production endpoint allowlist (ADR-028) — pass-through in dev/test.
    from utils.feature_flags import is_endpoint_visible

    @app.before_request
    def enforce_endpoint_allowlist():
        if not is_endpoint_visible(request.endpoint, current_user):
            abort(404)

    @app.context_processor
    def inject_endpoint_visibility():
        def feature_visible(endpoint: str) -> bool:
            return is_endpoint_visible(endpoint, current_user)

        def url_visible(url: str) -> bool:
            """B23: True if the URL maps to an endpoint visible for the current user.

            Used to defensively gate links built from stored URLs (e.g. notification
            action_url) so we don't promote endpoints the user can't reach.
            Returns True for unparseable/external URLs (no false negatives).
            """
            if not url or not url.startswith("/"):
                return True
            try:
                adapter = app.url_map.bind("")
                endpoint, _args = adapter.match(url, method="GET")
                return is_endpoint_visible(endpoint, current_user)
            except Exception:
                return True

        return {"feature_visible": feature_visible, "url_visible": url_visible}

    # Filtri Jinja per status
    register_status_filters(app)

    # Register formatting filters
    from utils.jinja import (
        format_distance,
        format_score,
        format_distance_short,
        gara_display_name,
        player_name_with_forfeit,
        trio_config_for_distance,
    )

    app.jinja_env.filters["format_distance"] = format_distance
    app.jinja_env.filters["format_score"] = format_score
    app.jinja_env.filters["format_distance_short"] = format_distance_short
    app.jinja_env.filters["gara_display_name"] = gara_display_name
    app.jinja_env.filters["player_name_with_forfeit"] = player_name_with_forfeit
    app.jinja_env.filters["trio_config_for_distance"] = trio_config_for_distance

    # Register image path template functions
    from utils.image_paths import challenge_image_url, challenge_image_filename

    app.jinja_env.globals["challenge_image_url"] = challenge_image_url
    app.jinja_env.globals["challenge_image_filename"] = challenge_image_filename

    # Registra blueprints
    from routes import register_blueprints

    register_blueprints(app)

    # Register gamification event handlers
    # This imports the module which auto-registers handlers with EventBus
    from models.gamification import (  # noqa: F401, F811
        event_handlers as _gamification_eh,
    )
    # Register rating event handlers
    from models.rating import event_handlers as _rating_eh  # noqa: F401, F811
    # Register gamification notification handlers
    # Creates notifications for level ups, achievements, streaks, quests
    from models.gamification import notification_handlers  # noqa: F401
    # Register SSE bridge - routes domain events to SSE for real-time updates
    from routes import sse_bridge  # noqa: F401
    # Register gamification frontend bridge - pipes events to flash messages for UI
    from models.gamification import frontend_bridge  # noqa: F401

    # Inizializzazione database per applicazione normale (non testing)
    if not app.config.get("TESTING", False):
        with app.app_context():
            db.create_all()
            create_admin_if_not_exists()
            # Seed gamification achievements (idempotent)
            from models.gamification.achievement_seeds import seed_achievements
            created, skipped = seed_achievements(db.session)
            if created > 0:
                app.logger.info(f"Gamification: seeded {created} achievements")

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net code.jquery.com; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com; "
            "font-src cdnjs.cloudflare.com cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    # Health check endpoint
    @app.route("/health")
    def health():
        from sqlalchemy import text
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="healthy", version=app.config["VERSION"]), 200
        except Exception as e:
            return jsonify(status="unhealthy", error=str(e)), 503

    # Custom error pages
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return render_template("errors/400.html"), 400

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if request.is_json or is_ajax:
            return jsonify({"error": "Errore interno del server"}), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def ratelimit_error(e):
        return render_template("errors/429.html"), 429

    return app


# Application entry point
if __name__ == "__main__":
    app = create_app()
    debug_mode = app.config.get("DEBUG_MODE", False)
    app.run(debug=debug_mode)
