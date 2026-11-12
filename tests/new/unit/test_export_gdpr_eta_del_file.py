"""L'età di un file di export si legge in UTC, come `utc_now()`.

`routes/player/exports.py` confronta la data di modifica del file con
`utc_now()`, che è naive-UTC. Fino al 2026-11-10 la data si otteneva con
`datetime.fromtimestamp(...)` senza fuso, cioè nell'ora **locale** del server.
In produzione il server è in UTC e i due orologi coincidono; su una macchina in
ora italiana il file risultava un'ora o due più giovane: «già richiesto negli
ultimi cinque minuti» restava vero per un'ora, e la scadenza arrivava in
ritardo.

Il test forza un fuso diverso da UTC: su un runner in UTC la versione
sbagliata passerebbe lo stesso.
"""

import os
import time
from datetime import datetime

import pytest

from routes.player.exports import _file_mtime_utc

pytestmark = pytest.mark.unit


@pytest.fixture
def fuso_italiano():
    prima = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Rome"
    time.tzset()
    yield
    if prima is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = prima
    time.tzset()


def test_la_data_del_file_e_in_utc_anche_su_un_server_in_ora_locale(
    tmp_path, fuso_italiano
):
    file = tmp_path / "1_export.zip"
    file.write_bytes(b"x")
    # 2026-07-01 12:00:00 UTC: in Italia sono le 14:00.
    os.utime(file, (1782907200, 1782907200))

    assert _file_mtime_utc(file) == datetime(2026, 7, 1, 12, 0, 0)
