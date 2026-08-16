"""
Migration Script: Level Based Unlocks -> ABAC Feature Configs

This script migrates the old level-based unlock configuration
    (models.gamification.config_models)
to the new ABAC FeatureConfig table.

It:
1. reads all old LevelUnlock entries (from DB or default config).
2. creates corresponding FeatureConfig entries with JSON rules.
3. deactivates old LevelUnlocks (optional, or we keep them for reference).
"""

import json
import logging
from app import create_app
from models.base import db
from models.gamification.config_models import DEFAULT_LEVEL_UNLOCKS
from models.gamification.feature_models import FeatureConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")


def migrate_level_unlocks():
    app = create_app()
    with app.app_context():
        logger.info("Starting migration of Level Unlocks to Feature Configs...")

        # 1. Get existing unlocks from DB or Defaults
        # We prefer Defaults as the source of truth for the *code* mapping
        # unless DB has custom overrides.

        # Let's use the explicit DEFAULT_LEVEL_UNLOCKS list as a base
        # (level, code, name, description)

        processed_codes = set()

        for level, code, name, description in DEFAULT_LEVEL_UNLOCKS:
            if code in processed_codes:
                continue

            logger.info(f"Migrating {code} (Level {level})...")

            # Create Rule: Level >= X
            rule_set = {
                "description": f"Requires Level {level}",
                "conditions": [{"type": "LEVEL", "operator": "gte", "value": level}],
            }

            # Serialize rules
            rules_json = json.dumps([rule_set])

            # Check if FeatureConfig exists
            feature = db.session.get(FeatureConfig, code)
            if not feature:
                feature = FeatureConfig(
                    code=code,
                    name=name,
                    description=description,
                    rules=rules_json,
                    is_active=True,
                )
                db.session.add(feature)
                logger.info(f"Created FeatureConfig for {code}")
            else:
                # Update rules only if they seem empty or legacy?
                # For safety, let's not overwrite if already exists to avoid destroying
                # custom admin configs.
                logger.info(f"FeatureConfig {code} already exists. Skipping overwrite.")

            processed_codes.add(code)

        # 2. Add New Complex Features definitions (from feature_definitions.md)
        # These might not be in the old system.

        complex_features = [
            {
                "code": "create_match_direct",
                "name": "Create Direct Match",
                "rules": [
                    {
                        "conditions": [
                            {
                                "type": "METRIC",
                                "metric": "total_matches",
                                "operator": "gte",
                                "value": 5,
                            },
                            {
                                "type": "METRIC",
                                "metric": "scores_inserted",
                                "operator": "gte",
                                "value": 1,
                            },
                        ]
                    }
                ],
            },
            {
                "code": "create_match_community",
                "name": "Create Community Match",
                "rules": [
                    {
                        "conditions": [
                            {
                                "type": "METRIC",
                                "metric": "total_matches",
                                "operator": "gte",
                                "value": 15,
                            }
                        ]
                    }
                ],
            },
            {
                "code": "manage_availability",
                "name": "Manage Availability",
                "rules": [
                    # OR logic: 3 sets
                    {"conditions": [{"type": "ROLE", "value": "VENUE_MANAGER"}]},
                    {
                        "conditions": [
                            {
                                "type": "METRIC",
                                "metric": "matches_in_location",
                                "operator": "gte",
                                "value": 20,
                            }
                        ]
                    },
                    {
                        "conditions": [
                            {
                                "type": "METRIC",
                                "metric": "tournaments_in_location",
                                "operator": "gte",
                                "value": 5,
                            }
                        ]
                    },
                ],
            },
            {
                "code": "create_campionato",
                "name": "Create Championship",
                "rules": [
                    {
                        "conditions": [
                            {"type": "ROLE", "value": "DIRECTOR"},
                            {
                                "type": "METRIC",
                                "metric": "tournaments_organized",
                                "operator": "gte",
                                "value": 3,
                            },
                        ]
                    }
                ],
            },
        ]

        for cf in complex_features:
            code = cf["code"]
            feature = db.session.get(FeatureConfig, code)
            rules_json = json.dumps(cf["rules"])

            if not feature:
                feature = FeatureConfig(
                    code=code,
                    name=cf["name"],
                    description="Complex rule migrated from system defaults",
                    rules=rules_json,
                    is_active=True,
                )
                db.session.add(feature)
                logger.info(f"Created Complex FeatureConfig for {code}")
            else:
                # Force update for complex rules ensuring we adhere to new specs
                feature.rules = rules_json
                logger.info(f"Updated Complex FeatureConfig for {code}")

        db.session.commit()
        logger.info("Migration completed successfully.")


if __name__ == "__main__":
    migrate_level_unlocks()
