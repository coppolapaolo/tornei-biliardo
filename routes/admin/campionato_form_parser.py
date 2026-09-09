# routes/admin/campionato_form_parser.py
"""Shared form-parsing logic for campionato creation / update routes.

The "default gare settings" block (default venue / entry fee / rounds count /
odd-number policy / anti-rematch) was duplicated, with slightly different
validation, between ``wizard_create`` and ``edit_campionato``. This parser is
the single source of truth for that block so the two paths cannot drift.

It intentionally covers only the fields both routes read from ``request.form``
with the same meaning. Step-1 wizard fields (name, type, classification system,
playoff config) live in the session for the wizard and in the form for edit, so
they stay in their respective handlers.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from werkzeug.datastructures import MultiDict

from models.classification.position_points import (
    DEFAULT_POSITION_POINTS,
    serialize_points_table,
)
from models.match.break_rules import (
    DEFAULT_BREAK_RULE,
    DEFAULT_START_RULE,
    BreakRule,
    StartRule,
)
from models.matchmaking.configuration import OddNumberPolicy

_VALID_ODD_POLICIES = {
    OddNumberPolicy.NO.value,
    OddNumberPolicy.BYE.value,
    OddNumberPolicy.BYE_WITH_CHALLENGE.value,
    OddNumberPolicy.TRIO.value,
}

DEFAULT_ROUNDS_COUNT = 3


def parse_position_points(form: MultiDict) -> Optional[str]:
    """Tabella punti per posizione (US-17), o ``None`` per "usa il default".

    Il form espone una casella per ciascuna **soglia** del default — 1°, 2°,
    3°, 4°, 5°-8°, 9°-16° — e non una per posizione: è la stessa forma in cui
    la tabella è scritta nella spec, e ``points_for_position`` risolve già una
    posizione scoperta con la prima soglia che la contiene.

    Se i valori coincidono col default si salva ``None`` invece della tabella:
    un campionato che non ha configurato nulla deve continuare a **seguire** il
    default, non a portarsene dietro una copia congelata.
    """
    table: Dict[int, int] = {}
    for threshold, fallback in DEFAULT_POSITION_POINTS:
        raw = form.get(f"position_points_{threshold}")
        if raw is None or raw == "":
            table[threshold] = fallback
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = fallback
        table[threshold] = max(value, 0)

    if table == {threshold: pts for threshold, pts in DEFAULT_POSITION_POINTS}:
        return None
    return serialize_points_table(table)


class CampionatoFormParser:
    """Extract and normalise the shared 'default gare settings' form block."""

    @staticmethod
    def parse_prova(form: MultiDict) -> bool:
        """La spunta «Competizione di prova» del passo 1 (ADR-058).

        Sta qui e non nella route perché è la stessa domanda del modulo della
        gara singola (`request.form.get("is_prova") == "on"`), e la risposta
        deve avere una forma sola.
        """
        return form.get("is_prova") == "on"

    @staticmethod
    def parse_default_settings(form: MultiDict) -> Dict[str, Any]:
        """Parse the default-settings block shared by create-wizard and edit.

        Returns kwargs ready for ``TournamentService.update_campionato`` /
        ``create_campionato_with_director``:
        ``default_venue_id``, ``default_entry_fee``, ``default_rounds_count``,
        ``default_odd_policy``, ``default_anti_rematch``.

        Invalid/empty numeric inputs fall back to safe defaults rather than
        raising, so neither path can 500 on a malformed field.
        """
        raw_venue = form.get("default_venue_id")
        try:
            default_venue_id = int(raw_venue) if raw_venue else None
        except (TypeError, ValueError):
            default_venue_id = None

        raw_fee = form.get("default_entry_fee")
        try:
            default_entry_fee = float(raw_fee) if raw_fee else None
        except (TypeError, ValueError):
            default_entry_fee = None

        try:
            default_rounds_count = int(
                form.get("default_rounds_count", DEFAULT_ROUNDS_COUNT)
            )
            if default_rounds_count < 1:
                default_rounds_count = DEFAULT_ROUNDS_COUNT
        except (TypeError, ValueError):
            default_rounds_count = DEFAULT_ROUNDS_COUNT

        default_odd_policy = form.get("default_odd_policy", OddNumberPolicy.BYE.value)
        if default_odd_policy not in _VALID_ODD_POLICIES:
            default_odd_policy = OddNumberPolicy.BYE.value

        return {
            "default_venue_id": default_venue_id,
            "default_entry_fee": default_entry_fee,
            "default_rounds_count": default_rounds_count,
            "default_odd_policy": default_odd_policy,
            "default_anti_rematch": "default_anti_rematch" in form,
            # Come si comincia e chi apre poi (ADR-056). Radice della catena:
            # un valore ignoto ricade sul default del progetto — che è il
            # comportamento storico, non una scelta nuova imposta a nessuno.
            "default_start_rule": (
                StartRule.normalize(form.get("default_start_rule"))
                or DEFAULT_START_RULE
            ).value,
            "default_break_rule": (
                BreakRule.normalize(form.get("default_break_rule"))
                or DEFAULT_BREAK_RULE
            ).value,
            # Handicap mode del campionato (ereditato da gare/match). Checkbox.
            "has_handicap": "has_handicap" in form,
            # Punti per posizione delle gare a tabellone (US-17). Il campo
            # esiste solo sui campionati a tabellone; altrove resta None e la
            # colonna non viene mai letta.
            "position_points": parse_position_points(form),
        }
