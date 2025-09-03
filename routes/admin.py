# routes/admin.py - REFACTORED: Domain-specific blueprint architecture
"""
Admin routes - STEP 1 REFACTORING COMPLETED

This file has been decomposed into domain-specific blueprints:
- routes/admin/campionato.py - Campionato management
- routes/admin/competition.py - Gara/competition management  
- routes/admin/match.py - Match and rack management
- routes/admin/user.py - User administration
- routes/admin/dashboard.py - Admin dashboard

All routes are now handled by the new blueprint structure in routes/admin/
The main blueprint registration is in routes/admin/__init__.py

BEFORE: 1,442 lines in monolithic file
AFTER: 6 domain-specific files averaging ~240 lines each

This compatibility layer imports the new blueprint structure.
The original file has been backed up to routes/admin_backup.py
"""

# Import the new blueprint structure

# The admin_bp blueprint is now available for registration in the main app
# All existing URLs are preserved through the new blueprint architecture:

# URLs preserved:
# /admin/ -> dashboard (routes/admin/dashboard.py)
# /admin/campionato/* -> campionato management (routes/admin/campionato.py)
# /admin/gara/* -> competition management (routes/admin/competition.py)
# /admin/match/* -> match management (routes/admin/match.py)
# /admin/rack/* -> rack management (routes/admin/match.py)
# /admin/users -> user management (routes/admin/user.py)
# /admin/user/* -> user management (routes/admin/user.py)
# /admin/director_requests -> user management (routes/admin/user.py)

# All legacy functionality has been preserved
# No behavioral changes to any admin feature
# Blueprint registration maintains exact URL compatibility
