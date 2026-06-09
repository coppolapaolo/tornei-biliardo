"""Regression (review 2026-06-09, batch 5): i18n + architettura.

- utils/status_ui: i fallback 'Sconosciuto' non erano wrappati in _() (le altre
  label sì), quindi non venivano mai tradotti.
- classification/campionato_classification: lo stack decoratori aveva DUE cache
  (@cached + @optimized_query). Il layer interno @optimized_query usava il tag
  'campionato_classification' che invalidate_campionato_cache NON pulisce →
  dati stale serviti dopo invalidazione. Rimosso il layer ridondante.
"""

import pytest


@pytest.mark.unit
def test_status_ui_unknown_fallbacks_are_translatable(app):
    """I fallback dei presenter usano _() (qui locale=it → 'Sconosciuto')."""
    from utils.status_ui import StatusPresenter

    with app.test_request_context("/"):
        # status sconosciuto → fallback tradotto (questi presenter accettano
        # una stringa di stato grezza).
        assert StatusPresenter.match("xxx")[1] == "Sconosciuto"
        assert StatusPresenter.director_request("xxx")[1] == "Sconosciuto"
        assert StatusPresenter.playoff_confirmation("xxx")[1] == "Sconosciuto"


@pytest.mark.unit
def test_campionato_classification_single_cache_layer():
    """update_campionato_classification non ha piu' il doppio layer di cache.

    Verifica che il sorgente non importi/usi piu' optimized_query nel modulo
    (il layer interno serviva dati stale perche' il suo tag non veniva
    invalidato da invalidate_campionato_cache).
    """
    import inspect
    from models.classification import campionato_classification as mod

    src = inspect.getsource(mod)
    assert "optimized_query" not in src
