"""La fase finale dopo i gironi: le regole, senza database (piano gironi, PR 5).

Un girone all'italiana — a uno o più gironi — può avere una **fase finale**
(`Gara.final_phase_mode`):

* **nessuna**: la gara finisce coi gironi (la classifica «prima i primi, poi
  i secondi» di ADR-076);
* **tabellone**: i primi `K` di ogni girone (`Gara.qualifiers_per_group`)
  giocano un tabellone a eliminazione diretta;
* **piazzamento**: il p-esimo di un girone contro il p-esimo dell'altro. Il
  valore esiste, la formula arriva con la PR 6.

Quattro domande, quattro risposte di questo modulo, tutte sul tabellone:

1. **Si può fare?** (`verifica_qualificati`): almeno un qualificato per
   girone, non più di quanti ne ha il girone più piccolo, e almeno due in
   tutto, perché un tabellone con un giocatore solo non è una partita.
2. **Quanto è grande** (`taglia_del_tabellone`, `turni_del_tabellone`): la
   potenza di 2 subito sopra i qualificati, come il tabellone a eliminazione
   diretta (ADR-038), ma da 2 in su: con due gironi e un qualificato per
   girone si gioca la sola finale.
3. **Chi passa** (`qualificati_dei_gironi`): i primi `K` di ogni girone fra
   chi è ancora in gara. Chi si è ritirato non va al tabellone: passa il
   successivo del suo girone.
4. **Con che ordine entrano** (`semina_del_tabellone`): per colonne, prima
   tutti i primi, poi tutti i secondi; dentro la colonna i migliori, cioè
   l'ordine della classifica a gironi (per partita giocata). I bye, quando i
   qualificati non sono una potenza di 2, vanno alle prime teste di serie:
   con tre gironi e due qualificati, ai due migliori primi. Che due
   qualificati dello stesso girone non si incontrino subito lo decide la
   strategia, separandoli come fa il tabellone finale della formula FISBB.
"""

from __future__ import annotations

from enum import Enum
from typing import Container, Dict, List, Mapping, Optional, Sequence

from .bracket import bracket_levels, bracket_size
from .group_phase import seed_per_colonne

#: Quanti passano per girone se la gara non lo dice.
QUALIFICATI_PER_GIRONE_DEFAULT = 2

#: Il massimo che si può scrivere su una gara.
MASSIMO_QUALIFICATI_PER_GIRONE = 8

#: Il tabellone più piccolo: la sola finale.
TAGLIA_MINIMA = 2


class FaseFinale(str, Enum):
    """Cosa si gioca dopo i gironi."""

    NESSUNA = "nessuna"
    TABELLONE = "tabellone"
    PIAZZAMENTO = "piazzamento"

    def __str__(self) -> str:  # pragma: no cover – banale
        return str(self.value)

    @classmethod
    def resolve(cls, valore: object) -> "FaseFinale":
        """Il valore salvato, o «nessuna» se manca o non si riconosce."""
        try:
            return cls(str(getattr(valore, "value", valore)))
        except ValueError:
            return cls.NESSUNA


def qualificati_per_girone(valore: object) -> int:
    """Il `K` della gara, letto con tolleranza: assente o non valido vale 2."""
    try:
        k = int(valore) if valore is not None else QUALIFICATI_PER_GIRONE_DEFAULT
    except (TypeError, ValueError):
        return QUALIFICATI_PER_GIRONE_DEFAULT
    return max(1, min(k, MASSIMO_QUALIFICATI_PER_GIRONE))


def verifica_qualificati(taglie: Sequence[int], k: int) -> Optional[str]:
    """Perché il tabellone non si fa con questi gironi, o None se si fa.

    Il motivo è una chiave (``"minimo"``, ``"girone"``, ``"pochi"``): le
    parole le mette chi lo mostra.
    """
    if k < 1:
        return "minimo"
    if not taglie or k > min(taglie):
        return "girone"
    if k * len(taglie) < TAGLIA_MINIMA:
        return "pochi"
    return None


def taglia_del_tabellone(qualificati: int) -> int:
    """La taglia del tabellone: la potenza di 2 subito sopra, almeno 2."""
    if qualificati < 1:
        raise ValueError(f"tabellone senza qualificati: {qualificati}")
    return max(TAGLIA_MINIMA, bracket_size(qualificati))


def turni_del_tabellone(qualificati: int) -> int:
    """I turni del tabellone: semifinali e finale con quattro qualificati.

    La finalina si gioca nello stesso turno della finale e non ne aggiunge.
    """
    return bracket_levels(taglia_del_tabellone(qualificati))


def qualificati_dei_gironi(
    ordine_nel_girone: Mapping[int, Sequence[int]],
    k: int,
    in_gara: Container[int],
) -> Dict[int, List[int]]:
    """I primi `k` di ogni girone fra chi è ancora in gara.

    Args:
        ordine_nel_girone: girone → giocatori dal primo all'ultimo.
        k: quanti passano per girone.
        in_gara: chi può giocare il tabellone (non ritirato, non escluso).
    """
    return {
        girone: [pid for pid in ordine if pid in in_gara][:k]
        for girone, ordine in ordine_nel_girone.items()
    }


def semina_del_tabellone(
    qualificati: Mapping[int, Sequence[int]],
    ordine_della_gara: Sequence[int],
) -> List[int]:
    """I qualificati in ordine di testa di serie, per colonne.

    Args:
        qualificati: girone → qualificati, dal primo.
        ordine_della_gara: la classifica a gironi, dal primo all'ultimo: dice
            chi è migliore dentro una colonna. Chi non c'è va in fondo alla
            sua colonna.
    """
    posto = {pid: i for i, pid in enumerate(ordine_della_gara)}
    fondo = len(posto)
    return seed_per_colonne(
        [list(qualificati[g]) for g in sorted(qualificati)],
        column_key=lambda pid: (posto.get(pid, fondo), pid),
    )


__all__ = [
    "FaseFinale",
    "MASSIMO_QUALIFICATI_PER_GIRONE",
    "QUALIFICATI_PER_GIRONE_DEFAULT",
    "TAGLIA_MINIMA",
    "qualificati_dei_gironi",
    "qualificati_per_girone",
    "semina_del_tabellone",
    "taglia_del_tabellone",
    "turni_del_tabellone",
    "verifica_qualificati",
]
