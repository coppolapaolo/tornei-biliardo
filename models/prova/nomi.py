"""I nomi dei giocatori fittizi di una competizione di prova.

Verosimili e generici — fra i nomi e i cognomi più diffusi in Italia — perché
una classifica di «Giocatore 3» e «Giocatore 7» non si legge, e il direttore
sta imparando proprio a leggere classifiche e abbinamenti. Il badge «prova»
sull'interfaccia li distingue dai giocatori veri; qui si evita solo di
coincidere con i nomi del seed dimostrativo della guida
(`scripts/help_docs/seed_demo.py`), che compaiono nelle schermate di /aiuto.

I rating iniziali sono **fissi e tutti diversi**: il seeding del primo turno
e le categorie devono mostrare qualcosa, e con sedici 1500 non mostrerebbero
niente. Sono decisi per posizione e non a caso, così due prove con lo stesso
numero di iscritti partono dalla stessa griglia e il direttore può ripetere
un esperimento.
"""

from __future__ import annotations

#: (nome, cognome, rating iniziale). L'ordine conta: i fittizi si creano
#: dal primo in poi, quindi una prova da otto ha sempre gli stessi otto.
NOMI_FITTIZI: tuple[tuple[str, str, int], ...] = (
    ("Maria", "Rossi", 1520),
    ("Mario", "Bianchi", 1470),
    ("Anna", "Verdi", 1590),
    ("Luca", "Russo", 1440),
    ("Paola", "Ferrari", 1505),
    ("Giorgio", "Esposito", 1555),
    ("Laura", "Romano", 1460),
    ("Marco", "Colombo", 1530),
    ("Silvia", "Marino", 1485),
    ("Antonio", "Gallo", 1575),
    ("Francesca", "Costa", 1450),
    ("Roberto", "Fontana", 1515),
    ("Chiara", "Bruno", 1545),
    ("Stefano", "Rizzo", 1495),
    ("Valentina", "Lombardi", 1565),
    ("Alessandro", "Moretti", 1425),
)


def nome_fittizio(indice: int) -> tuple[str, str, int]:
    """Nome, cognome e rating del fittizio numero `indice` (da 0).

    Oltre la tabella si ricomincia da capo con un ordinale romano sul
    cognome («Rossi II»): una prova non supera i sedici iscritti nell'uso
    previsto, ma il massimo della gara lo decide il direttore e il servizio
    non deve rompersi al diciassettesimo.
    """
    nome, cognome, rating = NOMI_FITTIZI[indice % len(NOMI_FITTIZI)]
    giro = indice // len(NOMI_FITTIZI)
    if giro:
        cognome = f"{cognome} {_romano(giro + 1)}"
    return nome, cognome, rating


def _romano(n: int) -> str:
    simboli = (
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    risultato = ""
    for valore, lettera in simboli:
        while n >= valore:
            risultato += lettera
            n -= valore
    return risultato
