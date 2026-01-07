# app.py - Clean application factory pattern
from flask import Flask, request, session
from flask_babel import Babel
from flask_login import LoginManager, current_user
import os
import logging

# Import configurazioni e modelli
from config import config
from models import db, User
from utils import create_admin_if_not_exists, UserPermissions
from utils.database_utils import get_database_stats

from utils.status_ui import register_status_filters

from sqlalchemy.orm import Session as SASession
from models.soft_delete import register_soft_delete_filters


def create_app(config_name=None):
    """Factory per creare l'app Flask"""

    # Determina configurazione
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    # Crea app Flask
    app = Flask(__name__)
    app.config.from_object(config[config_name])

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
        if current_user.is_authenticated and hasattr(current_user, "language") and current_user.language:
            return current_user.language
        # 3. Best match from request headers
        return request.accept_languages.best_match(["it", "en"])

    babel = Babel(app, locale_selector=get_locale)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, user_id)

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
        }

    # Context processor per enum
    @app.context_processor
    def inject_enums():
        """Inject enums into all Jinja2 templates"""
        from models.status_enum import GaraStatus

        return {
            "GaraStatus": GaraStatus,
        }

    # Filtri Jinja per status
    register_status_filters(app)

    # Register formatting filters
    from utils.jinja import (
        format_distance,
        format_score,
        format_distance_short,
        gara_display_name,
        player_name_with_forfeit,
    )

    app.jinja_env.filters["format_distance"] = format_distance
    app.jinja_env.filters["format_score"] = format_score
    app.jinja_env.filters["format_distance_short"] = format_distance_short
    app.jinja_env.filters["gara_display_name"] = gara_display_name
    app.jinja_env.filters["player_name_with_forfeit"] = player_name_with_forfeit

    # Register image path template functions
    from utils.image_paths import challenge_image_url, challenge_image_filename

    app.jinja_env.globals["challenge_image_url"] = challenge_image_url
    app.jinja_env.globals["challenge_image_filename"] = challenge_image_filename

    # Registra blueprints
    from routes import register_blueprints

    register_blueprints(app)

    # Register gamification event handlers
    # This imports the module which auto-registers handlers with EventBus
    from models.gamification import event_handlers  # noqa: F401
    # Register gamification notification handlers
    # Creates notifications for level ups, achievements, streaks, quests
    from models.gamification import notification_handlers  # noqa: F401

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

    return app


# Application entry point
if __name__ == "__main__":
    app = create_app()
    debug_mode = app.config.get("DEBUG_MODE", False)
    app.run(debug=debug_mode)
