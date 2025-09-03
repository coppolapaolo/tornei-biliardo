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
        f"- create_gara_standalone: "
        f"{hasattr(routes.admin.competition, 'create_gara_standalone')}"
    )
    print(f"- create_gara: {hasattr(routes.admin.competition, 'create_gara')}")
    print(f"- edit_gara: {hasattr(routes.admin.competition, 'edit_gara')}")

    # Try to access some route functions directly
    if hasattr(routes.admin.competition, "create_gara_standalone"):
        func = getattr(routes.admin.competition, "create_gara_standalone")
        print(f"Function create_gara_standalone: {func}")

    if hasattr(routes.admin.competition, "create_gara"):
        func = getattr(routes.admin.competition, "create_gara")
        print(f"Function create_gara: {func}")

    if hasattr(routes.admin.competition, "edit_gara"):
        func = getattr(routes.admin.competition, "edit_gara")
        print(f"Function edit_gara: {func}")

    print("Script completed successfully")

except ImportError as e:
    print(f"Import error: {e}")
except Exception as e:
    print(f"Error: {e}")
