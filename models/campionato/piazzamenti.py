"""Come una gara entra nel campionato: sommando i totali, o col piazzamento.

Un campionato decide due cose diverse, che fino al 2026-10-11 coincidevano:

* **come si classifica ogni gara** — il sistema della serata (vittorie,
  triangoli, punti; sul tabellone il piazzamento);
* **come la gara entra nella classifica generale** — sommando i suoi totali
  (vittorie, triangoli o punti), oppure col suo **piazzamento**, tradotto in
  punti dalla tabella del campionato (`position_points.py`).

I campionati **a piazzamenti** (`default_classification_system = POSITION`,
o un campionato a tabellone nato prima che il sistema si scegliesse)
ammettono gare di qualunque formato — Amalfi, casuale, girone all'italiana,
a uno o più gironi, tabellone — perché ognuna produce una classifica finale
completa. Il sistema della gara serve solo a ordinare quella serata, e lo
propone il campionato (`default_gara_classification_system`; NULL =
vittorie). Gli altri campionati **sommano i totali**: le gare hanno tutte il
sistema del campionato e restano a girone unico, perché in un girone più
numeroso si gioca una partita in più (SPECIFICHE.md, nota del 2026-10-11).

Stesso spirito di ADR-047, un livello più su: là il tipo di campionato non
decideva più la classifica, qui il sistema della gara non decide più come
la gara entra nel campionato (ADR-080).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.matchmaking.configuration import (
    BRACKET_STRATEGIES,
    MatchmakingStrategy,
    resolve_classification_system,
)
from models.status_enum import ClassificationSystem

#: I tipi di campionato che sono a piazzamenti anche senza il sistema scritto:
#: i campionati a tabellone nati prima che POSITION si potesse scegliere.
TIPI_A_TABELLONE = frozenset(BRACKET_STRATEGIES)

#: I sistemi con cui si ordina una serata che non è un tabellone.
SISTEMI_DELLA_SERATA = (
    ClassificationSystem.WINS.value,
    ClassificationSystem.RACK.value,
    ClassificationSystem.POINTS.value,
)

#: Le strategie che un campionato che somma i totali propone alle gare: tutte
#: tranne il tabellone, che ha solo il piazzamento.
STRATEGIE_DEI_TOTALI = (
    MatchmakingStrategy.AMALFI.value,
    MatchmakingStrategy.RANDOM.value,
    MatchmakingStrategy.ROUND_ROBIN.value,
)


def e_a_piazzamenti(campionato: Any) -> bool:
    """Se le gare entrano nella classifica generale col loro piazzamento."""
    if campionato is None:
        return False
    if getattr(campionato, "campionato_type", None) in TIPI_A_TABELLONE:
        return True
    return (
        ClassificationSystem.normalize(
            getattr(campionato, "default_classification_system", None)
        )
        == ClassificationSystem.POSITION
    )


def somma_i_totali(campionato: Any) -> bool:
    """Se il campionato somma i totali delle gare (vittorie, triangoli, punti)."""
    return campionato is not None and not e_a_piazzamenti(campionato)


def sistema_della_serata(valore: Any) -> str:
    """Un sistema con cui si ordina una serata: WINS, RACK o POINTS."""
    sistema = ClassificationSystem.resolve(valore).value
    return (
        sistema if sistema in SISTEMI_DELLA_SERATA else ClassificationSystem.WINS.value
    )


def sistema_delle_gare(campionato: Any) -> str:
    """Il sistema che il campionato propone alle sue gare non a tabellone.

    Se somma i totali, il suo: tutte le gare contano la stessa cosa. Se è a
    piazzamenti, quello scelto per le serate (di norma vittorie).
    """
    if campionato is None:
        return ClassificationSystem.WINS.value
    if e_a_piazzamenti(campionato):
        return sistema_della_serata(
            getattr(campionato, "default_gara_classification_system", None)
        )
    return sistema_della_serata(
        getattr(campionato, "default_classification_system", None)
    )


def sistema_per_la_gara(
    campionato: Any, strategia: Any, richiesto: Optional[str] = None
) -> str:
    """Il sistema di una gara del campionato, data la sua strategia.

    Sul tabellone è il piazzamento. Altrimenti: se il campionato somma i
    totali, il suo, qualunque cosa si chieda; se è a piazzamenti, quello
    chiesto per la gara o, senza, quello proposto.
    """
    strategia = getattr(strategia, "value", strategia)
    if somma_i_totali(campionato) or not richiesto:
        richiesto = sistema_delle_gare(campionato)
    return resolve_classification_system(strategia, sistema_della_serata(richiesto))


def sistema_del_campionato(tipo: Any, richiesto: Any) -> str:
    """Il sistema del campionato, coerente col tipo che propone alle gare.

    Un campionato che propone il tabellone è a piazzamenti: le sue gare non
    hanno totali da sommare.
    """
    tipo = getattr(tipo, "value", tipo)
    if tipo in TIPI_A_TABELLONE:
        return ClassificationSystem.POSITION.value
    return ClassificationSystem.resolve(richiesto).value


def strategie_per_sistema() -> Dict[str, List[str]]:
    """Quali strategie il campionato può proporre, per ogni suo sistema.

    Serve ai moduli del campionato: a piazzamenti tutte, sommando i totali
    tutte tranne il tabellone.
    """
    tutte = [s.value for s in MatchmakingStrategy]
    mappa: Dict[str, List[str]] = {
        s: list(STRATEGIE_DEI_TOTALI) for s in SISTEMI_DELLA_SERATA
    }
    mappa[ClassificationSystem.POSITION.value] = tutte
    return mappa


def gironi_ammessi(gara: Any) -> bool:
    """Se questa gara può giocarsi a più gironi.

    Sempre, tranne in un campionato che somma i totali: lì chi capita nel
    girone più numeroso gioca una partita in più, e i totali non si
    confrontano. Fa eccezione la finale dei playoff che decide da sola la
    classifica finale (peso zero): di lei conta solo l'ordine d'arrivo.
    """
    campionato = getattr(gara, "campionato", None)
    if campionato is None:
        return True
    if not somma_i_totali(campionato):
        return True
    return getattr(gara, "classification_weight", 1) == 0


__all__ = [
    "SISTEMI_DELLA_SERATA",
    "STRATEGIE_DEI_TOTALI",
    "TIPI_A_TABELLONE",
    "e_a_piazzamenti",
    "gironi_ammessi",
    "sistema_del_campionato",
    "sistema_della_serata",
    "sistema_delle_gare",
    "sistema_per_la_gara",
    "somma_i_totali",
    "strategie_per_sistema",
]
