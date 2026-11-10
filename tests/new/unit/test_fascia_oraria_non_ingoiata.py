"""Una fascia oraria scritta male si interpreta o si rifiuta: non sparisce.

In «dove gioco» la fascia è un testo libero. Fino al 2026-11-10 tutto ciò che
non era esattamente `HH:MM-HH:MM` veniva scartato da un `except: pass`: il
modulo rispondeva «salvato», il campo tornava vuoto e la sala restava senza
orario. Bastava copiare il suggerimento con gli spazi attorno al trattino
(#216).

La decisione sul modulo — testo libero o due campi orario — resta aperta
nell'issue. Questa è la parte che vale comunque: il `pass` non c'è più.
"""

from datetime import time

import pytest

from models.exceptions import ValidationError
from models.individual_match.availability_service import parse_fascia_oraria

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "testo",
    [
        "18:00-22:00",
        "18:00 - 22:00",  # il suggerimento, scritto largo
        " 18:00-22:00 ",
        "18:00–22:00",  # il trattino lungo che l'iPhone mette da solo
        "18:00—22:00",
        "18-22",
        "18 - 22",
        "18.00-22.00",
    ],
)
def test_le_scritture_ragionevoli_si_capiscono(testo):
    assert parse_fascia_oraria(testo) == (time(18, 0), time(22, 0))


def test_i_minuti_si_conservano():
    assert parse_fascia_oraria("9:30-12:45") == (time(9, 30), time(12, 45))


@pytest.mark.parametrize("testo", [None, "", "   "])
def test_il_campo_vuoto_vuol_dire_nessuna_fascia(testo):
    assert parse_fascia_oraria(testo) is None


@pytest.mark.parametrize(
    "testo",
    ["dopo cena", "dalle 18 alle 22", "18:00", "25:00-26:00", "18:00-22:99", "a-b"],
)
def test_cio_che_non_si_capisce_si_rifiuta_a_voce_alta(testo):
    with pytest.raises(ValidationError):
        parse_fascia_oraria(testo)
