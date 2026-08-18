"""Le traduzioni devono restare stringhe di formato valide.

Incidente 2026-08-17 (GlitchTip TORNEI-BILIARDO-63, `player.profile`): il
catalogo inglese aveva `msgstr[0] "%"` e `msgstr[1] "("` per `%(n)s referto`.
Un `"%"` da solo, che `jinja2.ext` passa a `rv % variables`, solleva
`ValueError: incomplete format`: la pagina profilo in inglese rispondeva 500.

Nessuno l'aveva scritto a mano. Il ciclo di traduzione riempie le voci nuove
pescando da altre, e un plurale puo' uscirne ridotto a un frammento. Il
catalogo non e' codice: ne' pyright ne' flake8 lo guardano, e `pybabel
compile` accetta senza fiatare una msgstr che si rompe solo al momento
dell'interpolazione. Senza questo presidio l'unico modo di accorgersene e'
l'errore in faccia a chi legge.

Due invarianti, entrambe sul solo `msgstr` — il `msgid` e' scritto a mano nel
codice, e li' un errore si vede subito:

1. ogni `%` fa parte di uno specificatore valido, altrimenti `ValueError`;
2. i placeholder nominati della traduzione esistono anche nell'originale,
   altrimenti `KeyError`: il dizionario lo costruisce il chiamante guardando
   il `msgid`, e una chiave inventata dal traduttore non ci sara' mai.

Il controllo si applica alle sole voci marcate `python-format`. Le altre non
vengono mai interpolate, e un `%` letterale li' e' legittimo ("50% dei tiri").
"""

import re
from pathlib import Path

import pytest
from babel.messages.pofile import read_po

CATALOGHI = sorted(Path("translations").glob("*/LC_MESSAGES/messages.po"))

# Uno specificatore di conversione %-style completo, nominato o posizionale.
_CONVERSIONE = re.compile(
    r"%(?:\(\w+\))?[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?[diouxXeEfFgGcrsa%]"
)
_NOMINATO = re.compile(
    r"%\((\w+)\)[-+ #0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlL]?[diouxXeEfFgGcrsa]"
)


def _percentuali_rotte(testo: str) -> list:
    """Ogni `%` che non apre uno specificatore valido, col suo contorno."""
    rotte = []
    i = 0
    while i < len(testo):
        if testo[i] != "%":
            i += 1
            continue
        match = _CONVERSIONE.match(testo, i)
        if match is None:
            rotte.append(testo[max(0, i - 12) : i + 12])
            i += 1
        else:
            i = match.end()
    return rotte


def _nominati(testo: str) -> set:
    return set(_NOMINATO.findall(testo))


def _voci(catalogo):
    """(originali, traduzioni) per ogni voce interpolata e non vuota."""
    for messaggio in catalogo:
        if not messaggio.id or "python-format" not in messaggio.flags:
            continue
        originali = (
            list(messaggio.id)
            if isinstance(messaggio.id, (list, tuple))
            else [messaggio.id]
        )
        traduzioni = (
            list(messaggio.string)
            if isinstance(messaggio.string, (list, tuple))
            else [messaggio.string]
        )
        yield originali, [t for t in traduzioni if t]


@pytest.mark.unit
@pytest.mark.parametrize("percorso", CATALOGHI, ids=lambda p: p.parts[1])
def test_le_traduzioni_non_hanno_percentuali_penzolanti(percorso):
    """Un `%` che non apre uno specificatore fa `ValueError` all'uso."""
    with percorso.open("rb") as sorgente:
        catalogo = read_po(sorgente, locale=percorso.parts[1])

    guasti = [
        f"{originali[0]!r} -> {traduzione!r} (attorno a: {rotte})"
        for originali, traduzioni in _voci(catalogo)
        for traduzione in traduzioni
        for rotte in [_percentuali_rotte(traduzione)]
        if rotte
    ]
    assert not guasti, (
        "traduzioni non interpolabili in " + str(percorso) + ":\n" + "\n".join(guasti)
    )


@pytest.mark.unit
@pytest.mark.parametrize("percorso", CATALOGHI, ids=lambda p: p.parts[1])
def test_le_traduzioni_non_inventano_placeholder(percorso):
    """Un `%(nome)s` assente dall'originale fa `KeyError` all'uso."""
    with percorso.open("rb") as sorgente:
        catalogo = read_po(sorgente, locale=percorso.parts[1])

    guasti = []
    for originali, traduzioni in _voci(catalogo):
        attesi = set().union(*(_nominati(o) for o in originali)) if originali else set()
        for traduzione in traduzioni:
            inventati = _nominati(traduzione) - attesi
            if inventati:
                guasti.append(
                    f"{originali[0]!r} -> {traduzione!r} "
                    f"(inventati: {sorted(inventati)})"
                )
    assert not guasti, (
        "placeholder inesistenti in " + str(percorso) + ":\n" + "\n".join(guasti)
    )
