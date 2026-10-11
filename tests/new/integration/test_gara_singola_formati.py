"""La creazione della gara singola: formati coi nomi tradotti, regole da un modulo solo.

Fino al 2026-10-11 il menu del formato diceva «Round Robin» e «Direct
Elimination» (nomi ricavati dal valore in colonna) e la pagina aveva una sua
copia inline delle regole che seguono il formato, che non filtrava i dispari
per sistema di classifica. Ora i nomi vengono da `ETICHETTE_STRATEGIA` e le
regole da `static/js/strategia_gara.js`, come nella modifica della gara e nel
modale «Nuova gara».
"""

from __future__ import annotations

import re
import uuid

import pytest

from models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def director(db_session):
    user = User(
        username=f"dir_{uuid.uuid4().hex[:8]}",
        email=f"dir_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.DIRECTOR.value,
        onboarding_completed=True,
    )
    user.set_password("director123")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def pagina(client, director):
    client.post(
        "/auth/login",
        data={"username": director.username, "password": "director123"},
        follow_redirects=True,
    )
    risposta = client.get("/admin/gara/create_standalone")
    assert risposta.status_code == 200
    return risposta.get_data(as_text=True)


def _menu_formato(pagina: str) -> str:
    inizio = pagina.index('id="matchmaking_strategy"')
    return pagina[inizio : pagina.index("</select>", inizio)]


def test_il_menu_del_formato_ha_i_nomi_tradotti(pagina):
    menu = _menu_formato(pagina)
    nomi = [
        n.strip()
        for n in re.findall(r"<option[^>]*>\s*([^<]+?)\s*</option>", menu, re.S)
    ]
    assert nomi == [
        "Amalfi",
        "Casuale",
        "Girone all&#39;italiana",
        "Eliminazione diretta",
        "Doppio KO",
    ]
    assert "Round Robin" not in menu and "Direct Elimination" not in menu


def test_le_regole_del_formato_vengono_dal_modulo_condiviso(pagina):
    menu = _menu_formato(pagina)
    assert "data-strategia-gara" in menu
    assert 'data-girone="round_robin"' in menu
    assert "js/strategia_gara.js" in pagina
    # La sezione dell'anti-reincontro si nasconde solo nel girone.
    assert re.search(r'id="anti_rematch_section"[^>]*data-nascondi-se-spento', pagina)
    # La copia inline non c'è più.
    assert "function updateStrategyUI" not in pagina
    assert "allowedOddPolicies" not in pagina
