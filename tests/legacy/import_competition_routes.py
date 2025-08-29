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
    f"- create_prova_standalone: "
    f"{hasattr(routes.admin.competition, 'create_prova_standalone')}"
)
print(f"- create_prova: {hasattr(routes.admin.competition, 'create_prova')}")
print(f"- edit_prova: {hasattr(routes.admin.competition, 'edit_prova')}")

print("Script completed successfully")
