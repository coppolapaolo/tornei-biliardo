"""Guard i18n per le copy dei nudge (ADR-031 / review #10).

Le copy di ``_NUDGE_COPY`` vengono tradotte a emission-time con ``_(variabile)``,
che pybabel non estrae staticamente: per questo esiste ``_i18n_nudge_anchor`` che
ripete i literal dentro ``_()``. Questo test impedisce il *drift*: se una copy
cambia (o se ne aggiunge una) senza aggiornare l'ancora, la stringa resterebbe
non tradotta in EN senza alcun errore a runtime. Qui falliamo subito.
"""

import ast
import inspect

from models.gamification.frontend_bridge import (
    GamificationFrontendBridge,
    _i18n_nudge_anchor,
)


def _string_constants(func) -> set:
    tree = ast.parse(inspect.getsource(func))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_all_nudge_copy_strings_are_anchored_for_i18n():
    copy_strings = set()
    for entry in GamificationFrontendBridge._NUDGE_COPY.values():
        copy_strings.add(entry["name"])
        copy_strings.add(entry["description"])

    anchored = _string_constants(_i18n_nudge_anchor)

    missing = copy_strings - anchored
    assert not missing, (
        "Copy dei nudge non ancorate in _i18n_nudge_anchor (resterebbero non "
        f"tradotte in EN): {sorted(missing)}"
    )
