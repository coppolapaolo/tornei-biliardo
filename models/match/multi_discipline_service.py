"""
Module: models/match/multi_discipline_service.py
Purpose: Service for managing multi-discipline match configurations
Requirements: SPECIFICHE.md - Multi-discipline support within matches
"""

from typing import List, Dict, Any
from ..base import db
from .models import Match
from .set_models import Set
from ..transaction.manager import transactional
from ..status_enum import Discipline


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
            raise ValueError("Match non trovato")

        if not match.supports_multi_discipline():
            raise ValueError("Match does not support multi-discipline configuration")

        if len(disciplines) < 2:
            raise ValueError("At least 2 disciplines required for rotation")

        # Query sets explicitly instead of using relationship property
        match_sets = (
            Set.query.filter_by(match_id=match.id).order_by(Set.set_number).all()
        )

        if rotation_type == "set_level":
            # Assign different disciplines to each set
            for i, match_set in enumerate(match_sets):
                discipline_index = i % len(disciplines)
                match_set.discipline = disciplines[discipline_index]
                match_set.is_multi_discipline = False  # Single discipline per set

        elif rotation_type == "rack_level":
            # Configure each set for multi-discipline rotation
            for match_set in match_sets:
                match_set.configure_multi_discipline(disciplines, "rotation")

        else:
            raise ValueError(f"Unsupported rotation type: {rotation_type}")

        # Transaction managed by @transactional decorator

    @staticmethod
    @transactional(domain="match")
    def configure_custom_disciplines(
        match_id: int, set_configurations: Dict[int, Dict[str, Any]]
    ) -> None:
        """Configure custom discipline assignments for match sets.

        Args:
            match_id: ID of the match to configure
            set_configurations: Dict mapping set number to configuration.
                I valori sono quelli di `Discipline`:
                {
                    1: {"discipline": "8_ball"},
                    2: {"multi_discipline": True,
                        "rotation": ["9_ball", "10_ball"]},
                    3: {"multi_discipline": True,
                        "assignment": {1: "8_ball", 2: "9_ball"}},
                }
        """
        match = db.session.get(Match, match_id)
        if match is None:
            raise ValueError("Match non trovato")

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
                match_set.discipline = config.get(
                    "discipline", Discipline.EIGHT_BALL.value
                )
                match_set.is_multi_discipline = False

        # Transaction managed by @transactional decorator

    @staticmethod
    def get_available_disciplines() -> List[Dict[str, str]]:
        """Elenco delle discipline disponibili, derivato dall'enum.

        Era una tabella valore/etichetta scritta a mano — di fatto un secondo
        enum non dichiarato, per giunta col vocabolario storico nei valori.
        L'etichetta vive ora su `Discipline`, tradotta.
        """
        return [
            {"value": discipline.value, "label": discipline.display_name}
            for discipline in Discipline
        ]

    @staticmethod
    def get_discipline_rules(discipline) -> Dict[str, Any]:
        """Regole di gioco della disciplina.

        Accetta un membro di `Discipline` o un valore, anche del vocabolario
        storico: `normalize` fa da ponte. Prima la mappa era indicizzata su
        `palla_*`, quindi con i dati reali (`8_ball`) **non trovava mai nulla**
        e ogni chiamata cadeva nel dizionario vuoto.

        `name` non è ripetuto qui: viene da `display_name`, ed è tradotto.
        """
        member = Discipline.normalize(discipline)
        if member is None:
            return {}

        discipline_rules: Dict[Discipline, Dict[str, Any]] = {
            Discipline.SEVEN_BALL: {
                "rack_size": 7,
                "winning_condition": "7-ball on any legal shot",
                "break_rule": "push_out_allowed",
                "foul_penalties": ["ball_in_hand"],
                "tiebreaker_type": "spot_shot",
            },
            Discipline.EIGHT_BALL: {
                "rack_size": 15,
                "winning_condition": "8-ball after group clearance",
                "break_rule": "open",
                "foul_penalties": ["ball_in_hand"],
                "tiebreaker_type": "spot_shot",
            },
            Discipline.NINE_BALL: {
                "rack_size": 9,
                "winning_condition": "9-ball on any legal shot",
                "break_rule": "push_out_allowed",
                "foul_penalties": ["ball_in_hand"],
                "tiebreaker_type": "spot_shot",
            },
            Discipline.TEN_BALL: {
                "rack_size": 10,
                "winning_condition": "10-ball called and made",
                "break_rule": "call_shot",
                "foul_penalties": ["ball_in_hand"],
                "tiebreaker_type": "spot_shot",
            },
            Discipline.STRAIGHT_POOL: {
                "rack_size": 15,
                "winning_condition": "points_based",
                "target_score": 150,
                "break_rule": "safety_break",
                "foul_penalties": ["minus_one_point"],
                "tiebreaker_type": "rally",
            },
            Discipline.ONE_POCKET: {
                "rack_size": 15,
                "winning_condition": "points_based",
                "target_score": 8,
                "break_rule": "safety_break",
                "foul_penalties": ["minus_one_point"],
                "tiebreaker_type": "rally",
            },
            Discipline.BANK_POOL: {
                "rack_size": 15,
                "winning_condition": "points_based",
                "target_score": 9,
                "break_rule": "safety_break",
                "foul_penalties": ["ball_in_hand"],
                "tiebreaker_type": "rally",
            },
            Discipline.ROTATION: {
                "rack_size": 15,
                "winning_condition": "points_based",
                "target_score": 61,
                "break_rule": "open",
                "foul_penalties": ["ball_in_hand"],
                "tiebreaker_type": "rally",
            },
        }

        rules = discipline_rules.get(member)
        if rules is None:
            return {}
        return {"name": member.display_name, **rules}

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
                "disciplines": [
                    Discipline.EIGHT_BALL.value,
                    Discipline.NINE_BALL.value,
                    Discipline.TEN_BALL.value,
                ],
            },
            "classic_rotation": {
                "name": "Classic Rotation",
                "description": "Traditional pool games rotation",
                "rotation_type": "set_level",
                "disciplines": [
                    Discipline.EIGHT_BALL.value,
                    Discipline.STRAIGHT_POOL.value,
                    Discipline.NINE_BALL.value,
                ],
            },
            "rack_by_rack": {
                "name": "Rack by Rack",
                "description": "Different discipline each rack",
                "rotation_type": "rack_level",
                "disciplines": [
                    Discipline.EIGHT_BALL.value,
                    Discipline.NINE_BALL.value,
                ],
            },
            "skill_challenge": {
                "name": "Skill Challenge",
                "description": "Comprehensive skill test",
                "rotation_type": "set_level",
                "disciplines": [
                    Discipline.EIGHT_BALL.value,
                    Discipline.NINE_BALL.value,
                    Discipline.TEN_BALL.value,
                    Discipline.STRAIGHT_POOL.value,
                ],
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
            raise ValueError("Match non trovato")

        if not match.is_multi_set:
            return {
                "is_multi_discipline": False,
                "current_discipline": getattr(
                    match, "discipline", Discipline.EIGHT_BALL.value
                ),
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
