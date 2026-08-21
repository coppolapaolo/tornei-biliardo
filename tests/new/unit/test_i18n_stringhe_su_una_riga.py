"""Una stringa dentro `_()` non può essere spezzata su più righe.

Il formattatore HTML manda a capo gli attributi lunghi, e quando il capo cade
*dentro* `_("...")` il testo non cambia a schermo — cambia il `msgid`, che si
porta dietro il ritorno a capo e l'indentazione della riga sotto:

    {{ _("Questi dati saranno visibili ai giocatori e servono a
        identificare la gara.") }}

    msgid "Questi dati saranno visibili ai giocatori e servono a\\n"
    "                                identificare la gara."

Da lì in poi la stringa è **intraducibile in pratica**: la voce nel catalogo
esiste, ma chi traduce vede un testo con dentro trenta spazi, e alla prima
rindentazione del template il `msgid` cambia di nuovo e la traduzione si
stacca. Il difetto non si vede in italiano — la lingua di partenza esce dal
sorgente comunque — e si manifesta solo come una frase rimasta italiana in
mezzo a una pagina inglese.

È quel che era successo al passo 1 della creazione gara: sei stringhe su sette
spezzate, e la schermata inglese della guida (`static/img/help/en/gara-nuova.png`)
che mostrava un'interfaccia italiana.

Le eccezioni sono i testi in cui il ritorno a capo è **voluto** e fa parte di
quel che si legge — un `placeholder` di textarea su più righe. Vanno elencate
qui sotto una per una: se una stringa multilinea è deliberata, dirlo è il modo
di distinguerla da una spezzata per sbaglio.
"""

from __future__ import annotations

import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[3]
TEMPLATES = RADICE / "templates"

# `_("...")` / `_('...')`, apici escapati compresi. `re.S` perché è proprio il
# caso multilinea quello che stiamo cercando.
CHIAMATA = re.compile(r"""_\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""", re.S)

# Stringhe in cui il ritorno a capo è parte del testo mostrato.
DELIBERATE = {
    # placeholder di una textarea: gli orari di apertura si leggono uno per riga
    ("templates/admin/venue_form.html", "es:"),
}


def _e_deliberata(percorso: str, testo: str) -> bool:
    return any(percorso == p and testo.startswith(inizio) for p, inizio in DELIBERATE)


def test_nessuna_stringa_tradotta_spezzata_su_piu_righe():
    colpevoli: list[str] = []

    for file in sorted(TEMPLATES.rglob("*.html")):
        sorgente = file.read_text(encoding="utf-8")
        relativo = file.relative_to(RADICE).as_posix()

        for trovata in CHIAMATA.finditer(sorgente):
            testo = trovata.group(1)
            if testo is None:
                testo = trovata.group(2)
            if "\n" not in testo:
                continue
            if _e_deliberata(relativo, testo):
                continue
            riga = sorgente[: trovata.start()].count("\n") + 1
            colpevoli.append(f"{relativo}:{riga} -> {testo[:60]!r}")

    assert not colpevoli, (
        "Stringhe tradotte spezzate su più righe: il ritorno a capo finisce "
        "nel msgid e la traduzione non si aggancia più.\n"
        "Riuniscile su una riga sola, oppure — se il capo è voluto — "
        "aggiungile a DELIBERATE in questo file.\n  " + "\n  ".join(colpevoli)
    )
