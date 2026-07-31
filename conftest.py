# conftest.py - configurazione globale della sessione pytest.
"""Neutralizza il DSN GlitchTip prima che `config.py` lo legga.

`app.py` fa `load_dotenv(".envrc")` all'import, quindi il DSN di produzione
entra in `os.environ` non appena un test importa `app` — anche senza direnv
attivo nella shell. `Config.GLITCHTIP_DSN` lo legge a import-time e
`sentry_sdk.init()` è globale per processo, non per app: basta un test che
crei l'app in una config non-testing (`create_app("development")` in
tests/new/integration/test_admin.py) perché l'SDK si armi con il DSN vero.
Da lì in poi ogni ERROR loggato dai test successivi viene spedito, inclusi
quelli in config `testing` dove GLITCHTIP_DSN è già None.

Successo il 2026-07-28: ~20 eventi con environment `development` e
server_name `Serendipity-V-2.local` (issue TORNEI-BILIARDO-5O e vicini),
a carico della quota GlitchTip Free (1000 eventi/mese) — la stessa che
nell'incidente del 2026-06-10 ha fatto scartare all'ingest gli errori veri.

Sta nella rootdir perché deve girare prima di ogni import di `app`/`config`:
pytest carica i conftest della rootdir all'avvio della sessione, prima della
collection dei moduli di test. `load_dotenv` non sovrascrive le chiavi già
presenti in `os.environ` (override=False di default), quindi la stringa
vuota impostata qui resiste all'import di `app`.

Invariante verificata da tests/new/unit/test_glitchtip_no_events_from_tests.py.
"""

import os

os.environ["GLITCHTIP_DSN"] = ""
