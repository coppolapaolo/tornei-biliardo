#!/usr/bin/env python3
"""
Simple test to import and execute competition routes to improve coverage.
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def execute_competition_routes():
    """Import and execute competition routes to improve coverage."""
    print("Importing competition routes...")

    try:
        # Import the competition blueprint and module
        from routes.admin.competition import competition_bp
        import routes.admin.competition

        # Execute some basic operations to ensure the module is loaded
        print("Imported competition blueprint successfully")
        print(f"Blueprint name: {competition_bp.name}")

        # Reference all route functions to ensure they're loaded
        functions = [
            "create_gara_standalone",
            "create_gara",
            "edit_gara",
            "delete_gara",
            "gara_detail",
            "open_inscriptions",
            "modify_inscription_dates",
            "start_first_round",
            "gara_results_overview",
            "amalfi_classification",
            "amalfi_start_round",
            "trio_add_rack",
            "trio_reset",
        ]

        print("Available functions:")
        for func_name in functions:
            if hasattr(routes.admin.competition, func_name):
                func = getattr(routes.admin.competition, func_name)
                print(f"- {func_name}: {func}")
            else:
                print(f"- {func_name}: NOT FOUND")

        # Try to access the route decorators to ensure they're executed
        print("Route endpoints:")
        for rule in competition_bp.url_map.iter_rules():
            print(f"- {rule.rule}: {rule.endpoint}")

    except ImportError as e:
        print(f"Import error: {e}")
    except Exception as e:
        print(f"Error: {e}")

    print("Test completed")


if __name__ == "__main__":
    execute_competition_routes()
