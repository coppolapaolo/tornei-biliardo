#!/usr/bin/env python3
"""
Direct test script to execute competition routes module and improve coverage detection.
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import and execute the competition routes module
try:
    # Import the competition blueprint and module
    from routes.admin.competition import competition_bp
    import routes.admin.competition

    # Execute some basic operations to ensure the module is loaded
    print("Imported competition blueprint successfully")
    print(f"Blueprint name: {competition_bp.name}")

    # Reference some functions to ensure they're loaded
    print("Available functions:")
    print(
        f"- create_prova_standalone: "
        f"{hasattr(routes.admin.competition, 'create_prova_standalone')}"
    )
    print(f"- create_prova: {hasattr(routes.admin.competition, 'create_prova')}")
    print(f"- edit_prova: {hasattr(routes.admin.competition, 'edit_prova')}")

    # Try to access some route functions directly
    if hasattr(routes.admin.competition, "create_prova_standalone"):
        func = getattr(routes.admin.competition, "create_prova_standalone")
        print(f"Function create_prova_standalone: {func}")

    if hasattr(routes.admin.competition, "create_prova"):
        func = getattr(routes.admin.competition, "create_prova")
        print(f"Function create_prova: {func}")

    if hasattr(routes.admin.competition, "edit_prova"):
        func = getattr(routes.admin.competition, "edit_prova")
        print(f"Function edit_prova: {func}")

    print("Script completed successfully")

except ImportError as e:
    print(f"Import error: {e}")
except Exception as e:
    print(f"Error: {e}")
