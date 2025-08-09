# config.py - Configurazioni dell'applicazione
import os
from datetime import datetime

class Config:
    """Configurazione base"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///billiard_tournament.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Debug Mode - Cambia qui per attivare/disattivare
    DEBUG_MODE = True
    
    # App Info
    APP_NAME = 'Torneo Biliardo'
    VERSION = '1.0.0'
    
class DevelopmentConfig(Config):
    """Configurazione per sviluppo"""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Configurazione per produzione"""
    DEBUG = False
    DEBUG_MODE = False  # Sempre False in produzione
    TESTING = False

class TestingConfig(Config):
    """Configurazione per test"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_SESSION_OPTIONS = {"expire_on_commit": False}

# Mappatura configurazioni
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}