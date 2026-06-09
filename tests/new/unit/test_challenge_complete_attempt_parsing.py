"""Regression: parsing del payload di completamento tentativo challenge.

Bug (code review 2026-06-09, HIGH correttezza) —
`routes/challenge.py:231` e `:233`:

La route complete_attempt faceva `data.get("score", type=int)` /
`data.get("passed", type=bool)`:
  - con body JSON `data` è un dict semplice → `dict.get(..., type=int)`
    solleva TypeError (kwarg non supportato), non catturato (l'except prende
    solo ValueError) → 500;
  - `MultiDict.get("passed", type=bool)` esegue bool("false") == True →
    un tentativo pass/fail FALLITO veniva registrato come PASSATO.

Il parsing è ora in `_parse_complete_attempt_payload`, testato qui.
"""

from __future__ import annotations

import pytest
from werkzeug.datastructures import MultiDict

from routes.challenge import _parse_complete_attempt_payload


@pytest.mark.unit
def test_json_dict_does_not_raise_and_parses_score():
    # Body JSON → dict semplice. Prima: dict.get(type=int) → TypeError → 500.
    score, passed, notes = _parse_complete_attempt_payload({"score": 5})
    assert score == 5
    assert passed is None
    assert notes is None


@pytest.mark.unit
def test_passed_false_string_is_false():
    # Form con passed="false". Prima: bool("false") == True → fallito = passato.
    _, passed, _ = _parse_complete_attempt_payload(MultiDict([("passed", "false")]))
    assert passed is False


@pytest.mark.unit
def test_passed_true_string_is_true():
    _, passed, _ = _parse_complete_attempt_payload(MultiDict([("passed", "true")]))
    assert passed is True


@pytest.mark.unit
def test_passed_zero_string_is_false():
    _, passed, _ = _parse_complete_attempt_payload({"passed": "0"})
    assert passed is False


@pytest.mark.unit
def test_passed_empty_string_is_none_not_false():
    # Follow-up Copilot (PR #14): il placeholder "" di un <select> NON deve
    # registrare un fallimento implicito. Valore non riconosciuto → None.
    _, passed, _ = _parse_complete_attempt_payload(MultiDict([("passed", "")]))
    assert passed is None


@pytest.mark.unit
def test_passed_unrecognized_string_is_none():
    _, passed, _ = _parse_complete_attempt_payload({"passed": "maybe"})
    assert passed is None


@pytest.mark.unit
def test_score_string_coerced_to_int():
    score, _, _ = _parse_complete_attempt_payload(MultiDict([("score", "7")]))
    assert score == 7


@pytest.mark.unit
def test_missing_fields_return_none():
    score, passed, notes = _parse_complete_attempt_payload({})
    assert score is None
    assert passed is None
    assert notes is None


@pytest.mark.unit
def test_bool_passthrough_for_json_native_bool():
    # JSON può inviare un bool nativo.
    _, passed_true, _ = _parse_complete_attempt_payload({"passed": True})
    _, passed_false, _ = _parse_complete_attempt_payload({"passed": False})
    assert passed_true is True
    assert passed_false is False
