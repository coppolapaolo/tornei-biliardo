# routes/__init__.py - Inizializzazione package routes
def register_blueprints(app):
    """Registra tutti i blueprint dell'applicazione"""

    # Import dei blueprint core
    from .main import main_bp
    from .auth import auth_bp
    from .admin import admin_bp
    from .player import player_bp
    from .dashboard import dashboard_bp

    # Import dei blueprint extended domains (Phase 3)
    from .challenge import challenge_bp
    from .individual_match import individual_match_bp
    from .rating import rating_bp

    # Registrazione blueprints core
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(player_bp, url_prefix="/player")
    app.register_blueprint(dashboard_bp)

    # Registrazione blueprints extended domains
    app.register_blueprint(challenge_bp, url_prefix="/challenge")
    app.register_blueprint(individual_match_bp, url_prefix="/match")
    app.register_blueprint(rating_bp, url_prefix="/rating")
