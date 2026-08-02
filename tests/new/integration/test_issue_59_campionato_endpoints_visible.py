"""Regressione issue #59 — "Passa alla fase playoff" → 404 in produzione.

L'endpoint `admin.campionato.terminate_campionato` esiste ed è protetto da
`@campionato_manager_required`, ma non compariva in `ENDPOINT_ROLES`: per
ADR-028 un endpoint non listato è admin-only in produzione, quindi il POST
del director rispondeva 404 mentre il pulsante restava visibile.

Copre l'intero blocco del ciclo di vita del campionato (chiusura + fase
playoff), promosso insieme perché è un unico flusso.
"""

from __future__ import annotations

import pytest

from utils.feature_flags import ENDPOINT_ROLES, is_endpoint_visible

DIRECTOR_ENDPOINTS = [
    "admin.campionato.terminate_campionato",
    "admin.campionato.delete_campionato",
    "admin.campionato.toggle_campionato_active",
    "admin.campionato.add_director",
    "admin.campionato.remove_director",
    "admin.campionato.start_playoff",
    "admin.campionato.create_playoff_gara",
    "admin.campionato.update_playoff_min",
    "admin.campionato.playoff_add_config",
    "admin.campionato.playoff_edit_config",
    "admin.campionato.playoff_deactivate_config",
    "admin.campionato.playoff_add_player",
    "admin.campionato.playoff_remove_player",
]


class _FakeUser:
    def __init__(self, *, is_director=False, is_admin=False, is_authenticated=True):
        self.is_authenticated = is_authenticated
        self.is_director = is_director
        self.is_admin = is_admin


@pytest.mark.integration
@pytest.mark.parametrize("endpoint", DIRECTOR_ENDPOINTS)
def test_campionato_lifecycle_endpoints_visible_to_director(app, monkeypatch, endpoint):
    with app.test_request_context():
        # In test l'allowlist è pass-through: forziamo il path "produzione".
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)

        assert is_endpoint_visible(endpoint, _FakeUser(is_director=True))
        # I player non gestiscono campionati: restano fuori.
        assert not is_endpoint_visible(endpoint, _FakeUser())


@pytest.mark.integration
def test_soft_delete_campionato_stays_admin_only(app, monkeypatch):
    """`soft_delete_campionato` è `@admin_required`: set() esplicito, non
    assenza per inerzia."""
    assert ENDPOINT_ROLES["admin.campionato.soft_delete_campionato"] == set()

    with app.test_request_context():
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)

        assert not is_endpoint_visible(
            "admin.campionato.soft_delete_campionato", _FakeUser(is_director=True)
        )
        assert is_endpoint_visible(
            "admin.campionato.soft_delete_campionato", _FakeUser(is_admin=True)
        )
