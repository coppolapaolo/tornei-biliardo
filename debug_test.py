import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.user.services import UserService
from models.user.models import User
from models import db
from models.transaction.manager import transaction_manager
from sqlalchemy import func

def debug_test():
    app = create_app('testing')
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Check if tables exist
        from sqlalchemy import text
        result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        print("Tables in database:")
        for row in result:
            print(f"  {row[0]}")
        
        # Check transaction state
        print(f"\nInitial transaction state: {db.session.is_active}")
        
        # Create a user using raw SQLAlchemy to avoid transaction conflicts
        print("\nCreating user with raw SQLAlchemy...")
        try:
            user = User(username="getbyemail", email="getbyemail@example.com", role="player")
            user.set_password("password123")
            db.session.add(user)
            db.session.flush()  # Flush to get the ID without committing
            print(f"Created user: {user.id}, {user.username}, {user.email}")
            
            # Check if user exists in database
            all_users = db.session.query(User).all()
            print(f"\nAll users in DB (with filter): {len(all_users)}")
            for u in all_users:
                print(f"  User: {u.id}, {u.username}, {u.email}, deleted: {u.deleted_at}")
            
            # Try to retrieve user by email using UserService
            print("\nRetrieving user by email using UserService...")
            retrieved_user = UserService.get_user_by_email("getbyemail@example.com")
            print(f"Retrieved user: {retrieved_user}")
            if retrieved_user:
                print(f"  User: {retrieved_user.id}, {retrieved_user.username}, {retrieved_user.email}")
            else:
                print("  User not found!")
                
            # Try our fixed implementation directly
            print("\nTesting fixed implementation...")
            from models.user.services import _user_service_instance
            fixed_user = _user_service_instance.get_user_by_email("getbyemail@example.com")
            print(f"Fixed implementation result: {fixed_user}")
            if fixed_user:
                print(f"  User: {fixed_user.id}, {fixed_user.username}, {fixed_user.email}")
                
            # Check if soft delete filter is working
            print(f"\nUser deleted_at: {user.deleted_at}")
            print(f"User is_deleted: {user.is_deleted}")
            
            # Check the actual SQL query being generated
            print("\nChecking SQL queries...")
            from sqlalchemy import text
            result = db.session.execute(text("SELECT * FROM user")).fetchall()
            print(f"All users in DB (raw SQL): {len(result)}")
            for row in result:
                print(f"  Row: {row}")
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    debug_test()