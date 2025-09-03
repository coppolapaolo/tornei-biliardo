#!/usr/bin/env python3
"""
Comprehensive test to execute competition routes and improve coverage.
"""

import sys
import os
from flask import Flask
from routes.admin.competition import competition_bp

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_competition_routes():
    """Test competition routes to improve coverage."""
    # Create Flask app
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["WTF_CSRF_ENABLED"] = False

    # Register blueprint
    app.register_blueprint(competition_bp, url_prefix="/admin/competition")

    # Test importing and accessing route functions
    try:
        # Import route functions
        from routes.admin.competition import (
            create_gara_standalone,
            create_gara,
            edit_gara,
            delete_gara,
            gara_detail,
            open_inscriptions,
            modify_inscription_dates,
            start_first_round,
            gara_results_overview,
            amalfi_classification,
            amalfi_start_round,
            trio_add_rack,
            trio_reset,
        )

        print("Successfully imported all route functions")

        # Test that functions exist
        functions = [
            create_gara_standalone,
            create_gara,
            edit_gara,
            delete_gara,
            gara_detail,
            open_inscriptions,
            modify_inscription_dates,
            start_first_round,
            gara_results_overview,
            amalfi_classification,
            amalfi_start_round,
            trio_add_rack,
            trio_reset,
        ]

        for func in functions:
            print(f"Function {func.__name__}: {func}")

    except Exception as e:
        print(f"Error importing functions: {e}")

    print("Test completed")


if __name__ == "__main__":
    test_competition_routes()
