"""La card della partita regge le colonne strette della griglia del desktop.

Sul desktop le partite del turno stanno in due colonne (canvas 3.9), e ogni
lato della card con gli stepper diventa più stretto di «− numero +» con due
bersagli da 48px: il + sbordava dal lato. E la testata di una partita
conclusa — stato, tavolo, «Correggi», menu — non stava su una riga e si
schiacciava fino a far toccare stato e tavolo. Trovato nelle schermate della
guida il 2026-09-13; c'era già dalla prima card con gli stepper.

Il CSS non si prova con un browser nella suite: questi controlli leggono le
regole che lo impediscono, così che toglierle faccia rosso.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

CSS = (
    Path(__file__).resolve().parents[3] / "static" / "css" / "theme-7c.css"
).read_text(encoding="utf-8")


def _regola(selettore: str) -> str:
    inizio = CSS.index(selettore + " {")
    return CSS[inizio : CSS.index("}", inizio)]


def test_il_lato_con_gli_stepper_e_un_contenitore():
    assert "container-type: inline-size" in _regola(".c7-partita__lato--stepper")


def test_sotto_la_larghezza_di_due_bersagli_gli_stepper_si_impilano():
    inizio = CSS.index("@container (max-width: 150px)")
    blocco = CSS[inizio : CSS.index("\n}\n", inizio)]
    assert ".c7-partita__step { flex-direction: column-reverse" in blocco


def test_le_colonne_delle_partite_sono_due_solo_dove_ci_stanno():
    """A 1024 e 1280, con la colonna laterale, due card affiancate erano da 160px."""
    inizio = CSS.index("@media (min-width: 992px) {\n  .c7-partite {")
    blocco = CSS[inizio : CSS.index("\n}\n", inizio)]
    assert "repeat(auto-fill, minmax(340px, 1fr))" in blocco
    assert "repeat(2, minmax(0, 1fr))" not in blocco


def test_la_testata_della_card_va_a_capo():
    assert "flex-wrap: wrap" in _regola(".c7-partita__testa")
    assert "flex-wrap: wrap" in _regola(".c7-partita__destra")
