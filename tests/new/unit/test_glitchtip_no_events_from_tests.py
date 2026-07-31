"""Regression: la suite di test non deve spedire eventi al GlitchTip di prod.

`app.py` fa `load_dotenv(".envrc")` all'import, quindi il DSN di produzione
finisce in `os.environ` anche senza direnv attivo, e `Config.GLITCHTIP_DSN` lo
legge a import-time. `sentry_sdk.init()` è però globale per processo, non per
app: basta un test che crei l'app in una config non-testing (vedi
`create_app("development")` in tests/new/integration/test_admin.py) perché
l'SDK si armi con il DSN vero. Da quel momento ogni ERROR loggato dai test
successivi viene spedito, anche da quelli che girano in config `testing`
con GLITCHTIP_DSN = None.

È successo il 2026-07-28: ~20 eventi con environment `development` e
server_name `Serendipity-V-2.local`, tra cui l'InvalidToken atteso di
test_rotate_encryption_key (issue TORNEI-BILIARDO-5O). Sono eventi a carico
della quota GlitchTip Free (1000 eventi/mese), la stessa che nell'incidente
del 2026-06-10 ha fatto scartare all'ingest anche gli error event veri.

La difesa è in `conftest.py` di rootdir, che azzera GLITCHTIP_DSN prima che
`config.py` lo legga; questi test ne verificano l'invariante.
"""

import os

# L'import di `app` è quello che esegue `load_dotenv(".envrc")`: va fatto qui,
# a import-time del modulo di test, perché altrimenti l'esito dipenderebbe da
# quali altri test hanno già importato `app` nella stessa sessione.
import app  # noqa: F401
from config import config as config_map


def test_dsn_env_var_is_neutralized_during_tests():
    assert not os.environ.get(
        "GLITCHTIP_DSN"
    ), "Il conftest di rootdir deve azzerare GLITCHTIP_DSN prima di importare config"


def test_no_config_carries_a_dsn_during_tests():
    # Non solo `testing`: il leak passa da qualsiasi config usata in un test,
    # e `development`/`production` ereditano il DSN da Config.
    for name in ("development", "testing", "production"):
        assert not config_map[
            name
        ].GLITCHTIP_DSN, f"config['{name}'] ha un DSN: i test spedirebbero eventi reali"
