"""Quattro difetti d'interfaccia, presidiati sul testo di CSS e template.

jsdom non calcola il layout, e la CI esegue solo i test unitari: dove la
correzione è una regola di CSS il presidio legge la regola, dove è un
template lo rende.

* **Tabellone dopo i gironi (e tabellone puro con la finalina)**: il nodo
  futuro della Finale diceva «chi vince Giada Ferraro – Beatrice Serra» in
  una riga sola; da elemento flex il nodo non scendeva sotto quella
  larghezza e si accavallava alla «Finale 3°/4°» accanto. Sul telefono la
  colonna dopo era tagliata contro il margine della pagina. Lo schermo in
  sala, a gironi finiti, impilava le classifiche sotto il tabellone e le
  righe schiacciate si sovrapponevano; sul telefono i nomi andavano a capo a
  metà parola.
* **Card a tempo scaduto**: «In corso · Girone B · Tempo scaduto +12'»
  mandava a capo il tavolo, da solo.
* **Design system**: «fino al 3°» nell'editor della catena era in
  monospazio, e «I miei preset» era una lista dentro una card.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
CSS = (ROOT / "static" / "css" / "theme-7c.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "templates"


def _regole(css: str) -> list[tuple[str, str, str]]:
    """(media query o "", selettore, dichiarazioni) per ogni regola."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    regole: list[tuple[str, str, str]] = []
    pila: list[str] = []
    inizio = 0
    for i, c in enumerate(css):
        if c == "{":
            pila.append(css[inizio:i].strip())
            inizio = i + 1
        elif c == "}":
            selettore = pila.pop() if pila else ""
            if not selettore.startswith("@"):
                media = next((p for p in reversed(pila) if p.startswith("@")), "")
                for s in selettore.split(","):
                    regole.append((media, " ".join(s.split()), css[inizio:i]))
            inizio = i + 1
    return regole


REGOLE = _regole(CSS)


def _dichiarazioni(selettore: str, media: str | None = None) -> str:
    return ";".join(
        corpo
        for m, s, corpo in REGOLE
        if s == selettore and (media is None or media in m)
    )


def _valore(corpo: str, proprieta: str) -> str | None:
    trovati = re.findall(rf"(?:^|;|\s){re.escape(proprieta)}\s*:\s*([^;]+)", corpo)
    return trovati[-1].strip() if trovati else None


def _render(app, sorgente: str, **contesto) -> str:
    with app.test_request_context():
        return app.jinja_env.from_string(sorgente).render(**contesto)


# ── Il tabellone ────────────────────────────────────────────────────────────


def _posto_da_partita(esito: str):
    match = SimpleNamespace(
        player1=SimpleNamespace(username="Giada Ferraro"),
        player2=SimpleNamespace(username="Beatrice Serra"),
    )
    return SimpleNamespace(
        giocatore=None,
        vuoto=False,
        fonte=SimpleNamespace(
            esito=esito, nodo=SimpleNamespace(match=match, nome=None)
        ),
    )


MACRO = (
    '{% import "components/_tabellone_macros.html" as t with context %}'
    "{{ t.posto_nel_nodo(p) }}"
)


def test_nel_nodo_chi_vince_sta_sopra_e_i_due_nomi_sotto(app):
    html = _render(app, MACRO, p=_posto_da_partita("vincitore"))

    assert "c7-arrivo__esito" in html and "chi vince" in html
    nomi = re.findall(r'c7-arrivo__nome">([^<]+)<', html)
    assert nomi == ["Giada Ferraro", "Beatrice Serra"]
    # La frase in una riga sola è quella che allargava il nodo.
    assert "Giada Ferraro – Beatrice Serra" not in html


def test_nel_nodo_chi_perde_va_alla_finalina(app):
    html = _render(app, MACRO, p=_posto_da_partita("perdente"))
    assert "chi perde" in html


def test_nel_nodo_un_giocatore_gia_noto_resta_il_suo_nome(app):
    p = SimpleNamespace(
        giocatore=SimpleNamespace(username="Matteo Caruso"), vuoto=False, fonte=None
    )
    html = _render(app, MACRO, p=p)
    assert html.strip() == "Matteo Caruso"


def test_pagina_del_tabellone_e_tabellone_del_direttore_usano_il_posto_nel_nodo():
    for template in ("components/_bracket_view.html", "direttore/_tabellino.html"):
        testo = (TEMPLATES / template).read_text(encoding="utf-8")
        assert "t.posto_nel_nodo(p)" in testo, template
        assert "t.posto(p)" not in testo, template


def test_il_nodo_non_si_allarga_oltre_la_colonna():
    """Da elemento flex il nodo non scende sotto la sua larghezza minima."""
    assert _valore(_dichiarazioni(".c7-bracket__cell > *"), "min-width") == "0"


def test_la_finalina_non_e_collegata_alla_finale():
    """La finalina non discende dalla finale: niente moncherino fra le due."""
    assert "c7-bracket__col--finalina" in (
        TEMPLATES / "components" / "_bracket_view.html"
    ).read_text(encoding="utf-8")
    spenti = [
        s
        for m, s, corpo in REGOLE
        if "finalina" in s and _valore(corpo, "content") == "none"
    ]
    assert any(s.endswith("::before") for s in spenti)
    assert any(s.endswith("::after") for s in spenti)


def test_sul_telefono_il_tabellone_arriva_al_bordo_dello_schermo():
    """Lo spicchio della colonna dopo si taglia al bordo, non contro il margine."""
    corpo = _dichiarazioni(".c7-bracket", "max-width: 991.98px")
    assert _valore(corpo, "margin-inline") == "calc(-1 * var(--c7-gutter))"
    rotaia = _dichiarazioni(".c7-bracket__rail", "max-width: 991.98px")
    assert _valore(rotaia, "padding-inline") == "var(--c7-gutter)"


def test_lo_schermo_in_sala_affianca_i_gironi_sotto_il_tabellone():
    testo = (TEMPLATES / "public" / "schermo_sala.html").read_text(encoding="utf-8")
    assert "c7-sala__gironi--affiancati" in testo
    corpo = _dichiarazioni(".c7-sala__gironi--affiancati", "min-width: 992px")
    assert _valore(corpo, "grid-template-columns") == "repeat(2, minmax(0, 1fr))"
    # Le righe hanno un minimo: schiacciate a zero si sovrapponevano.
    riga = _dichiarazioni(".c7-sala__gironi .c7-sala__riga", "min-width: 992px")
    assert _valore(riga, "min-height") not in (None, "0")


def test_sul_telefono_le_colonne_dello_schermo_in_sala_tengono_un_nome():
    corpo = _dichiarazioni(".c7-sala-tab__colonne", "max-width: 991.98px")
    assert "minmax(150px" in (_valore(corpo, "grid-auto-columns") or "")
    assert _valore(corpo, "overflow-x") == "auto"


# ── La card a tempo scaduto ─────────────────────────────────────────────────


def test_la_testata_della_card_va_a_capo_a_sinistra_e_lascia_il_tavolo_in_alto():
    """Base zero: la sinistra va a capo dentro di sé invece di prendersi la riga."""
    corpo = _dichiarazioni(".c7-partita__sinistra")
    assert _valore(corpo, "flex") == "1 1 0"
    assert _valore(corpo, "flex-wrap") == "wrap"


# ── Design system ───────────────────────────────────────────────────────────


def test_fino_al_terzo_non_e_in_monospazio():
    corpo = _dichiarazioni(".c7-catena__postovalore")
    assert corpo
    assert "font-mono" not in corpo


def test_i_miei_preset_non_sono_una_card_dentro_una_card():
    testo = (TEMPLATES / "admin" / "preset_miei.html").read_text(encoding="utf-8")
    assert '<section class="c7-card">' not in testo
    assert "c7-rows--sunk" not in testo
