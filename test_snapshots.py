#!/usr/bin/env python3
"""
Script di test per verificare il funzionamento degli snapshot.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from utils.reset_manager import ResetManager


def test_snapshots():
    """Test del sistema di snapshot"""
    app = create_app()
    reset_manager = ResetManager()

    with app.app_context():
        print("=== Test Sistema Snapshot ===\n")

        # Lista opzioni disponibili
        options = reset_manager.get_reset_options()
        print(f"Opzioni di reset disponibili: {len(options)}")
        for key, option in options.items():
            print(
                f"  - {key}: {option['name']} ({'eliminabile' if option['deletable'] else 'predefinito'})"
            )

        # Test caricamento di uno snapshot (se ce ne sono)
        snapshots = [k for k, v in options.items() if v["deletable"]]
        if snapshots:
            print(f"\n=== Test Caricamento Snapshot ===")
            test_snapshot = snapshots[0]
            print(f"Testing snapshot: {test_snapshot}")

            try:
                result = reset_manager.restore_snapshot(test_snapshot)
                print(f"Result: {result}")
            except Exception as e:
                print(f"Errore nel caricamento: {e}")

        # Test reset base
        print(f"\n=== Test Reset Base ===")
        try:
            result = reset_manager.reset_base()
            print(f"Reset base result: {result['status']}")
        except Exception as e:
            print(f"Errore nel reset base: {e}")


if __name__ == "__main__":
    test_snapshots()
