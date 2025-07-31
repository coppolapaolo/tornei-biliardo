"""
Models package initialization - Phase 1 Foundation

This module provides the foundation for domain-driven model organization
while maintaining backward compatibility with existing code.

Phase 1: Base infrastructure with backward compatibility
Future phases will gradually modularize models into domain-specific modules.

Author: Refactoring Phase 1  
Created: 2025-01-31
"""

# Import database instance from base module
from .base import db

# Import utility functions from base module
from .base import get_or_create, bulk_create, safe_commit, init_db, reset_db

# PHASE 1: Maintain backward compatibility by importing from existing models.py
# This temporary solution ensures all existing code continues to work
# while we build the foundation for domain separation

try:
    # Import all existing models from the root models.py file
    # This maintains 100% backward compatibility during Phase 1
    import sys
    import os
    
    # Add parent directory to path to import models.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Import from existing models.py - temporary for Phase 1
    from models import (
        User, Tournament, Prova, Inscription, Match, TrioMatch,
        Rack, MatchResult, Classification, DirectorRequest, TournamentDirector
    )
    
    # Check if there are other models we missed
    try:
        from models import Playoff
    except ImportError:
        # Playoff might not exist in current models.py
        pass
    
except ImportError as e:
    # If models.py doesn't exist or has issues, create minimal structure
    print(f"Warning: Could not import from existing models.py: {e}")
    print("Creating minimal model structure for development...")
    
    # Minimal models for development - these will be replaced in Phase 2+
    class User(db.Model):
        """Temporary minimal User model for development"""
        __tablename__ = 'user'
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(80), unique=True, nullable=False)
        email = db.Column(db.String(120), unique=True, nullable=False)
        
    class Tournament(db.Model):
        """Temporary minimal Tournament model for development"""
        __tablename__ = 'tournament'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)

# Maintain backward compatibility - all models available at package level
# This ensures existing imports like 'from models import User' continue to work

__all__ = [
    # Database and utilities
    'db', 'get_or_create', 'bulk_create', 'safe_commit', 'init_db', 'reset_db',
    
    # Models (maintaining backward compatibility)
    'User', 'Tournament', 'Prova', 'Inscription', 'Match', 'TrioMatch',
    'Rack', 'MatchResult', 'Classification', 'DirectorRequest', 'TournamentDirector'
]

# Add Playoff to __all__ if it exists
try:
    Playoff
    __all__.append('Playoff')
except NameError:
    pass

# Version info for tracking refactoring progress
__version__ = "1.1.0-phase1"
__phase__ = "Phase 1: Base Infrastructure"

# Future import structure (will be implemented in subsequent phases)
# This serves as documentation for the target architecture
"""
FUTURE STRUCTURE (Phase 2+):

# User domain
from .user.models import User, TournamentDirector, DirectorRequest

# Tournament domain  
from .tournament.models import Tournament

# Competition domain
from .competition.models import Prova, Inscription

# Match domain
from .match.models import Match, TrioMatch, Rack, MatchResult

# Classification domain
from .classification.models import Classification

# Playoff domain
from .playoff.models import Playoff
"""

def get_current_models():
    """
    Utility function to get list of all currently available models.
    Useful for debugging and migration verification.
    
    Returns:
        dict: Dictionary of model names and their classes
    """
    models = {}
    for name in __all__:
        if name not in ['db', 'get_or_create', 'bulk_create', 'safe_commit', 'init_db', 'reset_db']:
            try:
                models[name] = globals()[name]
            except KeyError:
                models[name] = None
    return models

def verify_backward_compatibility():
    """
    Verify that all expected models are available for backward compatibility.
    
    Returns:
        tuple: (success, missing_models)
    """
    expected_models = [
        'User', 'Tournament', 'Prova', 'Inscription', 'Match', 
        'TrioMatch', 'Rack', 'MatchResult', 'Classification', 
        'DirectorRequest', 'TournamentDirector'
    ]
    
    missing = []
    for model_name in expected_models:
        try:
            globals()[model_name]
        except KeyError:
            missing.append(model_name)
    
    return len(missing) == 0, missing

# Debug information (only in development)
if __name__ == "__main__":
    print(f"Models package {__version__}")
    print(f"Current phase: {__phase__}")
    print(f"Available models: {list(get_current_models().keys())}")
    
    success, missing = verify_backward_compatibility()
    if success:
        print("✅ Backward compatibility verified")
    else:
        print(f"⚠️ Missing models: {missing}")