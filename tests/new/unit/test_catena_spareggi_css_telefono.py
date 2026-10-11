"""L'editor della catena degli spareggi non deve stringere i nomi sul telefono.

Nel passo 2 della gara singola l'editor sta dentro due card annidate e a
390px resta largo 266px. Ogni voce era una riga flessibile con il numero, il
corpo (nome e descrizione) e tre comandi da 44px; il corpo aveva
``flex: 1; min-width: 0``, cioè base zero e nessun minimo, e i comandi
``flex-shrink: 0``. Risultato: il corpo si riduceva a 30px e «Differenza
triangoli» andava a capo lettera per lettera.

La correzione sta nel CSS del componente, quindi vale in ogni posto che lo
include (gara singola, modifica gara, modale nuova gara, wizard e modifica del
campionato): la voce va a capo **sempre**, non solo sotto il punto di rottura,
e il corpo chiede una base minima, così quando non c'è posto sono i comandi a
scendere sotto. jsdom non calcola il layout, quindi il presidio è statico:
legge le regole fuori dalle media query.
"""

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[3] / "static" / "css" / "theme-7c.css"


def _regole_fuori_dalle_media_query(css: str) -> dict[str, str]:
    """Selettore → dichiarazioni, per le sole regole di primo livello."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    regole: dict[str, str] = {}
    profondita = 0
    inizio = 0
    selettore = ""
    for i, c in enumerate(css):
        if c == "{":
            if profondita == 0:
                selettore = css[inizio:i].strip()
                corpo_da = i + 1
            profondita += 1
        elif c == "}":
            profondita -= 1
            if profondita == 0:
                if not selettore.startswith("@"):
                    for s in selettore.split(","):
                        regole[s.strip()] = (
                            regole.get(s.strip(), "") + ";" + css[corpo_da:i]
                        )
                inizio = i + 1
    return regole


def _dichiarazione(corpo: str, proprieta: str) -> str | None:
    trovate = re.findall(rf"(?:^|;|\s){re.escape(proprieta)}\s*:\s*([^;]+)", corpo)
    return trovate[-1].strip() if trovate else None


REGOLE = _regole_fuori_dalle_media_query(CSS.read_text(encoding="utf-8"))


def test_la_voce_va_a_capo_a_ogni_larghezza():
    """Non solo sotto lg: l'editor sta anche in colonne strette su desktop."""
    corpo = REGOLE[".c7-catena__voce"]
    assert _dichiarazione(corpo, "flex-wrap") == "wrap"


def test_il_corpo_ha_una_base_minima():
    """Con base zero il corpo si lascia schiacciare dai comandi rigidi."""
    flex = _dichiarazione(REGOLE[".c7-catena__corpo"], "flex")
    assert flex is not None
    parti = flex.split()
    assert len(parti) == 3, f"serve la forma estesa grow shrink basis: {flex!r}"
    base = re.fullmatch(r"(\d+(?:\.\d+)?)(rem|em|px)", parti[2])
    assert base and float(base.group(1)) > 0, f"base nulla o non in lunghezza: {flex!r}"


def test_i_comandi_scesi_sotto_restano_a_destra():
    assert _dichiarazione(REGOLE[".c7-catena__comandi"], "margin-left") == "auto"
