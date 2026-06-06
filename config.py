# config.py - Configurazioni dell'applicazione
import os


class Config:
    """Configurazione base"""

    SECRET_KEY = (
        os.environ.get("SECRET_KEY") or "your-secret-key-change-this-in-production"
    )
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL") or "sqlite:///billiard_campionato.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEBUG_MODE = os.environ.get("DEBUG_MODE", "true").lower() in ("1", "true", "yes")

    # Admin bootstrap (ENV-first)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME") or "admin"
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL") or "admin@nowhere.it"
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or "admin123"
    ADMIN_PASSWORD_REQUIRED = False

    # Email Service (SMTP)
    MAIL_SERVER = os.environ.get("MAIL_SERVER") or "smtp.gmail.com"
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or 587)
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = (
        os.environ.get("MAIL_DEFAULT_SENDER")
        or f"Campionato Biliardo <{MAIL_USERNAME}>"
    )

    # Error tracking (GlitchTip/Sentry)
    GLITCHTIP_DSN = os.environ.get("GLITCHTIP_DSN")

    # App Info
    APP_NAME = "Campionato Biliardo"
    VERSION = "1.0.0"

    # Upload configurations
    UPLOAD_BASE_PATH = "static/uploads"
    CHALLENGE_UPLOAD_FOLDER = "challenges"
    VENUE_UPLOAD_FOLDER = "venues"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

    # I18n settings
    BABEL_DEFAULT_LOCALE = "it"
    BABEL_TRANSLATION_DIRECTORIES = "translations"

    # Onboarding obbligatorio (ADR-035): quando True, gli utenti non-admin con
    # onboarding non completato vengono reindirizzati alla pagina dedicata.
    # Attivo in dev e prod; disattivato nei test (vedi TestingConfig).
    ONBOARDING_ENFORCED = True


class DevelopmentConfig(Config):
    """Configurazione per sviluppo"""

    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Configurazione per produzione"""

    DEBUG = False
    DEBUG_MODE = False  # Sempre False in produzione
    TESTING = False
    ADMIN_PASSWORD_REQUIRED = True

    # In produzione SECRET_KEY DEVE venire da env var
    SECRET_KEY = os.environ.get("SECRET_KEY") or ""

    # Secure session cookies
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # In produzione, la password admin DEVE venire dalla variabile d'ambiente
    # Nessun fallback - se non settata, l'app deve fallire
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or None


class TestingConfig(Config):
    """Configurazione per test"""

    TESTING = True
    GLITCHTIP_DSN = None
    WTF_CSRF_ENABLED = False
    # L'enforcement onboarding è opt-in nei test: la maggior parte usa utenti
    # con onboarding_completed=False e finirebbe reindirizzata. I test dedicati
    # (ADR-035) lo riattivano localmente con app.config["ONBOARDING_ENFORCED"].
    ONBOARDING_ENFORCED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_SESSION_OPTIONS = {"expire_on_commit": False}
    ADMIN_USERNAME = "admin"
    ADMIN_EMAIL = "admin@campionato.local"
    ADMIN_PASSWORD = "admin123"
    ADMIN_PASSWORD_REQUIRED = False


# Mappatura configurazioni
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
