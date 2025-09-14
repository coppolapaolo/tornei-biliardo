#!/usr/bin/env python3
"""
Test semplificato per verificare che i concetti base dei UC01 funzionino.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.base import db
from models import User
from models.user.role_enum import UserRole
from models.competition.services import GaraService, InscriptionService
from utils.reset_manager import ResetManager


def test_uc01_basic_functionality():
    """Test base per verificare funzionalità UC01."""
    print("🧪 Testing UC01 basic functionality...")

    app = create_app()

    with app.app_context():
        # Test 1: ResetManager functionality
        print("1. Testing ResetManager...")
        reset_manager = ResetManager()

        # Create a simple user
        admin = User(
            username="test_admin_uc01", email="test@uc01.com", role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()

        # Try to create snapshot
        result = reset_manager.save_current_state(
            "UC01_Basic_Test", "Basic test snapshot for UC01 verification"
        )

        if result["status"] == "success":
            print("✅ Snapshot creation successful")
        else:
            print(f"❌ Snapshot creation failed: {result['message']}")
            return False

        # Test 2: Basic GaraService functionality
        print("2. Testing GaraService...")
        try:
            from datetime import date, timedelta

            gara = GaraService.create_gara(
                name="UC01 Test Tournament",
                number=1,
                date=date.today() + timedelta(days=1),
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin.id,
                min_participants=4,
                rounds_count=2,
            )
            print("✅ Gara creation successful")

        except Exception as e:
            print(f"❌ Gara creation failed: {e}")
            return False

        # Test 3: Basic user services
        print("3. Testing User services...")
        try:
            from models.user.services import UserService

            player = UserService.create_user(
                username="test_player_uc01",
                email="player@uc01.com",
                password="player123",
                role="player",
            )
            print("✅ User creation successful")

        except Exception as e:
            print(f"❌ User creation failed: {e}")
            return False

        # Test 4: Inscription functionality
        print("4. Testing Inscription...")
        try:
            InscriptionService.inscribe_user(player.id, gara.id)
            print("✅ Inscription successful")

        except Exception as e:
            print(f"❌ Inscription failed: {e}")
            return False

    print("\n🎉 All UC01 basic functionality tests passed!")
    return True


def test_uc01_snapshot_creation():
    """Test creazione snapshot specifici UC01."""
    print("\n🧪 Testing UC01 snapshot creation...")

    try:
        from create_uc01_snapshots import UC01SnapshotCreator

        creator = UC01SnapshotCreator()
        print("✅ UC01SnapshotCreator initialized")

        # Test solo un snapshot per verificare
        with creator.app.app_context():
            result = creator.create_uc6_standalone_challenge_snapshot()

            if result["status"] == "success":
                print("✅ UC6 snapshot creation successful")
                return True
            else:
                print(f"❌ UC6 snapshot creation failed: {result['message']}")
                return False

    except Exception as e:
        print(f"❌ UC01 snapshot creation error: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Starting UC01 functionality verification...\n")

    # Test base functionality
    basic_success = test_uc01_basic_functionality()

    if basic_success:
        # Test snapshot creation
        snapshot_success = test_uc01_snapshot_creation()

        if snapshot_success:
            print("\n🎯 All UC01 tests completed successfully!")
            print("✅ Framework is ready for use")
        else:
            print("\n⚠️ Basic functionality works, but snapshot creation has issues")
    else:
        print("\n❌ Basic functionality tests failed")
        print("🔧 Framework needs fixes before use")
