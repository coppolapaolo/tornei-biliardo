#!/usr/bin/env python
"""
Generate DATABASE_SCHEMA.md from SQLAlchemy models.

This script extracts the database schema from SQLAlchemy metadata
and generates a markdown documentation file.

Usage:
    python scripts/generate_schema_docs.py

Output:
    docs/reference/DATABASE_SCHEMA.md
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Domain groupings for tables
DOMAIN_GROUPS = {
    "User & Authentication": [
        "user",
        "director_assignment",
        "director_request",
        "venue_management",
        "venue_manager_request",
        "user_privacy_setting",
        "hidden_match",
        "hidden_inscription",
        "hidden_campionato",
    ],
    "Tournament & Competition": [
        "campionato",
        "gara",
        "inscription",
        "round_configuration",
    ],
    "Match & Scoring": [
        "match",
        "rack",
        "match_result",
        "trio_match",
        "trio_rack",
        "set",
        "set_rack",
    ],
    "Classification & Rankings": [
        "classification",
        "gara_classification",
        "round_classification",
        "player_encounter",
        "leaderboard_entry",
    ],
    "Playoff & Tiebreaker": [
        "playoff_configuration",
        "playoff_qualification",
        "playoff_campionato",
        "playoff_match",
        "tiebreaker",
        "tiebreaker_configuration",
        "spot_shot",
        "rally_attempt",
    ],
    "Challenge & Exam": [
        "challenge",
        "challenge_attempt",
        "challenge_favorite",
        "gara_challenge",
        "gara_challenge_attempt",
        "gara_challenge_classification",
        "gara_bye_challenge",
        "exam",
        "exam_challenge",
        "exam_attempt",
        "exam_challenge_result",
    ],
    "Individual Match": [
        "match_proposal",
        "proposal_invitation",
        "individual_match",
        "individual_rack",
        "player_availability",
    ],
    "Rating & Handicap": [
        "player_category",
        "player_rating",
        "handicap_rule",
        "category_handicap_rule",
        "rating_handicap_rule",
    ],
    "Gamification": [
        "user_level",
        "xp_transaction",
        "achievement",
        "user_achievement",
        "streak_tracker",
        "streak_milestone",
        "quest",
        "quest_participation",
        "gamification_config",
        "level_unlock",
    ],
    "Notification": [
        "notification",
        "notification_preference",
        "notification_template",
    ],
    "Location": [
        "billiard_hall",
        "user_location_availability",
    ],
    "KPI & Analytics": [
        "kpi_daily_snapshot",
        "kpi_feature_usage",
        "kpi_milestone",
    ],
    "System": [
        "migrations_history",
    ],
}


def get_column_type_str(column) -> str:
    """Get a readable string representation of column type."""
    try:
        type_str = str(column.type)
        # Simplify common types
        type_str = type_str.replace("VARCHAR", "VARCHAR")
        return type_str
    except Exception:
        return "UNKNOWN"


def get_constraints_info(table) -> list[str]:
    """Extract constraint information from table."""
    constraints = []

    # Unique constraints
    for constraint in table.constraints:
        constraint_type = type(constraint).__name__
        if constraint_type == "UniqueConstraint":
            cols = [c.name for c in constraint.columns]
            if cols:
                constraints.append(f"UNIQUE({', '.join(cols)})")
        elif constraint_type == "CheckConstraint":
            constraints.append(f"CHECK: {constraint.sqltext}")

    return constraints


def format_table_markdown(table) -> str:
    """Format a single table as markdown."""
    lines = []
    lines.append(f"### {table.name}")
    lines.append("")
    lines.append("| Column | Type | Nullable | Key | Default | Description |")
    lines.append("|--------|------|----------|-----|---------|-------------|")

    for column in table.columns:
        # Determine key type
        key_parts = []
        if column.primary_key:
            key_parts.append("PK")
        if column.foreign_keys:
            fk_targets = [fk.target_fullname for fk in column.foreign_keys]
            key_parts.append(f"FK→{','.join(fk_targets)}")
        if column.unique and not column.primary_key:
            key_parts.append("UQ")
        key_str = ", ".join(key_parts) if key_parts else ""

        # Get default value
        default_str = ""
        if column.default is not None:
            if hasattr(column.default, "arg"):
                default_str = str(column.default.arg)
                if callable(column.default.arg):
                    default_str = "func"
            else:
                default_str = str(column.default)

        # Nullable
        nullable = "YES" if column.nullable else "NO"

        # Column type
        col_type = get_column_type_str(column)

        # Description from doc or comment
        description = ""
        if hasattr(column, "comment") and column.comment:
            description = column.comment

        lines.append(
            f"| `{column.name}` | {col_type} | {nullable} | {key_str} | {default_str} | {description} |"
        )

    # Add constraints
    constraints = get_constraints_info(table)
    if constraints:
        lines.append("")
        lines.append("**Constraints:**")
        for c in constraints:
            lines.append(f"- {c}")

    # Add foreign key details with ON DELETE behavior
    fk_details = []
    for fk in table.foreign_keys:
        on_delete = fk.ondelete if fk.ondelete else "NO ACTION"
        fk_details.append(f"- `{fk.parent.name}` → `{fk.target_fullname}` (ON DELETE {on_delete})")

    if fk_details:
        lines.append("")
        lines.append("**Foreign Keys:**")
        lines.extend(fk_details)

    lines.append("")
    return "\n".join(lines)


def generate_schema_docs():
    """Generate the database schema documentation."""
    # Import Flask app to get SQLAlchemy context
    from app import create_app
    from models import db

    app = create_app()

    with app.app_context():
        # Get all tables from metadata
        tables = {t.name: t for t in db.metadata.sorted_tables}

        # Build output
        output_lines = []
        output_lines.append("# Database Schema Reference")
        output_lines.append("")
        output_lines.append("> **Auto-generated** from SQLAlchemy models.")
        output_lines.append(f"> Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        output_lines.append(">")
        output_lines.append("> To regenerate: `python scripts/generate_schema_docs.py`")
        output_lines.append("")
        output_lines.append("---")
        output_lines.append("")

        # Table of contents
        output_lines.append("## Table of Contents")
        output_lines.append("")
        for domain_name in DOMAIN_GROUPS.keys():
            anchor = domain_name.lower().replace(" ", "-").replace("&", "")
            output_lines.append(f"- [{domain_name}](#{anchor})")
        output_lines.append("- [Other Tables](#other-tables)")
        output_lines.append("")
        output_lines.append("---")
        output_lines.append("")

        # Track which tables we've documented
        documented_tables = set()

        # Generate by domain
        for domain_name, domain_tables in DOMAIN_GROUPS.items():
            output_lines.append(f"## {domain_name}")
            output_lines.append("")

            for table_name in domain_tables:
                if table_name in tables:
                    output_lines.append(format_table_markdown(tables[table_name]))
                    documented_tables.add(table_name)

            output_lines.append("---")
            output_lines.append("")

        # Document any remaining tables not in domain groups
        remaining = set(tables.keys()) - documented_tables
        if remaining:
            output_lines.append("## Other Tables")
            output_lines.append("")
            for table_name in sorted(remaining):
                output_lines.append(format_table_markdown(tables[table_name]))
            output_lines.append("---")
            output_lines.append("")

        # Summary statistics
        output_lines.append("## Summary")
        output_lines.append("")
        output_lines.append(f"- **Total tables**: {len(tables)}")
        output_lines.append(f"- **Domains**: {len(DOMAIN_GROUPS)}")
        output_lines.append("")

        # Write to file
        output_path = project_root / "docs" / "reference" / "DATABASE_SCHEMA.md"
        output_path.parent.mkdir(exist_ok=True)
        output_path.write_text("\n".join(output_lines), encoding="utf-8")

        print(f"✅ Generated {output_path}")
        print(f"   {len(tables)} tables documented across {len(DOMAIN_GROUPS)} domains")

        return output_path


if __name__ == "__main__":
    generate_schema_docs()
