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


# ---------------------------------------------------------------------------
# Il builder integrato non produce file.
#
# Il tool da cui viene nasce come pagina autonoma, e lì scaricare era l'unico
# modo di portarsi via il disegno. Qui è dentro l'applicazione e serve a una
# cosa sola: mettere il drill nel catalogo. Un pulsante che scarica un PNG o un
# JSON non porterebbe da nessuna parte, e accanto a «Salva il drill» sarebbe
# anche un tranello — si crede di aver pubblicato, e invece si ha un file nei
# download.
#
# Il presidio serve alla prossima versione del builder: chi la ri-innesta parte
# dall'originale, che quel pannello ce l'ha.
# ---------------------------------------------------------------------------

JS = Path(__file__).resolve().parents[3] / "static" / "js" / "drill-builder.js"
TEMPLATE = (
    Path(__file__).resolve().parents[3] / "templates" / "challenge" / "builder.html"
)


def _code_without_comments(source: str) -> str:
    """Via i commenti: qui se ne parla apposta, e non sono codice."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"\{#.*?#\}", "", source, flags=re.S)
    return re.sub(r"^\s*//.*$", "", source, flags=re.M)


@pytest.mark.parametrize(
    "impronta",
    [
        "a.download",
        "createObjectURL",
        "new FileReader",
        "exportImage",
        "function download",
    ],
)
def test_il_js_non_scarica_niente(impronta):
    codice = _code_without_comments(JS.read_text(encoding="utf-8"))
    assert impronta not in codice, (
        f"«{impronta}» è tornata in drill-builder.js: il builder integrato non "
        "produce file, l'immagine va al server."
    )


@pytest.mark.parametrize(
    "id_pulsante", ["expPng", "expJpg", "saveJson", "openJson", "fileIn"]
)
def test_il_pannello_esporta_non_c_e(id_pulsante):
    markup = _code_without_comments(TEMPLATE.read_text(encoding="utf-8"))
    assert id_pulsante not in markup, (
        f"«{id_pulsante}» è tornato nel builder: era un comando di scaricamento "
        "del tool autonomo e qui non ha senso."
    )


# ---------------------------------------------------------------------------
# Le parole del builder passano tutte da `_()`.
#
# `babel.cfg` estrae solo da `.py` e `.html`: una stringa scritta direttamente
# in `static/js/drill-builder.js` non è raggiungibile da gettext e resterebbe
# italiana in ogni lingua — senza che nulla si rompa, quindi senza che nessuno
# se ne accorga finché non apre la pagina in inglese.
#
# Il template le passa già tradotte in `window.DRILL_BUILDER_I18N`, e il JS le
# legge con `T_()`. Il presidio verifica le due metà: che il JS non abbia più
# testo italiano cablato, e che ogni chiave che chiede esista nel dizionario.
# ---------------------------------------------------------------------------

PAROLE_CABLATE = [
    '"tocco"',
    '"spacco"',
    '"Battente"',
    '"Biglia fantasma"',
    '"verticale',
    '"laterale',
    'toast("Clicca',
]


@pytest.mark.parametrize("parola", PAROLE_CABLATE)
def test_il_js_non_ha_testo_italiano_cablato(parola):
    """I ripieghi dentro `T_(...)` non contano: sono la rete, non l'etichetta."""
    codice = _code_without_comments(JS.read_text(encoding="utf-8"))
    # Toglie i ripieghi: `T_("chiave","testo italiano")` → `T_("chiave")`
    codice = re.sub(r'T_\((\s*"[^"]*")\s*,\s*"[^"]*"\s*\)', r"T_(\1)", codice)
    assert parola not in codice, (
        f"{parola} è cablata in drill-builder.js: va in DRILL_BUILDER_I18N, "
        "altrimenti resta italiana in ogni lingua."
    )


def test_ogni_chiave_chiesta_dal_js_esiste_nel_dizionario():
    """Una chiave assente non dà errore: cade sul ripiego italiano, in silenzio."""
    codice = _code_without_comments(JS.read_text(encoding="utf-8"))
    chieste = set(re.findall(r'T_\(\s*"([^"]+)"', codice))

    markup = TEMPLATE.read_text(encoding="utf-8")
    blocco = markup.split("window.DRILL_BUILDER_I18N = {", 1)
    assert len(blocco) == 2, "il dizionario delle traduzioni non c'è più"
    offerte = set(re.findall(r"^\s*(\w+):", blocco[1].split("};", 1)[0], re.M))

    mancanti = chieste - offerte
    assert not mancanti, f"chiavi chieste dal JS e non tradotte: {sorted(mancanti)}"


def test_il_dizionario_precede_lo_script():
    """`FORCE_PRESETS` è un `const`: un dizionario definito dopo arriva tardi."""
    markup = TEMPLATE.read_text(encoding="utf-8")
    assert markup.index("window.DRILL_BUILDER_I18N") < markup.index(
        "js/drill-builder.js"
    ), (
        "il dizionario deve stare prima dello <script src>, "
        "o le etichette della forza restano in italiano"
    )
