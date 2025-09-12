#!/usr/bin/env python3
"""
Debug script to check user permissions and challenge ownership
"""

from app import create_app
from models import db, Challenge, User
from flask_login import current_user

def debug_permissions():
    """Debug challenge permissions."""
    app = create_app()
    
    with app.app_context():
        # Get all users
        users = User.query.all()
        print("=== USERS ===")
        for user in users:
            print(f"ID: {user.id}, Username: {user.username}, Role: {user.role}")
            print(f"  is_admin: {user.is_admin}")
            print(f"  is_director: {user.is_director}")
            print()
        
        # Get all challenges
        challenges = Challenge.query.all()
        print("=== CHALLENGES ===")
        for challenge in challenges:
            creator = User.query.get(challenge.created_by_id) if challenge.created_by_id else None
            print(f"ID: {challenge.id}, Name: {challenge.get_display_name()}")
            print(f"  Created by ID: {challenge.created_by_id}")
            print(f"  Created by: {creator.username if creator else 'Sistema'}")
            print(f"  Is active: {challenge.is_active}")
            print()

if __name__ == "__main__":
    debug_permissions()