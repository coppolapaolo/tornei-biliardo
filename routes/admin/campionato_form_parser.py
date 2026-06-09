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

from typing import Any, Dict

from werkzeug.datastructures import MultiDict

from models.matchmaking.configuration import OddNumberPolicy

_VALID_ODD_POLICIES = {
    OddNumberPolicy.NO.value,
    OddNumberPolicy.BYE.value,
    OddNumberPolicy.BYE_WITH_CHALLENGE.value,
    OddNumberPolicy.TRIO.value,
}

DEFAULT_ROUNDS_COUNT = 3


class CampionatoFormParser:
    """Extract and normalise the shared 'default gare settings' form block."""

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
            # Handicap mode del campionato (ereditato da gare/match). Checkbox.
            "has_handicap": "has_handicap" in form,
        }
