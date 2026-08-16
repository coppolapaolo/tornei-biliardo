"""Il foglio di stile del builder non deve uscire dal builder.

Il tool nasce come pagina autonoma e stila ``body``, ``header``, ``main``,
``*`` e — la peggiore — ``.btn``, che nell'applicazione è di Bootstrap.
Innestato senza confine ridisegnerebbe **ogni pulsante di ogni schermata**, e
il sintomo sarebbe «l'app è cambiata aspetto» senza nessuna modifica visibile
nel diff della pagina interessata.

Il presidio serve soprattutto alla prossima volta: il builder è un file che
l'utente aggiorna e riporta, e chi lo ri-innesta rischia di incollare il CSS
originale. Questo test fallisce prima che succeda.
"""

import re
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parents[3] / "static" / "css" / "drill-builder.css"
ROOT = ".drill-builder"


def _strip_comments(css: str) -> str:
    """Via i commenti prima di leggere i selettori.

    Un commento sta *fuori* da ogni graffa, quindi un parser ingenuo lo scambia
    per il selettore della regola che segue — e questo file ne ha uno in testa
    che nomina apposta `.btn` e `header`, cioè proprio le parole che il test
    cerca.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _selectors(css: str):
    """I gruppi di selettori, cioè ciò che sta prima di ogni ``{``.

    Si salta il corpo delle regole (dove le graffe sono annidate) e le at-rule,
    che non sono selettori: dentro una media query i selettori veri vengono
    comunque letti al giro successivo.
    """
    css = _strip_comments(css)
    out, depth, buf = [], 0, ""
    for ch in css:
        if ch == "{":
            if depth == 0:
                buf = buf.strip()
                if buf and not buf.startswith("@"):
                    out.append(buf)
            buf = ""
            depth += 1
        elif ch == "}":
            depth -= 1
            buf = ""
        elif depth == 0:
            buf += ch
    return out


def test_il_foglio_esiste():
    assert CSS.exists(), "static/css/drill-builder.css è sparito"


def test_ogni_selettore_e_confinato():
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    # Le at-rule contengono selettori annidati: si valutano anche quelli.
    inner = re.findall(r"@media[^{]*\{(.*?)\n\s*\}", css, re.S)
    gruppi = _selectors(css) + [s for blocco in inner for s in _selectors(blocco + "}")]

    fuori = [sel for gruppo in gruppi for sel in gruppo.split(",") if ROOT not in sel]

    assert not fuori, (
        "Selettori fuori da .drill-builder: %s. "
        "Il CSS del builder deve restare confinato — stila anche `.btn`, che "
        "nell'app è di Bootstrap." % fuori
    )


@pytest.mark.parametrize("pericoloso", ["body{", "html,body{", "*{", ".btn{"])
def test_nessuna_regola_globale_del_tool_originale(pericoloso):
    """Le firme del file autonomo: se ricompaiono, è stato incollato grezzo."""
    css = _strip_comments(CSS.read_text(encoding="utf-8"))
    righe_nude = [
        riga for riga in css.splitlines() if riga.strip().startswith(pericoloso)
    ]
    assert not righe_nude, f"Regola globale non confinata: {righe_nude}"
