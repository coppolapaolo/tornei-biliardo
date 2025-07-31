"""
Models package initialization - Phase 1 with User Domain Integration

This module provides domain-driven model organization while maintaining
backward compatibility with existing code.

Phase 1 Status:
- ✅ Base infrastructure complete
- ✅ User domain extracted and modularized
- 🔄 Other domains pending (Phase 2+)

Author: Refactoring Phase 1  
Created: 2025-01-31
Updated: 2025-01-31 (Task 1.2)
"""

# Import database instance and utilities from base module
from .base import db, get_or_create, bulk_create, safe_commit, init_db, reset_db

# PHASE 1 COMPLETE: User domain imported from modular structure
from .user.models import User, TournamentDirector, DirectorRequest

# TEMPORARY: Import remaining models from existing models.py
# These will be modularized in subsequent phases
try:
    # Add parent directory to path to import original models.py
    import sys
    import os
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Import non-user models from existing models.py
    # We need to be careful to avoid conflicts with our new User models
    import importlib.util
    
    # Load models.py module
    models_path = os.path.join(parent_dir, 'models.py')
    if os.path.exists(models_path):
        spec = importlib.util.spec_from_file_location("legacy_models", models_path)
        legacy_models = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy_models)
        
        # Import all non-user models
        for attr_name in dir(legacy_models):
            attr = getattr(legacy_models, attr_name)
            
            # Check if it's a model class (has __tablename__ attribute)
            if (hasattr(attr, '__tablename__') and 
                attr_name not in ['User', 'TournamentDirector', 'DirectorRequest']):
                
                # Import the model
                globals()[attr_name] = attr
                
        # Import other important items from legacy models
        try:
            # Import db if it exists (though we prefer our own)
            if hasattr(legacy_models, 'db') and 'db' not in globals():
                pass  # We use our own db from base
        except:
            pass
    
    else:
        # models.py doesn't exist, create minimal models for development
        print("Warning: models.py not found, using minimal model definitions")
        
        class Tournament(db.Model):
            """Minimal Tournament model for development"""
            __tablename__ = 'tournament'
            id = db.Column(db.Integer, primary_key=True)
            name = db.Column(db.String(100), nullable=False)
            tournament_type = db.Column(db.String(50), default='Amalfi')
            without_x = db.Column(db.Boolean, default=False)
            final_playoffs = db.Column(db.Boolean, default=True)
            challenge_mode = db.Column(db.Boolean, default=False)
            is_active = db.Column(db.Boolean, default=True)
            created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
        
        class Prova(db.Model):
            """Minimal Prova model for development"""
            __tablename__ = 'prova'
            id = db.Column(db.Integer, primary_key=True)
            tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'))
            number = db.Column(db.Integer, nullable=False)
            name = db.Column(db.String(100))
            status = db.Column(db.String(20), default='setup')
        
        class Inscription(db.Model):
            """Minimal Inscription model for development"""
            __tablename__ = 'inscription'
            id = db.Column(db.Integer, primary_key=True)
            user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
            prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'))
        
        class Match(db.Model):
            """Minimal Match model for development"""
            __tablename__ = 'match'
            id = db.Column(db.Integer, primary_key=True)
            prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'))
            player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
            player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
            winner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
            status = db.Column(db.String(20), default='pending')
            player1_score = db.Column(db.Integer, default=0)
            player2_score = db.Column(db.Integer, default=0)
        
        # Add minimal models to globals
        globals().update({
            'Tournament': Tournament,
            'Prova': Prova, 
            'Inscription': Inscription,
            'Match': Match
        })

except Exception as e:
    print(f"Warning: Error importing legacy models: {e}")
    # Create minimal fallback models
    class Tournament(db.Model):
        __tablename__ = 'tournament'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)
    
    globals()['Tournament'] = Tournament

# Ensure all expected models are available for backward compatibility
EXPECTED_MODELS = [
    'User', 'Tournament', 'Prova', 'Inscription', 'Match', 
    'TournamentDirector', 'DirectorRequest'
]

# Add optional models that might exist
OPTIONAL_MODELS = [
    'TrioMatch', 'Rack', 'MatchResult', 'Classification', 'Playoff'
]

# Collect all available models
available_models = []
for model_name in EXPECTED_MODELS + OPTIONAL_MODELS:
    if model_name in globals():
        available_models.append(model_name)

# Export all available models for backward compatibility
__all__ = [
    # Database and utilities
    'db', 'get_or_create', 'bulk_create', 'safe_commit', 'init_db', 'reset_db'
] + available_models

# Phase tracking
__version__ = "1.2.0-phase1"
__phase__ = "Phase 1: User Domain Complete"

def get_current_models():
    """
    Get list of all currently available models.
    
    Returns:
        dict: Dictionary of model names and their classes
    """
    models = {}
    for name in available_models:
        try:
            models[name] = globals()[name]
        except KeyError:
            models[name] = None
    return models

def verify_user_domain():
    """
    Verify that user domain is properly integrated.
    
    Returns:
        dict: Integration status
    """
    try:
        from .user.models import User as UserDomain
        from .user import check_domain_health
        
        # Test that our modular User is being used
        current_user = globals().get('User')
        is_modular = current_user is UserDomain
        
        domain_health = check_domain_health()
        
        return {
            'status': 'success',
            'user_domain_active': is_modular,
            'domain_health': domain_health,
            'available_models': len(available_models)
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'available_models': len(available_models)
        }

def verify_backward_compatibility():
    """
    Verify that backward compatibility is maintained.
    
    Returns:
        tuple: (success, missing_models)
    """
    missing = []
    for model_name in EXPECTED_MODELS:
        if model_name not in globals():
            missing.append(model_name)
    
    return len(missing) == 0, missing

# Debug information (development only)
if __name__ == "__main__":
    print(f"Models package {__version__}")
    print(f"Current phase: {__phase__}")
    print(f"Available models: {available_models}")
    
    # Test user domain integration
    user_status = verify_user_domain()
    print(f"User domain status: {user_status}")
    
    # Test backward compatibility
    success, missing = verify_backward_compatibility()
    if success:
        print("✅ Backward compatibility verified")
    else:
        print(f"⚠️ Missing models: {missing}")