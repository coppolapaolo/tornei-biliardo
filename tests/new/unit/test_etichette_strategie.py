"""Il nome mostrato di un formato di gara ha una fonte sola.

Fino al 2026-10-11 i nomi erano tre: `get_available_strategies()` li ricavava
dal valore in colonna senza tradurli («Round Robin», «Direct Elimination»),
`CAMPIONATO_TYPES` ne aveva di suoi tradotti — ma diceva «Random» dove la guida
e il resto dell'interfaccia dicono «Casuale» — e la macro `nome_formula` dei
template una terza copia. Il menu della modifica della gara parlava inglese
accanto al modale «Nuova gara» che parlava italiano.

La fonte è `ETICHETTE_STRATEGIA` in `models/matchmaking/configuration.py`: i
menu la leggono da `get_available_strategies()` o da `CAMPIONATO_TYPES`, le
pagine dal filtro `nome_formula`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from models.matchmaking.configuration import (
    ETICHETTE_STRATEGIA,
    MatchmakingStrategy,
    etichetta_strategia,
    get_available_strategies,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# I nomi che l'interfaccia e la guida (`help_content/it/pages/abbinamenti.yaml`)
# usano già, nell'ordine dei menu.
NOMI_ATTESI = {
    "amalfi": "Amalfi",
    "random": "Casuale",
    "round_robin": "Girone all'italiana",
    "direct_elimination": "Eliminazione diretta",
    "double_knockout": "Doppio KO",
}


@pytest.fixture
def richiesta_italiana(app):
    with app.test_request_context("/", headers={"Accept-Language": "it"}):
        yield


def test_ogni_strategia_ha_il_suo_nome():
    assert set(ETICHETTE_STRATEGIA) == set(MatchmakingStrategy)


def test_i_nomi_sono_quelli_della_guida(richiesta_italiana):
    nomi = {s.value: etichetta_strategia(s.value) for s in MatchmakingStrategy}
    assert nomi == NOMI_ATTESI


def test_i_menu_della_gara_usano_i_nomi_tradotti(richiesta_italiana):
    strategie = get_available_strategies()
    assert {k: v["display_name"] for k, v in strategie.items()} == NOMI_ATTESI
    # Stesso ordine del modale «Nuova gara»: la fonte decide anche quello.
    assert list(strategie) == list(NOMI_ATTESI)
    # Arriva nel `data-vincoli` via `tojson`: deve essere una stringa vera.
    assert all(type(v["display_name"]) is str for v in strategie.values())
    # Anche la descrizione mostrata sotto il menu è tradotta e serializzabile.
    assert strategie["round_robin"]["description"] == (
        "Girone all'italiana: tutti contro tutti"
    )
    assert all(type(v["description"]) is str for v in strategie.values())
    assert all(type(v["constraints"]["description"]) is str for v in strategie.values())


def test_i_formati_del_campionato_vengono_dalla_stessa_fonte(richiesta_italiana):
    from routes.admin.campionato import CAMPIONATO_TYPES

    assert [(v, str(n)) for v, n in CAMPIONATO_TYPES] == list(NOMI_ATTESI.items())


def test_il_filtro_dei_template_usa_la_stessa_fonte(app, richiesta_italiana):
    filtro = app.jinja_env.filters["nome_formula"]
    assert filtro("round_robin") == "Girone all'italiana"
    assert filtro(MatchmakingStrategy.RANDOM) == "Casuale"
    # Un valore fuori vocabolario non sparisce, e un vuoto resta vuoto.
    assert filtro("formula_ignota") == "Formula ignota"
    assert filtro(None) == ""


# Le forme con cui i template ricavavano il nome dal valore in colonna:
# ripulito a mano (`|title`, `.replace("_", " ")`) o stampato grezzo.
NOME_RICAVATO_A_MANO = re.compile(
    r"(campionato_type|matchmaking_strategy)\s*"
    r"(\|\s*(title|capitalize)|\.replace\(|(\s+or\s+'')?\)\s*\|\s*replace\()"
    r"|\{\{\s*[\w.]+\.(campionato_type|matchmaking_strategy)\s*\}\}"
)
# Dove il valore grezzo è voluto: gli attributi letti dal JavaScript e il
# riquadro di debug, che mostra la colonna com'è.
VALORE_GREZZO_VOLUTO = re.compile(r"value=|data-|onclick=|Type:")


def test_nessun_template_ricava_il_nome_dal_valore():
    colpevoli = []
    for path in sorted((REPO_ROOT / "templates").rglob("*.html")):
        for n, riga in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if NOME_RICAVATO_A_MANO.search(riga) and not VALORE_GREZZO_VOLUTO.search(
                riga
            ):
                colpevoli.append(f"{path.relative_to(REPO_ROOT)}:{n}: {riga.strip()}")
    assert not colpevoli, "usa il filtro `nome_formula`:\n" + "\n".join(colpevoli)
