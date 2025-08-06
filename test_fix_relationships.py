#!/usr/bin/env python
"""
Quick test to verify relationship fixes
"""

import sys

def test_imports_and_relationships():
    """Test that all imports work after relationship fix"""
    print("Testing imports after relationship fix...")
    
    try:
        # Test imports
        from models import (
            db, User, Tournament, Prova, Match,
            Classification, RoundClassification, PlayerEncounter
        )
        print("✅ All imports successful")
        
        # Test creating app context
        from app import create_app
        app = create_app('testing')
        
        with app.app_context():
            # Force SQLAlchemy to configure all mappers
            db.create_all()
            
            # Try a simple query to ensure relationships are configured
            User.query.first()
            Classification.query.first()
            
            print("✅ Database schema created successfully")
            print("✅ Relationships configured correctly")
            
            # Test that relationships exist
            assert hasattr(User, 'classifications')
            assert hasattr(Classification, 'user')
            assert hasattr(Classification, 'tournament')
            
            print("✅ All relationships accessible")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_imports_and_relationships()
    sys.exit(0 if success else 1)