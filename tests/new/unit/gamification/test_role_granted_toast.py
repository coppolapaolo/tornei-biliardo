"""Il toast di sblocco quando viene concesso un ruolo (ADR-041).

Perché non si riusa ``handle_feature_unlock_event``: la sua firma vuole una
``FeatureConfig``, e un ruolo **non è** una feature sbloccata. Fabbricarne una
fittizia significherebbe mettere nel payload un ``code`` che in
``feature_config`` non esiste — e il frontend usa proprio quel codice per
identificare la feature.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import models.gamification.frontend_bridge as bridge_module
from models.gamification.frontend_bridge import GamificationFrontendBridge
from models.user.role_enum import GrantableRole

pytestmark = pytest.mark.unit


def _capture(app, role):
    """Emette il toast dentro una richiesta e restituisce il payload."""
    captured = {}

    def _spy(event_type, data, user_id):
        captured["type"] = event_type
        captured["data"] = data
        captured["user_id"] = user_id

    with app.test_request_context("/"):
        with patch.object(
            GamificationFrontendBridge,
            "_flash_gamification_event",
            staticmethod(_spy),
        ):
            GamificationFrontendBridge.handle_role_granted_event(7, role)
    return captured


def test_granting_the_examiner_role_emits_an_unlock_toast(app):
    captured = _capture(app, GrantableRole.EXAMINER)

    assert captured["type"] == "unlock"
    assert captured["user_id"] == 7
    assert captured["data"]["icon"] == "🔓"
    assert captured["data"]["name"]
    assert captured["data"]["description"]


def test_the_payload_code_is_not_mistaken_for_a_feature(app):
    """Il codice deve dichiararsi come ruolo, non spacciarsi per una feature."""
    captured = _capture(app, GrantableRole.EXAMINER)
    code = captured["data"]["code"]

    assert code.startswith("role:")
    assert code == "role:examiner"


def test_a_plain_string_works_too(app):
    """Il chiamante può passare l'enum o il suo valore: entrambi validi."""
    assert _capture(app, "examiner")["data"]["code"] == "role:examiner"


def test_a_role_without_copy_stays_silent(app):
    """Meglio nessun toast che un toast vuoto o non tradotto."""
    assert _capture(app, "un_ruolo_futuro") == {}


def test_the_toast_is_a_no_op_outside_a_request(app):
    """Come per gli altri handler: uno script da console non deve rompersi.

    La guardia sta **prima** del corpo, perché comporre le stringhe con ``_()``
    fa già leggere la ``session`` (regressione nota di
    ``reconcile_achievements.py``).
    """

    def _explode(*args, **kwargs):
        raise RuntimeError("Working outside of request context.")

    with patch.object(bridge_module, "has_request_context", lambda: False):
        with patch.object(bridge_module, "_", _explode):
            GamificationFrontendBridge.handle_role_granted_event(
                7, GrantableRole.EXAMINER
            )  # non deve sollevare


def test_every_copy_is_anchored_for_pybabel(app):
    """Le copy passate a ``_()`` come variabile non sono estraibili.

    Servono ripetute come literal nell'ancora, altrimenti restano in italiano
    anche in EN: stesso motivo, e stesso rimedio, di ``_NUDGE_COPY``.
    """
    import inspect

    anchor = inspect.getsource(bridge_module._i18n_nudge_anchor)
    for copy in GamificationFrontendBridge._ROLE_GRANTED_COPY.values():
        for text in (copy["name"], copy["description"]):
            # L'ancora può spezzare il literal su più righe: si confronta
            # sulle parole, non sulla formattazione del sorgente.
            head = text.split(".")[0].strip()
            assert head[:40] in " ".join(anchor.split()), text
