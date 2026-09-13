"""L'interfaccia italiana dice «partita», mai «match».

Il vocabolario del progetto (``docs/reference/NAMING_CONVENTIONS.md``, skill
``help-docs`` e ``ui-7c``): «partita» per un incontro fra giocatori, «sfida
individuale» per quella amichevole, «turno» e non «round», «triangolo» e non
«rack», «X a tavolino» e non «bye», «esercizio» e non «challenge» o «drill»,
«direttore di gara» e non «director», «calendario» e non «schedule».

Identificatori, valori degli enum, URL e colonne restano come sono: qui si
guarda solo ciò che un utente legge, cioè i ``msgid`` del catalogo italiano.
I nomi dei segnaposto (``%(round)s``, ``{rounds}``) non si leggono e si tolgono
prima del controllo.

Il catalogo è la fonte giusta perché ogni stringa visibile passa da ``_()``:
una parola inglese scritta a mano in un template sfuggirebbe, ma è già un
difetto di i18n per conto suo.
"""

from __future__ import annotations

import re
from pathlib import Path

from babel.messages.pofile import read_po

CATALOGO = (
    Path(__file__).resolve().parents[3]
    / "translations"
    / "it"
    / "LC_MESSAGES"
    / "messages.po"
)

PAROLE_VIETATE = re.compile(
    r"\b(match(?:es)?|rounds?|racks?|byes?|challenges?|drills?|directors?"
    r"|schedules?)\b",
    re.IGNORECASE,
)

SEGNAPOSTO = re.compile(r"%\(\w+\)[sd]|\{\w+\}")

# Eccezioni legittime: msgid esatto -> perché la parola resta.
# Vuota oggi: ogni occorrenza trovata era un difetto e si è corretta. Chi
# aggiunge una voce scrive il motivo, e il motivo deve reggere a una rilettura.
ECCEZIONI: dict[str, str] = {}


def _msgid_italiani() -> list[str]:
    with CATALOGO.open("rb") as f:
        catalogo = read_po(f)
    testi: list[str] = []
    for voce in catalogo:
        if not voce.id:
            continue
        forme = voce.id if isinstance(voce.id, tuple) else (voce.id,)
        testi.extend(forme)
    return testi


def test_nessun_msgid_italiano_usa_il_vocabolario_inglese():
    trovati = []
    for testo in _msgid_italiani():
        if testo in ECCEZIONI:
            continue
        parola = PAROLE_VIETATE.search(SEGNAPOSTO.sub("", testo))
        if parola:
            trovati.append(f"{parola.group(0)!r} in {testo!r}")
    assert not trovati, (
        "Stringhe dell'interfaccia italiana con termini inglesi "
        "(partita, turno, triangolo, X a tavolino, esercizio, direttore di "
        "gara, calendario):\n" + "\n".join(trovati)
    )


def test_il_controllo_riconosce_le_parole_e_ignora_i_segnaposto():
    """Il presidio non deve essere cieco né troppo zelante."""
    assert PAROLE_VIETATE.search("I match con handicap")
    assert PAROLE_VIETATE.search("Classifica (rack)")
    assert PAROLE_VIETATE.search("Rimuovi director")
    assert not PAROLE_VIETATE.search(SEGNAPOSTO.sub("", "Chi vince: %(round)s."))
    assert not PAROLE_VIETATE.search(SEGNAPOSTO.sub("", "al massimo {rounds} turni"))
    # Parole italiane che contengono le vietate non vanno segnalate.
    assert not PAROLE_VIETATE.search("Abbinamento del turno, rematch evitato")


def test_le_eccezioni_esistono_ancora_nel_catalogo():
    """Un'eccezione rimasta senza la sua stringa copre la prossima, in silenzio."""
    presenti = set(_msgid_italiani())
    orfane = [m for m in ECCEZIONI if m not in presenti]
    assert not orfane, f"Eccezioni senza stringa nel catalogo: {orfane}"
