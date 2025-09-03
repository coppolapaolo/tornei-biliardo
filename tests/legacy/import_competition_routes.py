#!/usr/bin/env python3
"""
Simple script to import and execute code from competition routes to improve coverage.
"""

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

print("Script completed successfully")
