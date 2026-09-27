"""Una conferma non passa dal `confirm()` del browser (ADR-074).

Il 27 settembre 2026 il direttore premeva «Accetta» per conto dell'ultimo
invitato ai playoff, e non succedeva nulla: niente nel log, niente in
console, form corretto. Dopo sei conferme sulla stessa pagina il browser
aveva offerto «impedisci a questa pagina di creare altre finestre di
dialogo», e da lì `confirm()` restituiva `false` senza mostrare niente. Il
form non partiva. Con una scheda nuova ha funzionato.

Non era la prima volta che la regola esisteva: l'11 gennaio 2026 **tutte** le
67 chiamate a `confirm()` erano state migrate a `showConfirm`
(`docs/reference/UI_CONVENTIONS.md`, registro delle decisioni). Nessun test
la presidiava, e in otto mesi ne sono ricomparse diciassette — tutte in
codice scritto dopo, compreso il pulsante che si è bloccato. Una regola
senza presidio dura quanto la memoria di chi l'ha scritta.

**Cosa conta come chiamata.** `confirm(` e `window.confirm(` fuori dai
commenti: `{# … #}` di Jinja, `<!-- … -->`, `/* … */` e `// …`. Un metodo
omonimo — `modal.confirm(`, `showConfirm(`, `confirmSubmit(` — non è il
dialogo del browser e non conta.

**L'unica eccezione** è il ripiego dentro `showConfirm`, in
`static/js/notifications.js`: scatta solo se una pagina non ha il modale di
`base.html`, e lì chiedere col browser è meglio che eseguire senza chiedere o
non eseguire affatto.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Chiamate ammesse, per file: il ripiego di `showConfirm` quando manca il
# modale di `base.html`.
AMMESSE = {"static/js/notifications.js": 1}

_COMMENTI = re.compile(
    r"\{#.*?#\}"  # Jinja
    r"|<!--.*?-->"  # HTML
    r"|/\*.*?\*/"  # JS / CSS a blocco
    r"|(?<![:\w'\"])//[^\n]*",  # JS a riga, ma non `https://`
    re.DOTALL,
)

# `confirm(` non preceduto da un carattere di identificatore o da un punto
# (esclude `showConfirm(`, `modal.confirm(`), oppure `window.confirm(`.
_CHIAMATA = re.compile(r"(?:(?<![\w$.])|(?<=window\.))confirm\s*\(")


def _sorgenti() -> Iterator[Path]:
    yield from sorted((PROJECT_ROOT / "templates").rglob("*.html"))
    for js in sorted((PROJECT_ROOT / "static" / "js").rglob("*.js")):
        if not js.name.endswith(".min.js"):
            yield js


def _senza_commenti(testo: str) -> str:
    """Toglie i commenti tenendo gli a-capo, così i numeri di riga restano."""
    return _COMMENTI.sub(lambda m: "\n" * m.group(0).count("\n"), testo)


def chiamate_a_confirm(testo: str) -> list[int]:
    """Le righe in cui si chiama il `confirm()` del browser."""
    pulito = _senza_commenti(testo)
    return [pulito.count("\n", 0, m.start()) + 1 for m in _CHIAMATA.finditer(pulito)]


def test_il_riconoscitore_distingue_le_chiamate_dai_nomi_simili():
    """Il criterio è testuale: lo si mette alla prova prima di fidarsene."""
    assert chiamate_a_confirm("onclick='return confirm(\"x\")'") == [1]
    assert chiamate_a_confirm("if (window.confirm(msg)) {}") == [1]
    assert chiamate_a_confirm("return confirmSubmit(this, msg)") == []
    assert chiamate_a_confirm("showConfirm(msg, fn)") == []
    assert chiamate_a_confirm("modal.confirm(x)") == []
    assert chiamate_a_confirm("{# mai `confirm()` #}") == []
    assert chiamate_a_confirm("// fallback a confirm() nativo") == []
    assert chiamate_a_confirm("<!-- confirm(x) -->\nconfirm(y)") == [2]
    assert chiamate_a_confirm('<a href="https://x.it">confirm(1)</a>') == [1]


def test_nessun_confirm_del_browser():
    """Le conferme passano dal modale dell'app o da un foglio 7c (ADR-074)."""
    trovate: list[str] = []
    for percorso in _sorgenti():
        relativo = percorso.relative_to(PROJECT_ROOT).as_posix()
        righe = chiamate_a_confirm(percorso.read_text(encoding="utf-8"))
        if len(righe) > AMMESSE.get(relativo, 0):
            trovate.extend(f"{relativo}:{riga}" for riga in righe)

    assert not trovate, (
        "`confirm()` del browser: se l'utente ha spuntato «impedisci altre "
        "finestre di dialogo» restituisce false in silenzio e il pulsante non "
        "fa nulla. Usa `confirmSubmit(this.form, …)` / `confirmSubmit(this, …)` "
        "o un foglio 7c (ADR-074):\n  " + "\n  ".join(trovate)
    )
