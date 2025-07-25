# routes/__init__.py - Inizializzazione package routes
from flask import Blueprint

def register_blueprints(app):
    """Registra tutti i blueprint dell'applicazione"""
    
    # Import dei blueprint
    from .main import main_bp
    from .auth import auth_bp
    from .admin import admin_bp
    from .player import player_bp
    
    # Registrazione blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(player_bp, url_prefix='/player')