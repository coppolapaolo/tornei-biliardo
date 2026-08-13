# config.py - Configurazioni dell'applicazione
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _compute_asset_version() -> str:
    """Cache-buster derivato dal file statico modificato più di recente.

    I CSS/JS sono referenziati come `?v=<questo valore>` e in produzione sono
    serviti con cache lunga: serve quindi un valore che cambi da sé a ogni
    modifica di un asset, altrimenti i browser resterebbero con file vecchi
    in cache per un anno. `VERSION` non va bene perché è scritta a mano e
    nessuno si ricorderebbe di incrementarla dopo un ritocco al CSS.

    Si guardano solo `static/css` e `static/js`: `static/uploads` contiene le
    immagini caricate dagli utenti, non è codice e cresce senza limiti.
    Ritorna "0" se le cartelle non esistono (il caching resta corretto: il
    valore è comunque stabile).

    Si usa `st_mtime_ns` e non `getmtime()`: quest'ultimo andrebbe troncato ai
    secondi, e due modifiche allo stesso asset nello stesso secondo
    produrrebbero lo stesso cache-buster — con cache di un anno gli utenti
    resterebbero sul file vecchio senza modo di accorgersene.
    """
    latest = 0
    for folder in ("css", "js"):
        base = os.path.join(_BASE_DIR, "static", folder)
        for root, _dirs, files in os.walk(base):
            for name in files:
                try:
                    latest = max(latest, os.stat(os.path.join(root, name)).st_mtime_ns)
                except OSError:
                    continue
    return str(latest)


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

    # App Info — dichiarate qui, prima della posta, perché il mittente di
    # default le usa: dentro il corpo di una classe si vede solo ciò che è
    # già stato definito sopra.
    APP_NAME = "Tornei Biliardo"
    VERSION = "1.0.0"

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
        os.environ.get("MAIL_DEFAULT_SENDER") or f"{APP_NAME} <{MAIL_USERNAME}>"
    )

    # Error tracking (GlitchTip/Sentry)
    GLITCHTIP_DSN = os.environ.get("GLITCHTIP_DSN")

    # Google Analytics 4 (ID misurazione, formato "G-XXXXXXXXXX").
    # Non impostato = nessuno snippet renderizzato: in sviluppo e nei test il
    # traffico locale non finisce nelle statistiche di produzione.
    GA_MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID")

    # Cache-buster per CSS/JS (vedi _compute_asset_version).
    ASSET_VERSION = _compute_asset_version()

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

    # NB: la cache lunga sugli asset NON si imposta qui con
    # SEND_FILE_MAX_AGE_DEFAULT, perché quello varrebbe per tutto /static/,
    # incluse le cartelle i cui file sono referenziati senza cache-buster
    # (img/, uploads/): resterebbero bloccati nei browser per un anno.
    # La policy è in app.py, applicata solo ai prefissi versionati.

    # In produzione, la password admin DEVE venire dalla variabile d'ambiente
    # Nessun fallback - se non settata, l'app deve fallire
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or None


class TestingConfig(Config):
    """Configurazione per test"""

    TESTING = True
    GLITCHTIP_DSN = None
    GA_MEASUREMENT_ID = None
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
