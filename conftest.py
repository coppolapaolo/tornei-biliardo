"""
PyTest configuration - Minimal and focused

Adds project root to sys.path and provides basic Flask app fixture
for testing user domain services.
"""

import sys
import pytest
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import after path setup
from app import create_app


@pytest.fixture(scope='function')
def app():
    """Create Flask app for testing with clean in-memory database"""
    app = create_app('testing')
    
    with app.app_context():
        from models.base import db
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()