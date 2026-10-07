"""Quanto vale un risultato nella classifica a punti (ADR-078, emendamento).

Il sistema `ClassificationSystem.POINTS` ordina **solo sui punti**: ogni
partita ne dà un certo numero a seconda dell'esito, e fra chi è a pari punti
decide la catena degli spareggi. Quanti punti valgono vittoria, pareggio e
sconfitta lo sceglie la gara (di norma 3, 1 e 0); il campionato lo propone
alle sue gare, che lo ricevono quando nascono (ADR-075).

Le regole sugli esiti, scritte in SPECIFICHE.md, «Classifica»:

- la **X** vale una vittoria (anche quella con l'esercizio, che in più porta
  la differenza pari al punteggio della prova);
- il **pareggio** — esattamente N triangoli pari, o una partita interrotta a
  tempo a parità fuori dal tabellone (ADR-077) — dà i punti del pareggio;
- nel **trio** con un vincitore, lui prende la vittoria e gli altri due la
  sconfitta; senza vincitore, chi è a pari merito in testa prende il pareggio
  e il terzo, se è staccato, la sconfitta.

Un posto solo per i tre numeri: chi aggrega (`ScoreAggregator`), chi li mostra
e chi li scrive nel regolamento li leggono da qui.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from flask_babel import gettext as _

#: Il punteggio più alto che si può dare a un risultato.
PUNTI_MASSIMO = 99


@dataclass(frozen=True)
class Punti:
    """I punti di una vittoria, di un pareggio e di una sconfitta."""

    vittoria: int = 3
    pareggio: int = 1
    sconfitta: int = 0

    def come_tupla(self) -> tuple[int, int, int]:
        return (self.vittoria, self.pareggio, self.sconfitta)


#: Il default dell'app: 3 la vittoria, 1 il pareggio, 0 la sconfitta.
PUNTI_DEFAULT = Punti()

#: Le colonne della gara e quelle che il campionato propone, nell'ordine
#: vittoria, pareggio, sconfitta.
COLONNE_DELLA_GARA = ("points_win", "points_draw", "points_loss")
COLONNE_PROPOSTE = (
    "default_points_win",
    "default_points_draw",
    "default_points_loss",
)


def _intero(valore: Any) -> Optional[int]:
    if valore is None or isinstance(valore, bool):
        return None
    try:
        return int(valore)
    except (TypeError, ValueError):
        return None


def punti_proposti(campionato: Any) -> Punti:
    """I punti che il campionato propone alle sue gare (o il default)."""
    valori = [
        _intero(getattr(campionato, colonna, None)) if campionato is not None else None
        for colonna in COLONNE_PROPOSTE
    ]
    default = PUNTI_DEFAULT.come_tupla()
    return Punti(*(v if v is not None else d for v, d in zip(valori, default)))


def punti_della_gara(gara: Any) -> Punti:
    """I punti della gara: i suoi, o quelli del campionato, o il default.

    La gara li riceve quando nasce (ADR-075), quindi di norma sono i suoi; il
    ripiego sul campionato serve solo alle gare nate prima della classifica a
    punti, e una gara singola senza valori vale il default dell'app.
    """
    proposti = punti_proposti(getattr(gara, "campionato", None))
    valori = [_intero(getattr(gara, colonna, None)) for colonna in COLONNE_DELLA_GARA]
    return Punti(
        *(v if v is not None else d for v, d in zip(valori, proposti.come_tupla()))
    )


def valida_punti(vittoria: Any, pareggio: Any, sconfitta: Any) -> Punti:
    """I tre punteggi, se sono ammessi; altrimenti `ValueError` da mostrare.

    Interi da 0 a `PUNTI_MASSIMO`, in ordine: una vittoria vale almeno un
    pareggio, un pareggio almeno una sconfitta, e la vittoria più della
    sconfitta — altrimenti vincere e perdere darebbero la stessa classifica.
    """
    numeri = [_intero(v) for v in (vittoria, pareggio, sconfitta)]
    if any(n is None or n < 0 or n > PUNTI_MASSIMO for n in numeri):
        raise ValueError(
            _(
                "I punti di vittoria, pareggio e sconfitta sono numeri interi "
                "da 0 a %(max)s.",
                max=PUNTI_MASSIMO,
            )
        )
    v, p, s = (int(n) for n in numeri if n is not None)
    if not (v >= p >= s and v > s):
        raise ValueError(
            _(
                "La vittoria deve valere più della sconfitta, e il pareggio "
                "stare fra le due."
            )
        )
    return Punti(v, p, s)


def descrivi_punti(punti: Punti) -> str:
    """La frase del regolamento: «3 punti la vittoria, 1 il pareggio, …»."""
    return _(
        "%(v)s punti la vittoria, %(p)s il pareggio, %(s)s la sconfitta",
        v=punti.vittoria,
        p=punti.pareggio,
        s=punti.sconfitta,
    )


__all__ = [
    "COLONNE_DELLA_GARA",
    "COLONNE_PROPOSTE",
    "PUNTI_DEFAULT",
    "PUNTI_MASSIMO",
    "Punti",
    "descrivi_punti",
    "punti_della_gara",
    "punti_proposti",
    "valida_punti",
]
