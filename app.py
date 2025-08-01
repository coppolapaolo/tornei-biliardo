# app.py - Clean application factory pattern
from flask import Flask, request
from flask_login import LoginManager, current_user
import os

# Import configurazioni e modelli
from config import config
from models import db, User
from utils import get_database_stats, create_admin_if_not_exists, UserPermissions


def create_app(config_name=None):
    """Factory per creare l'app Flask"""

    # Determina configurazione
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    # Crea app Flask
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Inizializza estensioni
    db.init_app(app)

    # Setup Login Manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

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
                    "username": current_user.username
                    if current_user.is_authenticated
                    else "Anonymous",
                    "is_admin": current_user.is_admin
                    if current_user.is_authenticated
                    else False,
                },
                "request_endpoint": request.endpoint,
                "request_method": request.method,
                "database_stats": get_database_stats()
                if current_user.is_authenticated
                else {},
            }
        return {"debug_info": debug_info}

    # Context processor per permissions
    @app.context_processor
    def inject_permissions():
        """Inject permission helpers into all Jinja2 templates"""
        return {
            "can_inscribe": UserPermissions.can_inscribe_to_prova(),
            "can_view_profile": UserPermissions.can_view_profile(),
            "can_delete_account": UserPermissions.can_delete_account(),
            "show_admin_management": UserPermissions.show_admin_management(),
            "show_director_management": UserPermissions.show_director_management(),
            "is_player": current_user.is_authenticated and current_user.is_player,
            "is_director": current_user.is_authenticated and current_user.is_director,
            "is_admin": current_user.is_authenticated and current_user.is_admin,
        }

    # Registra blueprints
    from routes import register_blueprints

    register_blueprints(app)

    # Inizializzazione database per applicazione normale (non testing)
    if not app.config.get("TESTING", False):
        with app.app_context():
            db.create_all()
            create_admin_if_not_exists()

    return app


# Application entry point
if __name__ == "__main__":
    app = create_app()
    debug_mode = app.config.get("DEBUG_MODE", False)
    app.run(debug=debug_mode)
