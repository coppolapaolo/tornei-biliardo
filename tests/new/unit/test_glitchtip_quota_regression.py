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
    # Il DSN si inietta sovrascrivendo `environment_settings()`, non
    # l'attributo di classe: da quando `create_app` rilegge l'ambiente dopo
    # `from_object` (docstring di `Config`), è quel dizionario a vincere.
    testing = config_map["testing"]
    con_dsn = dict(
        testing.environment_settings(),
        GLITCHTIP_DSN="https://fake@glitchtip.example/1",
    )

    with patch.object(
        testing, "environment_settings", classmethod(lambda cls: dict(con_dsn))
    ):
        with patch("sentry_sdk.init") as mock_init:
            create_app("testing")

    assert mock_init.call_count == 1
    assert mock_init.call_args.kwargs["traces_sample_rate"] == 0.0
