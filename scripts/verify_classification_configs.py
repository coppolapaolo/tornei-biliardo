#!/usr/bin/env python3
"""Verify classification system configurations for all gare.

This script checks all existing gare against the validation rules defined in
models/competition/validators.py and reports any invalid configurations.

Usage:
    python scripts/verify_classification_configs.py [--fix]

Options:
    --fix   Attempt to fix invalid configurations (interactive)
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from models.base import db
from models.competition.models import Gara
from models.competition.validators import validate_gara, ClassificationSystem


def verify_all_gare(fix_mode: bool = False) -> tuple[int, int, int]:
    """Verify all gare configurations.

    Returns:
        Tuple of (total, valid, invalid) counts
    """
    gare = Gara.query.all()
    total = len(gare)
    valid = 0
    invalid = 0

    print(f"\n{'='*60}")
    print(f"Verifying {total} gare...")
    print(f"{'='*60}\n")

    invalid_gare = []

    for gara in gare:
        # Determine classification system
        if gara.classification_system:
            try:
                class_sys = ClassificationSystem(gara.classification_system)
            except ValueError:
                class_sys = ClassificationSystem.WINS
        else:
            class_sys = ClassificationSystem.WINS

        errors, warnings = validate_gara(gara, classification_system=class_sys)

        if errors:
            invalid += 1
            invalid_gare.append((gara, errors, warnings))
            print(f"❌ Gara {gara.id}: {gara.name or f'Gara #{gara.number}'}")
            print(
                f"   Config: strategy={gara.matchmaking_strategy}, "
                f"odd={gara.odd_number_policy}, "
                f"class={gara.classification_system}"
            )
            for error in errors:
                print(f"   ERROR: {error}")
            if warnings:
                for warning in warnings:
                    print(f"   WARNING: {warning}")
            print()
        else:
            valid += 1
            if warnings:
                print(f"⚠️  Gara {gara.id}: {gara.name or f'Gara #{gara.number}'}")
                for warning in warnings:
                    print(f"   WARNING: {warning}")

    print(f"\n{'='*60}")
    print(f"Results: {valid} valid, {invalid} invalid out of {total} gare")
    print(f"{'='*60}\n")

    if fix_mode and invalid_gare:
        print("Fix mode enabled. Attempting to fix invalid configurations...\n")
        for gara, errors, _ in invalid_gare:
            fix_gara(gara, errors)

    return total, valid, invalid


def fix_gara(gara: Gara, errors: list[str]) -> None:
    """Attempt to fix an invalid gara configuration.

    Common fixes:
    - RACK + bye -> bye_with_challenge
    - Missing classification_system -> WINS
    """
    print(f"Fixing Gara {gara.id}: {gara.name or f'Gara #{gara.number}'}")

    changes = []

    # Fix: RACK + bye semplice -> bye_with_challenge
    if gara.classification_system == "RACK" and gara.odd_number_policy == "bye":
        gara.odd_number_policy = "bye_with_challenge"
        changes.append("odd_number_policy: bye -> bye_with_challenge")

    # Fix: Missing classification_system -> WINS
    if not gara.classification_system:
        gara.classification_system = "WINS"
        changes.append("classification_system: NULL -> WINS")

    if changes:
        print(f"   Changes: {', '.join(changes)}")
        try:
            db.session.commit()
            print("   ✅ Fixed successfully")
        except Exception as e:
            db.session.rollback()
            print(f"   ❌ Failed to fix: {e}")
    else:
        print("   ⚠️  No automatic fix available")
    print()


def verify_campionati() -> None:
    """Verify campionato configurations."""
    from models.campionato.models import Campionato

    campionati = Campionato.query.all()
    print(f"\n{'='*60}")
    print(f"Verifying {len(campionati)} campionati...")
    print(f"{'='*60}\n")

    for camp in campionati:
        class_sys = camp.default_classification_system or "WINS"
        odd_policy = camp.default_odd_policy or "bye"

        # Check compatibility
        issues = []
        if class_sys == "RACK" and odd_policy == "bye":
            issues.append("RACK + bye semplice non compatibili")

        if issues:
            print(f"⚠️  Campionato {camp.id}: {camp.name}")
            print(f"   Config: class={class_sys}, odd={odd_policy}")
            for issue in issues:
                print(f"   ISSUE: {issue}")
        else:
            print(f"✅ Campionato {camp.id}: {camp.name} (class={class_sys})")

    print()


def main():
    fix_mode = "--fix" in sys.argv

    # Use default config to access the real database
    app = create_app()
    with app.app_context():
        # Verify gare
        total, valid, invalid = verify_all_gare(fix_mode)

        # Verify campionati
        verify_campionati()

        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Gare: {valid}/{total} valid")
        if invalid > 0:
            print(f"⚠️  {invalid} gare need attention")
            if not fix_mode:
                print("   Run with --fix to attempt automatic fixes")
        else:
            print("✅ All configurations are valid!")
        print()

        return 0 if invalid == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
