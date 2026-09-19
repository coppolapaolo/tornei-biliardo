"""Difetti trovati mappando TPA, esercizi ed esami per il redesign (2026-09-19).

Nessuno di questi dava un errore: sono tutti testi o regole di stile che
**sembrano** a posto finché non li si guarda da vicino, e per questo i presidi
sono statici, sul testo dei file.

1. la guida aveva due refusi lasciati da una rinomina fatta col cerca-e-
   sostituisci («drill» → «esercizi»): «sequenza dgli esercizi» e il modulo
   «Nuova esercizi»;
2. nel referto TPA l'intestazione di ogni triangolo diceva «Triangoli 1»,
   «Triangoli 2»: è un ordinale, non un conteggio — stessa rinomina;
3. sempre nel referto, gli accenti erano scritti con l'apostrofo
   («perche'», «e'», «piu'»): testo visibile all'utente, non un commento;
4. da 640px il tastierino andava su sei colonne **anche per le lettere**, e la
   disposizione del foglio Accu-Stats — M K S / P G N / n x p — si rompeva;
5. i due tasti larghi erano alti 46px, sotto la soglia di tocco del design
   system;
6. «Esami» stava nella barra laterale e non nella nav del telefono: da
   telefono gli esami non avevano una porta.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REFERTO = ROOT / "templates" / "individual_match" / "tpa_referto.html"
CSS = ROOT / "static" / "css" / "theme-7c.css"
BASE = ROOT / "templates" / "base.html"
GUIDA = ROOT / "help_content"


def test_la_guida_non_ha_i_refusi_della_rinomina():
    trovati = []
    for path in sorted(GUIDA.rglob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for refuso in ("dgli ", "Nuova esercizi"):
            if refuso in text:
                trovati.append(f"{path.relative_to(ROOT)}: «{refuso.strip()}»")
    assert not trovati, "\n".join(trovati)


def test_l_intestazione_del_triangolo_e_al_singolare():
    """«Triangolo 3» è il terzo triangolo, non tre triangoli."""
    text = REFERTO.read_text(encoding="utf-8")
    match = re.search(r"const LABEL_RACK = \{\{ _\('([^']+)'\)", text)
    assert match, "LABEL_RACK non trovata: il test va aggiornato"
    assert match.group(1) == "Triangolo"


def test_il_referto_non_scrive_gli_accenti_con_l_apostrofo():
    text = REFERTO.read_text(encoding="utf-8")
    # Dentro una stringa Jinja fra apici singoli l'apostrofo è `\'`: una
    # vocale seguita da `\'` e poi da uno spazio, un punto o la fine della
    # stringa è un accento scritto male, non un'elisione («l\'altro»).
    sospetti = re.findall(r"\w*[aeiou]\\'(?=[\s.,;:?!)]|'\))", text)
    assert not sospetti, sospetti


def _blocco_media_640(css: str) -> str:
    start = css.index("/* Da 640px in su le due colonne del referto")
    end = css.index("}\n}", start)
    return css[start:end]


def test_le_lettere_restano_su_tre_colonne_anche_su_schermo_largo():
    """M K S / P G N / n x p: la griglia è quella del foglio, a ogni larghezza.

    La regola del breakpoint aveva la stessa specificità di
    `.c7-tpa-pad--letters` e veniva dopo: vinceva lei, e le nove lettere
    finivano su sei colonne.
    """
    blocco = _blocco_media_640(CSS.read_text(encoding="utf-8"))
    assert ".c7-tpa-pad:not(.c7-tpa-pad--letters)" in blocco
    assert not re.search(r"\.c7-tpa-pad\s*\{", blocco)


def test_i_tasti_larghi_del_referto_hanno_l_altezza_di_tocco():
    css = CSS.read_text(encoding="utf-8")
    regola = re.search(r"\.c7-tpa-key--wide\s*\{([^}]*)\}", css)
    assert regola
    assert "46px" not in regola.group(1)
    assert "var(--c7-touch)" in regola.group(1)


def test_gli_esami_hanno_una_porta_anche_nella_nav_del_telefono():
    text = BASE.read_text(encoding="utf-8")
    start = text.index('<nav class="c7-mobilenav">')
    nav = text[start : text.index("</nav>", start)]
    assert "exam.exam_catalog" in nav
    assert "nav_exam" in nav
