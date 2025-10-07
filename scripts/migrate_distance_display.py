#!/usr/bin/env python3
"""Script to migrate legacy distance display patterns to new format_distance filter.

Phase 6: Frontend Integration - Template Migration Automation
"""

import re
import sys
from pathlib import Path

# Pattern replacements for distance display migration
PATTERNS = [
    # Pattern 1: Standard if/else block (multi-line)
    (
        r'{%\s+if\s+(\w+)\.best_of\s+%}\s*'
        r'Al meglio di\s+{{\s*\1\.distance\s*}}\s*'
        r'{%\s+else\s+%}\s*'
        r'{{\s*\1\.distance\s*}}\s+rack esatti\s*'
        r'{%\s+endif\s+%}',
        r'{{ \1.distance_config|format_distance }}'
    ),

    # Pattern 2: Inline ternary (single line with set)
    (
        r'{%\s+set\s+distance_label\s+=\s+\(\(\'Al meglio di \'\s+~\s+(\w+)\.distance\)\s+if\s+\1\.best_of\s+else\s+\(\1\.distance\s+~\s+\' rack esatti\'\)\)\s+%}',
        r'{% set distance_label = \1.distance_config|format_distance %}'
    ),

    # Pattern 3: Parenthesized inline version
    (
        r'\(Al meglio di\s+{{\s*(\w+)\.distance\s*}}\)\s*'
        r'{%\s+else\s+%}\s*'
        r'\({{\s*\1\.distance\s*}}\s+rack esatti\)',
        r'({{ \1.distance_config|format_distance }})'
    ),
]


def migrate_file(filepath: Path, dry_run: bool = True) -> tuple[bool, int]:
    """Migrate a single template file.

    Args:
        filepath: Path to template file
        dry_run: If True, only show what would change

    Returns:
        (changed, num_replacements) tuple
    """
    content = filepath.read_text()
    original_content = content
    total_replacements = 0

    for pattern, replacement in PATTERNS:
        content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
        total_replacements += count

    if content != original_content:
        if not dry_run:
            filepath.write_text(content)
            print(f"✅ Migrated: {filepath} ({total_replacements} replacements)")
        else:
            print(f"🔍 Would migrate: {filepath} ({total_replacements} replacements)")
        return True, total_replacements

    return False, 0


def main():
    """Main migration script."""
    if len(sys.argv) > 1 and sys.argv[1] == "--apply":
        dry_run = False
        print("🚀 APPLYING MIGRATIONS (files will be modified)")
    else:
        dry_run = True
        print("🔍 DRY RUN MODE (use --apply to actually modify files)")

    print()

    # Files to migrate (from grep results)
    files_to_migrate = [
        "templates/admin/campionato_detail.html",
        "templates/admin/gara_result_overview.html",
        "templates/components/_available_garas.html",
        "templates/components/_available_proofs.html",
        "templates/components/_current_matches_dashboard.html",
        "templates/components/_current_matches.html",
        "templates/components/_director_current_matches.html",
        "templates/components/_director_my_inscriptions.html",
        "templates/components/_gara_cards.html",
        "templates/components/_match_admin_controls.html",
        "templates/components/_match_header.html",
        "templates/components/_match_info.html",
        "templates/components/_my_inscriptions_dashboard.html",
        "templates/components/_my_inscriptions.html",
        "templates/components/_round_management.html",
        "templates/components/_separated_dashboard_content.html",
        "templates/components/_unified_cards.html",
        "templates/public/garas_list.html",
    ]

    # Note: Excluding form templates that need input fields:
    # - templates/admin/gara_edit.html (form - keep as is)
    # - templates/individual_match/create_proposal.html (form - keep as is)

    base_path = Path(__file__).parent.parent
    migrated = 0
    total_replacements = 0

    for filepath_str in files_to_migrate:
        filepath = base_path / filepath_str
        if filepath.exists():
            changed, count = migrate_file(filepath, dry_run=dry_run)
            if changed:
                migrated += 1
                total_replacements += count
        else:
            print(f"⚠️  File not found: {filepath}")

    print()
    print(f"{'✅ MIGRATION COMPLETE' if not dry_run else '🔍 DRY RUN COMPLETE'}")
    print(f"Files migrated: {migrated}/{len(files_to_migrate)}")
    print(f"Total replacements: {total_replacements}")

    if dry_run:
        print()
        print("To apply changes, run: python scripts/migrate_distance_display.py --apply")


if __name__ == "__main__":
    main()
