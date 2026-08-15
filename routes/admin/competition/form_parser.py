# routes/admin/competition/form_parser.py
"""Shared form-parsing logic for gara creation / update routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import request

from models.competition.models import Gara
from models.competition.constants import (
    DEFAULT_MIN_PARTICIPANTS,
    DEFAULT_ROUNDS_COUNT,
    DEFAULT_ENTRY_FEE,
    DEFAULT_WITHDRAW_POLICY,
)
from models.matchmaking.configuration import (
    BRACKET_STRATEGIES,
    StrategyConfiguration,
    MatchmakingStrategy,
    FirstRoundPolicy,
    OddNumberPolicy,
)

# Ri-esportato: `BRACKET_STRATEGIES` vive nel dominio
# (`models/matchmaking/configuration.py`) perché la domanda "questa gara ha un
# tabellone?" se la pongono anche modelli e template. Qui resta importabile
# dove lo era prima.
__all__ = ["BRACKET_STRATEGIES", "GaraFormParser"]


def _resolve_classification_system(strategy: str, requested: str) -> str:
    """Sistema di classifica coerente con la strategia scelta.

    Sul tabellone è POSITION e basta: chiederlo all'utente per poi rifiutare
    ogni altra risposta sarebbe solo un modo di far fallire il salvataggio.
    Fuori dal tabellone POSITION non ha senso, quindi si ricade su WINS.
    """
    if strategy in BRACKET_STRATEGIES:
        return "POSITION"
    return requested if requested in ("WINS", "RACK") else "WINS"


class GaraFormParser:
    """Extract and validate gara form fields from a Flask request.

    Usage::

        parser = GaraFormParser(campionato=campionato)  # or campionato=None
        data = parser.parse()
        # data contains all kwargs ready for GaraService.create_gara()
    """

    def __init__(self, campionato: Optional[Any] = None) -> None:
        self.campionato = campionato

    def parse(self) -> Dict[str, Any]:
        """Parse the current Flask request form and return a dict of gara fields.

        Raises ValueError if strategy validation fails.
        """
        data: Dict[str, Any] = {}

        # ── Date / time ──────────────────────────────────────────
        date_str = request.form["date"]
        time_str = request.form.get("time", "20:00")
        if "T" in date_str:
            parsed_dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M")
            data["date"] = parsed_dt.date()
            data["time"] = parsed_dt.time()
        else:
            data["date"] = datetime.strptime(date_str, "%Y-%m-%d").date()
            data["time"] = datetime.strptime(time_str, "%H:%M").time()

        # ── Tables ───────────────────────────────────────────────
        tables_input = request.form.get("available_tables", "").strip()
        data["available_tables"] = (
            Gara.parse_tables_input(tables_input) if tables_input else []
        )

        # ── Basic fields ─────────────────────────────────────────
        camp = self.campionato
        default_rounds = (
            camp.default_rounds_count
            if camp and camp.default_rounds_count
            else DEFAULT_ROUNDS_COUNT
        )
        default_fee = (
            camp.default_entry_fee
            if camp and camp.default_entry_fee is not None
            else DEFAULT_ENTRY_FEE
        )

        data["description"] = request.form.get("description", "").strip()
        data["rounds_count"] = int(request.form.get("rounds_count", default_rounds))
        data["min_participants"] = int(
            request.form.get("min_participants", DEFAULT_MIN_PARTICIPANTS)
        )
        max_p = request.form.get("max_participants")
        data["max_participants"] = int(max_p) if max_p else None
        data["entry_fee"] = float(request.form.get("entry_fee", default_fee))

        # ── Game settings ────────────────────────────────────────
        data["discipline"] = request.form["discipline"]
        data["distance"] = int(request.form["distance"])
        data["is_race_to"] = "exact_number" not in request.form
        data["withdraw_policy"] = request.form.get(
            "withdraw_policy", DEFAULT_WITHDRAW_POLICY
        )

        # ── Multi-set ────────────────────────────────────────────
        data["is_multi_set"] = "is_multi_set" in request.form
        md = request.form.get("match_distance")
        data["match_distance"] = int(md) if md else None
        data["is_race_to_sets"] = "is_race_to_sets" in request.form

        # ── Handicap mode (tri-state: eredita/sì/no) ─────────────
        # Select con valori "" (eredita dal campionato) / "true" / "false".
        # Per gare standalone "" equivale a NULL → False.
        raw_handicap = request.form.get("has_handicap", "")
        if raw_handicap == "true":
            data["has_handicap"] = True
        elif raw_handicap == "false":
            data["has_handicap"] = False
        else:
            data["has_handicap"] = None  # eredita dal campionato

        # ── Strategy ─────────────────────────────────────────────
        if camp:
            data["matchmaking_strategy"] = camp.campionato_type
            default_anti = (
                camp.default_anti_rematch
                if camp.default_anti_rematch is not None
                else True
            )
            default_odd = camp.default_odd_policy or "bye"
            data["anti_rematch_enabled"] = (
                request.form.get("anti_rematch_enabled") == "on"
                if "anti_rematch_enabled" in request.form
                else default_anti
            )
            data["odd_number_policy"] = request.form.get(
                "odd_number_policy", default_odd
            )
            data["first_round_policy"] = request.form.get(
                "first_round_policy", "random"
            )
            data["classification_system"] = camp.default_classification_system or "WINS"
        else:
            data["matchmaking_strategy"] = request.form.get(
                "matchmaking_strategy", "amalfi"
            )
            data["first_round_policy"] = request.form.get(
                "first_round_policy", "random"
            )
            data["odd_number_policy"] = request.form.get("odd_number_policy", "bye")
            data["anti_rematch_enabled"] = (
                request.form.get("anti_rematch_enabled") == "on"
            )
            data["classification_system"] = request.form.get(
                "classification_system", "WINS"
            )

        # I formati a tabellone ammettono un solo sistema di classifica, quindi
        # non lo si chiede: lo si impone. Prima il parser forzava WINS/RACK, il
        # che rendeva la combinazione valida irraggiungibile e faceva fallire il
        # salvataggio di ogni gara a eliminazione diretta o doppio KO.
        data["classification_system"] = _resolve_classification_system(
            data["matchmaking_strategy"], data["classification_system"]
        )

        data.update(GaraFormParser._parse_bracket_options(data["matchmaking_strategy"]))

        # ── SSR tiebreaker ───────────────────────────────────────
        data["tiebreaker_enabled"] = request.form.get("tiebreaker_enabled") == "on"
        data["tiebreaker_until_position"] = int(
            request.form.get("tiebreaker_until_position", 3)
        )

        return data

    @staticmethod
    def _parse_bracket_options(strategy: str) -> Dict[str, Any]:
        """Opzioni che esistono solo per i formati a tabellone.

        Fuori dal tabellone vengono **azzerate** invece che ignorate: se il
        director cambia formato dopo aver spuntato la finalina, lasciare il
        flag acceso su una gara a girone significherebbe portarsi dietro una
        configurazione che nessuna schermata mostra più.
        """
        if strategy not in BRACKET_STRATEGIES:
            return {
                "separate_teammates": False,
                "third_place_match": False,
                "double_ko_rounds": None,
            }

        options: Dict[str, Any] = {
            "separate_teammates": request.form.get("separate_teammates") == "on",
            # La finalina esiste solo a eliminazione diretta: nel doppio KO il
            # terzo posto lo decide già il tabellone.
            "third_place_match": (
                request.form.get("third_place_match") == "on"
                and strategy == MatchmakingStrategy.DIRECT_ELIMINATION.value
            ),
            "seeding_rating": request.form.get("seeding_rating", "elo"),
            "double_ko_rounds": None,
        }

        if strategy == MatchmakingStrategy.DOUBLE_KNOCKOUT.value:
            raw = (request.form.get("double_ko_rounds") or "").strip()
            if raw:
                try:
                    parsed = int(raw)
                except ValueError:
                    parsed = 0
                # 0 e valori non numerici valgono "nessuna fase a gironi",
                # cioè doppio KO pieno: è il default e non va segnalato come
                # errore, il formato a gironi è una scelta esplicita.
                options["double_ko_rounds"] = parsed if parsed > 0 else None

        return options

    @staticmethod
    def validate_strategy(data: Dict[str, Any]) -> List[str]:
        """Validate strategy config. Returns error strings (empty = OK)."""
        try:
            cfg = StrategyConfiguration(
                strategy=MatchmakingStrategy(data["matchmaking_strategy"]),
                first_round_policy=FirstRoundPolicy(data["first_round_policy"]),
                odd_number_policy=OddNumberPolicy(data["odd_number_policy"]),
                anti_rematch_enabled=data.get("anti_rematch_enabled", False),
                rounds_count=data["rounds_count"],
            )
            return cfg.validate(
                distance=data["distance"], is_race_to=data["is_race_to"]
            )
        except ValueError as e:
            return [str(e)]
