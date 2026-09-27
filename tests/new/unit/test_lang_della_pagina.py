"""`<html lang>` dice la lingua in cui la pagina è scritta davvero.

Era `lang="it"` scritto a mano in `base.html`: chi sceglieva l'inglese
riceveva testo inglese dichiarato italiano. Il lettore di schermo lo legge con
la pronuncia italiana, il browser propone di tradurlo «dall'italiano», e i
motori di ricerca lo indicizzano come pagina italiana.
"""

import pytest


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_lang_segue_la_lingua_scelta(client, lingua):
    client.get(f"/set_language/{lingua}")
    html = client.get("/auth/login").get_data(as_text=True)
    assert f'<html lang="{lingua}"' in html
