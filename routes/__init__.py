# routes/__init__.py - Inizializzazione package routes
def register_blueprints(app):
    """Registra tutti i blueprint dell'applicazione"""

    # Import dei blueprint core
    from .main import main_bp
    from .auth import auth_bp
    from .admin import admin_bp
    from .player import player_bp
    from .dashboard import dashboard_bp
    from .i18n import i18n_bp
    from .onboarding import onboarding_bp
    from .demand import demand_bp
    from .help import help_bp
    from .role_grant import role_grant_bp

    # Import dei blueprint extended domains (Phase 3)
    from .challenge import challenge_bp
    from .exam import exam_bp
    from .individual_match import individual_match_bp

    # Import gamification blueprint (Phase 4)
    from .gamification import gamification_bp

    # Import SSE blueprint for real-time updates
    from .sse import sse_bp

    # Registrazione blueprints core
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(player_bp, url_prefix="/player")
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(i18n_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(demand_bp, url_prefix="/demand")
    # Il prefisso /aiuto lo dichiara il blueprint stesso.
    app.register_blueprint(help_bp)
    # Ruoli concedibili (ADR-041): prefix /roles, non /admin — le richieste
    # le processano anche i titolari non-admin.
    app.register_blueprint(role_grant_bp)

    # Registrazione blueprints extended domains
    app.register_blueprint(challenge_bp, url_prefix="/challenges")
    # Esami (ADR-042): un esame è una sequenza di drill, ma vive per conto suo —
    # ha un ciclo di vita, degli esaminatori e degli appuntamenti che il
    # catalogo challenge non ha.
    app.register_blueprint(exam_bp, url_prefix="/exam")
    app.register_blueprint(individual_match_bp, url_prefix="/match")

    # Registrazione gamification blueprint
    app.register_blueprint(gamification_bp)

    # Registrazione SSE blueprint
    app.register_blueprint(sse_bp)
