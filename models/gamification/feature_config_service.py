"""Feature Config Service - Admin operations for feature gating configuration."""

from __future__ import annotations
from typing import Dict, Any, List
import logging

from models.base import db
from models.transaction.manager import transactional
from models.gamification.feature_models import FeatureConfig

logger = logging.getLogger(__name__)


class FeatureConfigService:
    """Service for creating and updating feature gating configuration."""

    @staticmethod
    @transactional(domain="gamification")
    def create_feature(
        code: str, name: str, description: str, is_active: bool
    ) -> FeatureConfig:
        """Create a new feature configuration.

        Raises:
            ValueError: If code/name empty or code already exists.
        """
        if not code or not name:
            raise ValueError("Codice e nome sono obbligatori")
        if db.session.get(FeatureConfig, code):
            raise ValueError("Codice feature già esistente")
        feature = FeatureConfig(
            code=code,
            name=name,
            description=description,
            is_active=is_active,
            rules="[]",
        )
        db.session.add(feature)
        logger.info(f"Created feature '{code}'")
        return feature

    @staticmethod
    @transactional(domain="gamification")
    def update_feature(
        code: str,
        rules: List[Dict[str, Any]],
        is_active: bool,
        name: str,
        description: str,
    ) -> FeatureConfig:
        """Update feature rules and metadata.

        Raises:
            ValueError: If feature not found or rules invalid.
        """
        feature = db.session.get(FeatureConfig, code)
        if not feature:
            raise ValueError("Feature non trovata")
        feature.set_rules(rules)
        feature.is_active = is_active
        feature.name = name
        feature.description = description
        logger.info(f"Updated feature '{code}'")
        return feature
