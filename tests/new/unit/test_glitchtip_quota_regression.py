"""Regression: il SDK GlitchTip non deve campionare transaction di performance.

Il piano GlitchTip Free ha un limite di 1000 eventi/mese e le transaction
(traces) contano nel conteggio: con traces_sample_rate=0.1 la quota si
esauriva in un giorno (2026-06-10: 887/1000, proiezione 21k) e l'ingest
scartava anche gli error event. Solo gli errori vanno spediti.
"""

from unittest.mock import patch

from app import create_app
from config import config as config_map


def test_sentry_init_does_not_sample_traces():
    original_dsn = config_map["testing"].GLITCHTIP_DSN
    config_map["testing"].GLITCHTIP_DSN = "https://fake@glitchtip.example/1"
    try:
        with patch("sentry_sdk.init") as mock_init:
            create_app("testing")
        assert mock_init.call_count == 1
        kwargs = mock_init.call_args.kwargs
        assert kwargs["traces_sample_rate"] == 0.0
    finally:
        config_map["testing"].GLITCHTIP_DSN = original_dsn
