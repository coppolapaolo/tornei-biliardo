# app.py - Clean application factory pattern
from flask import (
    Flask,
    abort,
    render_template,
    request,
    session,
    jsonify,
    redirect,
    url_for,
)
from flask_babel import Babel, gettext as _
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


def glitchtip_before_send(event, hint):
    """Filtra gli eventi prima dell'invio a GlitchTip.

    Scarta `OSError: write error`: lo solleva uwsgi quando il client chiude
    la connessione prima che la risposta sia scritta (tipico della prima
    richiesta dopo un reload della web app). È rumore benigno che
    consumerebbe la quota GlitchTip Free (1000 eventi/mese).

    L'errore arriva per due canali distinti: come eccezione (hint con
    `exc_info`) e come record di log catturato dalla logging integration
    (evento message-only, senza `exc_info` — issue GlitchTip 5295144).
    Vanno scartati entrambi.
    """
    exc_info = hint.get("exc_info")
    if exc_info:
        exc = exc_info[1]
        if isinstance(exc, OSError) and "write error" in str(exc):
            return None
    logentry = event.get("logentry") or {}
    message = logentry.get("message") or event.get("message") or ""
    if "OSError: write error" in message:
        return None
    return event


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
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            # Integrazioni dichiarate a mano, auto-discovery spenta: di suo
            # sentry importa ~40 moduli di integrazione per scoprire quali
            # pacchetti siano installati. Su PythonAnywhere quel giro tocca
            # anche i pacchetti di sistema, e pymongo trascina un pyOpenSSL
            # incompatibile con la cryptography installata: da console (dove
            # quei pacchetti sono visibili) create_app moriva su
            # `AttributeError: module 'lib' has no attribute
            # 'X509_V_FLAG_NOTIFY_POLICY'`. Qui servono solo queste due, che
            # erano già le uniche ad attivarsi davvero.
            integrations=[FlaskIntegration(), SqlalchemyIntegration()],
            auto_enabling_integrations=False,
            # Solo error event: le transaction di performance consumano la
            # quota GlitchTip Free (1000 eventi/mese) in poche ore.
            traces_sample_rate=0.0,
            environment=config_name,
            before_send=glitchtip_before_send,
        )

    # Configura logging per debug
    if config_name == "development":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        # Abilita logging per i nostri moduli
        logging.getLogger("models.match.table_assignment_service").setLevel(
            logging.INFO
        )
        logging.getLogger("routes.admin.match").setLevel(logging.INFO)

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
                    # I due gate che decidono cosa si vede dell'area esami
                    # (US-D1): il ruolo concedibile (L1) e l'override della
                    # progressione (L2). Mostrarli qui evita di andare a
                    # indovinare quale dei due sta bloccando la schermata.
                    "is_examiner": (
                        current_user.is_examiner
                        if current_user.is_authenticated
                        else False
                    ),
                    "gamification_override": (
                        bool(current_user.gamification_override)
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
            if not hasattr(g, "unread_notifications_count"):
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

            if not hasattr(g, "_gamification_progress"):
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
        """Inject enums into all Jinja2 templates.

        `Discipline` c'e' per la stessa ragione degli altri due: un template che
        deve nominare una disciplina non deve riscriverne il valore a mano.
        Dal 2026-08 e' l'**unico** vocabolario delle discipline: il parallelo
        non dichiarato che i match individuali salvavano e' stato normalizzato
        nei dati e rimosso dal codice, quindi un elenco di opzioni costruito su
        questo enum combacia con qualunque riga.
        """
        from models.status_enum import Discipline, GaraStatus, MatchStatus

        return {
            "GaraStatus": GaraStatus,
            "MatchStatus": MatchStatus,
            "Discipline": Discipline,
        }

    # Production endpoint allowlist (ADR-028) — pass-through in dev/test.
    from utils.feature_flags import is_endpoint_visible

    @app.before_request
    def enforce_endpoint_allowlist():
        if not is_endpoint_visible(request.endpoint, current_user):
            abort(404)

    # Onboarding obbligatorio (ADR-035): finché non completato, ogni utente
    # autenticato non-admin viene reindirizzato alla pagina dedicata. Attivo in
    # dev/prod, disattivato nei test (config ONBOARDING_ENFORCED). La decisione
    # è in utils.onboarding (funzione pura, testata in isolamento).
    from utils.onboarding import needs_onboarding_redirect, ONBOARDING_ENDPOINT

    @app.before_request
    def enforce_onboarding():
        if not app.config.get("ONBOARDING_ENFORCED", True):
            return None
        if needs_onboarding_redirect(current_user, request.endpoint):
            return redirect(url_for(ONBOARDING_ENDPOINT))

    # Tracciamento attività utente (ADR-036): touch throttled di last_active_at,
    # usato per l'auto-refresh dei segnali-domanda. Skip nei test per non
    # interferire con l'isolamento della suite (commit per-richiesta).
    from utils.activity import touch_user_activity

    @app.before_request
    def track_user_activity():
        if app.config.get("TESTING", False):
            return None
        touch_user_activity(current_user)
        return None

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

    # Register demand-signal handlers (ADR-036): consume signals on gara created
    from models.demand import event_handlers as _demand_eh  # noqa: F401, F811

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
            # Seed quest personali della settimana corrente (idempotente).
            # L'avvio dell'app si ripete ~quotidianamente: ogni nuova settimana
            # ISO ottiene così le proprie quest, senza scheduler.
            from models.gamification.quest_seeds import seed_weekly_quests

            quests_created = seed_weekly_quests(db.session)
            if quests_created > 0:
                app.logger.info(f"Gamification: seeded {quests_created} weekly quests")

    # Domini necessari a Google Analytics 4. Aggiunti alla CSP solo quando il
    # tracking e' effettivamente configurato: una policy piu' larga del
    # necessario e' superficie di attacco gratuita.
    # Senza questi domini il browser blocca gtag.js e le chiamate di raccolta,
    # e GA resta a zero visite senza alcun errore visibile lato server.
    _GA_SCRIPT_SRC = "https://www.googletagmanager.com"
    _GA_IMG_SRC = "https://www.googletagmanager.com https://*.google-analytics.com"
    _GA_CONNECT_SRC = (
        "https://*.google-analytics.com "
        "https://*.analytics.google.com "
        "https://*.googletagmanager.com"
    )

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"

        ga_enabled = bool(app.config.get("GA_MEASUREMENT_ID"))
        script_src = "'self' 'unsafe-inline' cdn.jsdelivr.net code.jquery.com"
        img_src = "'self' data:"
        connect_src = "'self'"
        if ga_enabled:
            script_src += f" {_GA_SCRIPT_SRC}"
            img_src += f" {_GA_IMG_SRC}"
            connect_src += f" {_GA_CONNECT_SRC}"

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src {script_src}; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com "
            "fonts.googleapis.com; "
            "font-src cdnjs.cloudflare.com cdn.jsdelivr.net fonts.gstatic.com; "
            f"img-src {img_src}; "
            f"connect-src {connect_src}"
        )
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    # Cache lunga SOLO sugli asset che portano un cache-buster nell'URL: sono
    # CSS e JS, referenziati in base.html come `?v=ASSET_VERSION`. Modificarli
    # cambia l'URL, quindi la cache si invalida da se e un anno e' sicuro.
    #
    # Il resto di /static/ resta sul default conservativo di Flask. `img/` e
    # `uploads/` sono referenziati a percorso fisso (es. /static/img/chalk1.png
    # da gamification.js): con una cache lunga un aggiornamento non
    # raggiungerebbe piu i browser, e non ci sarebbe modo di forzarlo.
    #
    # E una whitelist e non una blacklist di proposito: una cartella nuova
    # sotto static/ e al sicuro per default, invece di ereditare in silenzio
    # una cache che non le si addice.
    @app.after_request
    def set_static_cache_policy(response):
        if request.path.startswith(("/static/css/", "/static/js/")):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    # Health check endpoint
    @app.route("/health")
    def health():
        from sqlalchemy import text

        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="healthy", version=app.config["VERSION"]), 200
        except Exception as e:
            # Non esporre str(e) nel JSON: /health è pubblico (probe anonimo) e
            # l'eccezione DB rivelerebbe path file/dettagli driver. Logga lato
            # server, restituisci un messaggio generico.
            app.logger.error(f"Health check failed: {e}")
            return jsonify(status="unhealthy"), 503

    # Custom error pages
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return render_template("errors/400.html"), 400

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        # Senza questo handler un permesso negato mostrava la pagina grezza
        # di Werkzeug: in inglese e fuori dal design. I decoratori in
        # utils/permissions.py fanno abort(403) in parecchi punti.
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if request.is_json or is_ajax:
            return jsonify({"error": _("Accesso negato")}), 403
        return render_template("errors/403.html"), 403

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
    # Porta 5001: la 5000 su macOS è occupata dal ricevitore AirPlay
    # (ControlCenter), che risponde 403 quando il dev server è giù
    app.run(debug=debug_mode, port=int(os.environ.get("PORT", "5001")))
