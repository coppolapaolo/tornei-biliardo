"""
Module: models/match/multi_discipline_service.py
Purpose: Service for managing multi-discipline match configurations
Requirements: SPECIFICHE.md - Multi-discipline support within matches
"""

from typing import List, Dict, Any
from ..base import db
from .models import Match
from .set_models import Set
from models.transaction.manager import transactional


class MultiDisciplineService:
    """Service for managing multi-discipline match configurations."""

    @staticmethod
    @transactional(domain="match")
    def configure_rotating_disciplines(
        match_id: int, disciplines: List[str], rotation_type: str = "set_level"
    ) -> None:
        """Configure rotating disciplines for a match.

        Args:
            match_id: ID of the match to configure
            disciplines: List of disciplines to rotate through
            rotation_type: 'set_level' (different discipline per set) or
                          'rack_level' (different discipline per rack)
        """
        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if not match.supports_multi_discipline():
            raise ValueError("Match does not support multi-discipline configuration")

        if len(disciplines) < 2:
            raise ValueError("At least 2 disciplines required for rotation")

        # Direct query approach: avoids lazy loading issues with SQLAlchemy relationships
        # This ensures consistent data access in transaction context
        match_sets = (
            Set.query.filter_by(match_id=match.id).order_by(Set.set_number).all()
        )

        if rotation_type == "set_level":
            # Set-level rotation: each set plays a different discipline in sequence
            # This creates variety while maintaining discipline consistency within sets
            for i, match_set in enumerate(match_sets):
                discipline_index = i % len(disciplines)
                match_set.discipline = disciplines[discipline_index]
                match_set.is_multi_discipline = False  # Single discipline per set

        elif rotation_type == "rack_level":
            # Rack-level rotation: different discipline for each rack within sets
            # This maximizes variety and skill testing across all disciplines
            for match_set in match_sets:
                match_set.configure_multi_discipline(disciplines, "rotation")

        else:
            raise ValueError(f"Unsupported rotation type: {rotation_type}")

    @staticmethod
    @transactional(domain="match")
    def configure_custom_disciplines(
        match_id: int, set_configurations: Dict[int, Dict[str, Any]]
    ) -> None:
        """Configure custom discipline assignments for match sets.

        Args:
            match_id: ID of the match to configure
            set_configurations: Dict mapping set number to configuration:
                {
                    1: {"discipline": "palla_8"},
                    2: {"multi_discipline": True, "rotation": ["palla_9", "palla_10"]},
                    3: {"multi_discipline": True, "assignment": {1: "palla_8", 2: "palla_9"}}
                }
        """
        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if not match.supports_multi_discipline():
            raise ValueError("Match does not support multi-discipline configuration")

        # Query sets explicitly instead of using relationship property
        match_sets = (
            Set.query.filter_by(match_id=match.id).order_by(Set.set_number).all()
        )

        for set_number, config in set_configurations.items():
            match_set = next(
                (s for s in match_sets if s.set_number == set_number), None
            )
            if not match_set:
                continue

            if config.get("multi_discipline"):
                if "rotation" in config:
                    match_set.configure_multi_discipline(config["rotation"], "rotation")
                elif "assignment" in config:
                    match_set.configure_multi_discipline(
                        list(set(config["assignment"].values())), "assignment"
                    )
                    match_set.set_discipline_assignment(config["assignment"])
            else:
                # Single discipline for this set
                match_set.discipline = config.get("discipline", "palla_8")
                match_set.is_multi_discipline = False

    @staticmethod
    def get_available_disciplines() -> List[Dict[str, str]]:
        """Get list of available disciplines with their display names."""
        return [
            {
                "value": "palla_8",
                "label": "8-Ball",
                "description": "Standard 8-ball pool",
            },
            {"value": "palla_9", "label": "9-Ball", "description": "9-ball rotation"},
            {
                "value": "palla_10",
                "label": "10-Ball",
                "description": "10-ball rotation",
            },
            {
                "value": "straight_pool",
                "label": "Straight Pool",
                "description": "14.1 continuous",
            },
            {
                "value": "one_pocket",
                "label": "One Pocket",
                "description": "One pocket pool",
            },
            {
                "value": "bank_pool",
                "label": "Bank Pool",
                "description": "Bank shot pool",
            },
            {
                "value": "rotation",
                "label": "Rotation",
                "description": "15-ball rotation",
            },
        ]

    @staticmethod
    def get_discipline_rules(discipline: str) -> Dict[str, Any]:
        """Get rules and configuration for a specific discipline."""
        discipline_rules = {
            "palla_8": {
                "name": "8-Ball",
                "rack_size": 15,
                "winning_condition": "8-ball after group clearance",
                "break_rule": "open",
                "foul_penalties": ["ball_in_hand"],
                "tiebreaker_type": "spot_shot",
            },
            "palla_9": {
                "name": "9-Ball",
                "rack_size": 9,
                "winning_condition": "9-ball on any legal shot",
                "break_rule": "push_out_allowed",
                "foul_penalties": ["ball_in_hand"],
                "tiebreaker_type": "spot_shot",
            },
            "palla_10": {
                "name": "10-Ball",
                "rack_size": 10,
                "winning_condition": "10-ball called and made",
                "break_rule": "call_shot",
                "foul_penalties": ["ball_in_hand"],
                "tiebreaker_type": "spot_shot",
            },
            "straight_pool": {
                "name": "Straight Pool",
                "rack_size": 15,
                "winning_condition": "points_based",
                "target_score": 150,
                "break_rule": "safety_break",
                "foul_penalties": ["minus_one_point"],
                "tiebreaker_type": "rally",
            },
        }

        return discipline_rules.get(discipline, {})

    @staticmethod
    def validate_discipline_configuration(config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a multi-discipline configuration.

        Returns:
            Dict with 'valid' boolean and 'errors' list
        """
        errors = []

        # Check for required fields
        if "match_id" not in config:
            errors.append("match_id is required")

        # Validate disciplines
        if "disciplines" in config:
            available = [
                d["value"] for d in MultiDisciplineService.get_available_disciplines()
            ]
            for discipline in config["disciplines"]:
                if discipline not in available:
                    errors.append(f"Invalid discipline: {discipline}")

        # Check for conflicts
        if "rotation_type" in config and config["rotation_type"] not in [
            "set_level",
            "rack_level",
        ]:
            errors.append("rotation_type must be 'set_level' or 'rack_level'")

        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def create_preset_configuration(preset_name: str) -> Dict[str, Any]:
        """Create a preset multi-discipline configuration.

        Args:
            preset_name: Name of the preset configuration

        Returns:
            Configuration dictionary
        """
        presets = {
            "pool_variety": {
                "name": "Pool Variety",
                "description": "Rotate through different pool disciplines",
                "rotation_type": "set_level",
                "disciplines": ["palla_8", "palla_9", "palla_10"],
            },
            "classic_rotation": {
                "name": "Classic Rotation",
                "description": "Traditional pool games rotation",
                "rotation_type": "set_level",
                "disciplines": ["palla_8", "straight_pool", "palla_9"],
            },
            "rack_by_rack": {
                "name": "Rack by Rack",
                "description": "Different discipline each rack",
                "rotation_type": "rack_level",
                "disciplines": ["palla_8", "palla_9"],
            },
            "skill_challenge": {
                "name": "Skill Challenge",
                "description": "Comprehensive skill test",
                "rotation_type": "set_level",
                "disciplines": ["palla_8", "palla_9", "palla_10", "straight_pool"],
            },
        }

        if preset_name not in presets:
            raise ValueError(f"Unknown preset: {preset_name}")

        return presets[preset_name]

    @staticmethod
    def get_match_discipline_progress(match_id: int) -> Dict[str, Any]:
        """Get progress summary for a multi-discipline match."""
        match = db.session.get(Match, match_id)
        if match is None:
            from flask import abort

            abort(404)

        if not match.is_multi_set:
            return {
                "is_multi_discipline": False,
                "current_discipline": getattr(match, "discipline", "palla_8"),
                "progress": "Single discipline match",
            }

        current_set = match.get_current_set()
        discipline_summary = match.get_multi_discipline_summary()

        # Query sets explicitly instead of using relationship property
        match_sets = (
            Set.query.filter_by(match_id=match.id).order_by(Set.set_number).all()
        )

        progress_info = {
            "is_multi_discipline": discipline_summary["is_multi_discipline"],
            "total_sets": len(match_sets),
            "completed_sets": len([s for s in match_sets if s.is_completed()]),
            "current_set": current_set.set_number if current_set else None,
            "disciplines_used": discipline_summary["disciplines_used"],
            "sets_summary": [],
        }

        for match_set in match_sets:
            set_info = {
                "set_number": match_set.set_number,
                "status": match_set.status,
                "discipline": match_set.discipline,
                "is_multi_discipline": match_set.is_multi_discipline,
            }

            if current_set and match_set.set_number == current_set.set_number:
                if match_set.is_multi_discipline:
                    next_rack = len(match_set.racks) + 1
                    set_info["next_rack_discipline"] = (
                        match_set.get_discipline_for_rack(next_rack)
                    )
                else:
                    set_info["current_discipline"] = match_set.discipline

            progress_info["sets_summary"].append(set_info)

        return progress_info
