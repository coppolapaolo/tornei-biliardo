# amalfi/__init__.py - Sistema Abbinamenti Amalfi

"""
Sistema Amalfi per abbinamenti automatici tornei biliardo.

Funzionalità principali:
- Algoritmo salto dinamico per turni successivi
- Anti-reincontro intelligente  
- Gestione X vs Trii automatica
- Classifiche real-time
"""

from .engine import (
    AmalfiEngine,
    create_amalfi_round_matches,
    get_amalfi_classification,
    validate_amalfi_configuration
)

__version__ = "1.0.0"
__all__ = [
    'AmalfiEngine',
    'create_amalfi_round_matches', 
    'get_amalfi_classification',
    'validate_amalfi_configuration'
]