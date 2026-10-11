"""La fase finale dopo i gironi: le regole, senza database (piano gironi, PR 5).

Un girone all'italiana — a uno o più gironi — può avere una **fase finale**
(`Gara.final_phase_mode`):

* **nessuna**: la gara finisce coi gironi (la classifica «prima i primi, poi
  i secondi» di ADR-076);
* **tabellone**: i primi `K` di ogni girone (`Gara.qualifiers_per_group`)
  giocano un tabellone a eliminazione diretta;
* **piazzamento**: il p-esimo di un girone contro il p-esimo dell'altro
  (`incroci_per_piazzamento`), con due gironi (PR 6): ogni finale assegna
  due posti, e l'ultimo del girone più numeroso si classifica direttamente.

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
from typing import Any, Container, Dict, List, Mapping, Optional, Sequence, Tuple

from .bracket import BRACKET_PLACEMENT, BRACKET_WINNERS, bracket_levels, bracket_size
from .group_phase import seed_per_colonne

#: Quanti passano per girone se la gara non lo dice.
QUALIFICATI_PER_GIRONE_DEFAULT = 2

#: Il massimo che si può scrivere su una gara.
MASSIMO_QUALIFICATI_PER_GIRONE = 8

#: Il tabellone più piccolo: la sola finale.
TAGLIA_MINIMA = 2

#: Le finali per piazzamento si giocano fra due gironi: il p-esimo dell'uno
#: contro il p-esimo dell'altro. Con più gironi la formula resta un punto
#: aperto (ADR-076, ADR-081).
MASSIMO_GIRONI_PER_PIAZZAMENTO = 2


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


class LimiteDellaFaseFinale(str, Enum):
    """I tre stati del limite di tempo della fase finale, come li sceglie il modulo.

    Sulla gara il valore è un numero a tre stati
    (`Gara.final_phase_time_limit_minutes`): NULL come i gironi, 0 senza
    limite, N minuti. Il modulo li chiede con un menu e un campo dei minuti.
    """

    COME_I_GIRONI = "gironi"
    SENZA = "nessuno"
    MINUTI = "minuti"

    @classmethod
    def del_valore(cls, minuti: Optional[int]) -> "LimiteDellaFaseFinale":
        """Il modo che il modulo mostra per un valore salvato."""
        if minuti is None:
            return cls.COME_I_GIRONI
        return cls.MINUTI if minuti > 0 else cls.SENZA


#: Il limite più lungo che si può scrivere, in minuti: lo stesso del limite
#: della gara (`form_parser.LIMITE_DI_TEMPO_MASSIMO`).
LIMITE_MASSIMO_IN_MINUTI = 600


def limite_dal_modulo(
    modo: object, minuti: object, *, finale: bool = False
) -> Optional[int]:
    """Il valore da salvare per la scelta del modulo: None, 0 o N minuti.

    Lo stesso per il limite della sola finale (`Gara.final_time_limit_minutes`),
    dove «come i gironi» vuol dire «come la fase finale»: ``finale`` cambia
    solo il messaggio d'errore.

    Raises:
        ValueError: un modo sconosciuto, o minuti fuori da 1–600 quando si
            sceglie un limite diverso.
    """
    from flask_babel import gettext as _

    try:
        scelta = LimiteDellaFaseFinale(str(modo or "").strip())
    except ValueError:
        raise ValueError(_("Limite di tempo della fase finale sconosciuto."))
    if scelta is LimiteDellaFaseFinale.COME_I_GIRONI:
        return None
    if scelta is LimiteDellaFaseFinale.SENZA:
        return 0
    try:
        valore = int(str(minuti or "").strip())
    except ValueError:
        valore = 0
    if (valore < 1 or valore > LIMITE_MASSIMO_IN_MINUTI) and finale:
        raise ValueError(
            _(
                "Il limite di tempo della finale si scrive in minuti, da 1 a "
                "%(max)s.",
                max=LIMITE_MASSIMO_IN_MINUTI,
            )
        )
    if valore < 1 or valore > LIMITE_MASSIMO_IN_MINUTI:
        raise ValueError(
            _(
                "Il limite di tempo della fase finale si scrive in minuti, da 1 "
                "a %(max)s.",
                max=LIMITE_MASSIMO_IN_MINUTI,
            )
        )
    return valore


class DistanzaDellaFase(str, Enum):
    """I due stati della distanza della fase finale o della finale, nel modulo.

    Sulla gara il valore è un numero o NULL (`Gara.final_phase_distance`,
    `Gara.final_distance`): NULL «come i gironi» (o «come la fase finale»),
    N «al N». Il tabellone si gioca sempre al N: qualcuno deve passare.
    """

    COME_PRIMA = "come"
    ALTRA = "altra"

    @classmethod
    def del_valore(cls, distanza: Optional[int]) -> "DistanzaDellaFase":
        return cls.ALTRA if distanza else cls.COME_PRIMA


#: La distanza più lunga che si può scrivere: la stessa del modulo della gara
#: (`_distance_configurator.html`).
DISTANZA_MASSIMA = 15


def distanza_dal_modulo(
    modo: object, valore: object, *, finale: bool = False
) -> Optional[int]:
    """Il valore da salvare per la scelta del modulo: None o N.

    Args:
        finale: la distanza della sola finale, per il messaggio d'errore.

    Raises:
        ValueError: un modo sconosciuto, o una distanza fuori da 1–15.
    """
    from flask_babel import gettext as _

    try:
        scelta = DistanzaDellaFase(str(modo or "").strip())
    except ValueError:
        raise ValueError(_("Distanza del tabellone sconosciuta."))
    if scelta is DistanzaDellaFase.COME_PRIMA:
        return None
    try:
        n = int(str(valore or "").strip())
    except ValueError:
        n = 0
    if n < 1 or n > DISTANZA_MASSIMA:
        if finale:
            raise ValueError(
                _(
                    "La distanza della finale va da 1 a %(max)s triangoli.",
                    max=DISTANZA_MASSIMA,
                )
            )
        raise ValueError(
            _(
                "La distanza della fase finale va da 1 a %(max)s triangoli.",
                max=DISTANZA_MASSIMA,
            )
        )
    return n


def la_finale_del_turno(nodi: Sequence[Any]) -> Optional[Any]:
    """La partita della finale fra quelle di un turno del tabellone, o None.

    È l'unico nodo dei vincenti del turno: il tabellone si dimezza a ogni
    turno, e i bye del primo turno sono nodi pieni (ADR-038), quindi un turno
    con un solo nodo dei vincenti è la finale — anche al primo turno, quando
    i qualificati sono due. La finalina (`3P`) sta nello stesso turno e non è
    la finale: segue le regole della fase finale (decisione dell'utente del
    2026-10-12). Si guardano i soli nodi del tabellone dopo i gironi, senza
    girone.
    """
    piazzamenti = [
        n for n in nodi if getattr(n, "bracket_type", None) == BRACKET_PLACEMENT
    ]
    if piazzamenti:
        # Le finali per piazzamento: la finale è quella per il 1°/2° posto,
        # la coppia 0. Le altre seguono la fase finale, come la finalina.
        return next(
            (n for n in piazzamenti if getattr(n, "bracket_slot", None) == 0), None
        )
    vincenti = [
        n
        for n in nodi
        if getattr(n, "bracket_type", None) == BRACKET_WINNERS
        and getattr(n, "bracket_group", None) is None
    ]
    return vincenti[0] if len(vincenti) == 1 else None


def verifica_piazzamento(gironi: int) -> Optional[str]:
    """Perché le finali per piazzamento non si fanno con questi gironi, o None.

    Servono esattamente due gironi: con uno solo la gara finisce col girone
    (lo decide l'avvio, non questa funzione), con tre o più la formula non è
    ancora definita. Il motivo è una chiave, ``"gironi"``.
    """
    return None if gironi == MASSIMO_GIRONI_PER_PIAZZAMENTO else "gironi"


def incroci_per_piazzamento(
    ordine_nel_girone: Mapping[int, Sequence[int]],
) -> Tuple[List[Tuple[int, int]], List[int]]:
    """Le coppie delle finali per piazzamento, e chi si classifica diretto.

    Il p-esimo del primo girone contro il p-esimo del secondo: la coppia 0
    gioca per il 1°/2° posto, la 1 per il 3°/4°, e così via. Con gironi di
    taglia diversa chi avanza nel girone più numeroso non ha avversario e si
    classifica direttamente, dietro all'ultima coppia.

    Args:
        ordine_nel_girone: girone → giocatori dal primo all'ultimo, con tutti
            i giocatori del girone (anche chi si è ritirato: perde la sua
            finale a tavolino).

    Raises:
        ValueError: se i gironi non sono due.
    """
    if len(ordine_nel_girone) != MASSIMO_GIRONI_PER_PIAZZAMENTO:
        raise ValueError(f"finali per piazzamento con {len(ordine_nel_girone)} gironi")
    a, b = (list(ordine_nel_girone[g]) for g in sorted(ordine_nel_girone))
    n = min(len(a), len(b))
    return list(zip(a[:n], b[:n])), a[n:] + b[n:]


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
    "DISTANZA_MASSIMA",
    "DistanzaDellaFase",
    "FaseFinale",
    "LIMITE_MASSIMO_IN_MINUTI",
    "LimiteDellaFaseFinale",
    "MASSIMO_GIRONI_PER_PIAZZAMENTO",
    "MASSIMO_QUALIFICATI_PER_GIRONE",
    "QUALIFICATI_PER_GIRONE_DEFAULT",
    "TAGLIA_MINIMA",
    "distanza_dal_modulo",
    "incroci_per_piazzamento",
    "la_finale_del_turno",
    "limite_dal_modulo",
    "qualificati_dei_gironi",
    "qualificati_per_girone",
    "semina_del_tabellone",
    "taglia_del_tabellone",
    "turni_del_tabellone",
    "verifica_piazzamento",
    "verifica_qualificati",
]
