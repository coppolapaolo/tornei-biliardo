# config.py - Configurazioni dell'applicazione
import os


class Config:
    """Configurazione base"""

    SECRET_KEY = (
        os.environ.get("SECRET_KEY") or "your-secret-key-change-this-in-production"
    )
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL") or "sqlite:///billiard_tournament.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() in ("1", "true", "yes")

    # Admin bootstrap (ENV-first)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
    ADMIN_PASSWORD_REQUIRED = False

    # App Info
    APP_NAME = "Torneo Biliardo"
    VERSION = "1.0.0"


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


class TestingConfig(Config):
    """Configurazione per test"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_SESSION_OPTIONS = {"expire_on_commit": False}
    ADMIN_USERNAME = "admin"
    ADMIN_EMAIL = "admin@tournament.local"
    ADMIN_PASSWORD = "admin123"
    ADMIN_PASSWORD_REQUIRED = False


# Mappatura configurazioni
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
