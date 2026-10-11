"""Questa gara ha un tabellone da mostrare? E in che fase è? (ADR-081)

Una domanda sola per le pagine, al posto dei controlli
``matchmaking_strategy in BRACKET_STRATEGIES`` sparsi in route, template e
modelli di vista. I tabelloni sono due:

* il **tabellone di formato** — eliminazione diretta e doppio KO, anche con
  la fase a gironi FISBB: la gara *è* un tabellone, dal sorteggio alla
  finale. La risposta non cambia mai, ed è quella di sempre;
* il **tabellone dopo i gironi** del girone all'italiana (ADR-081): la gara
  è prima una serie di gironi e poi, coi primi di ogni girone, un tabellone a
  eliminazione diretta. Da mostrare solo quando c'è: mentre si giocano i
  gironi le pagine mostrano le classifiche per girone, e con il girone unico
  il tabellone non si gioca e non compare niente.

La risposta si ricava dalla gara e dalle sue partite, **senza interrogare il
database**: i nodi del tabellone dopo i gironi sono le partite con le
coordinate del tabellone (``bracket_type``) e senza girone
(``bracket_group`` NULL); quelle dei gironi hanno il girone e non le
coordinate. Così lo schermo in sala, che non fa query, può chiederlo come la
pagina del direttore.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence

from models.matchmaking.configuration import BRACKET_STRATEGIES, MatchmakingStrategy


class FaseDellaGara(str, Enum):
    """La fase in corso in una gara che ha un tabellone."""

    #: Si giocano i gironi: il tabellone verrà dopo.
    GIRONI = "gironi"
    #: Si gioca il tabellone (o si è giocato: la gara è finita).
    TABELLONE = "tabellone"


@dataclass(frozen=True)
class TabelloneDellaGara:
    """Che tabellone ha la gara, e a che punto è."""

    #: Eliminazione diretta o doppio KO: la gara è un tabellone.
    di_formato: bool = False
    #: Girone all'italiana a più gironi col tabellone finale (ADR-081).
    dopo_i_gironi: bool = False
    #: None se la gara non ha tabellone (o non lo gioca: girone unico).
    fase: Optional[FaseDellaGara] = None
    #: I turni di gara prima del primo turno del tabellone: quelli dei
    #: gironi. Zero nel tabellone di formato. Noti solo quando il tabellone è
    #: stato sorteggiato.
    turni_prima: int = 0

    @property
    def da_mostrare(self) -> bool:
        """Le pagine mostrano il tabellone: quello di formato sempre, l'altro
        da quando è stato sorteggiato."""
        return self.fase is FaseDellaGara.TABELLONE

    @property
    def nei_gironi(self) -> bool:
        """Gara col tabellone dopo i gironi, mentre si giocano i gironi."""
        return self.dopo_i_gironi and self.fase is FaseDellaGara.GIRONI


NESSUN_TABELLONE = TabelloneDellaGara()


def _nodi_dopo_i_gironi(partite: Sequence[Any]) -> List[Any]:
    """I nodi del tabellone dopo i gironi.

    Le finali per piazzamento (`BRACKET_PLACEMENT`) hanno un tipo e niente
    girone, ma non sono un tabellone: nessuno passa a un turno dopo, e non
    c'è un albero da disegnare.
    """
    from models.matchmaking.bracket import BRACKET_PLACEMENT

    return [
        m
        for m in partite
        if getattr(m, "bracket_type", None)
        and getattr(m, "bracket_type", None) != BRACKET_PLACEMENT
        and getattr(m, "bracket_group", None) is None
    ]


def _gironi_giocati(partite: Sequence[Any]) -> int:
    """Quanti gironi hanno partite: con uno solo il tabellone non si gioca."""
    return len(
        {
            m.bracket_group
            for m in partite
            if not getattr(m, "bracket_type", None)
            and getattr(m, "bracket_group", None) is not None
        }
    )


def tabellone_della_gara(gara: Any, partite: Iterable[Any]) -> TabelloneDellaGara:
    """La risposta per questa gara, dalle sue partite.

    Args:
        gara: la gara (si leggono strategia e fase finale).
        partite: **tutte** le partite della gara, non solo quelle di chi
            guarda: con meno partite la fase sarebbe sbagliata.
    """
    strategia = getattr(gara, "matchmaking_strategy", None)
    if strategia in BRACKET_STRATEGIES:
        return TabelloneDellaGara(di_formato=True, fase=FaseDellaGara.TABELLONE)
    if strategia != MatchmakingStrategy.ROUND_ROBIN.value:
        return NESSUN_TABELLONE

    tutte = list(partite)
    nodi = _nodi_dopo_i_gironi(tutte)
    if nodi:
        primo = min(m.round_number or 1 for m in nodi)
        return TabelloneDellaGara(
            dopo_i_gironi=True,
            fase=FaseDellaGara.TABELLONE,
            turni_prima=primo - 1,
        )
    previsto = getattr(gara, "ha_tabellone_finale", False) is True
    if previsto and _gironi_giocati(tutte) >= 2:
        return TabelloneDellaGara(dopo_i_gironi=True, fase=FaseDellaGara.GIRONI)
    return NESSUN_TABELLONE


def albero_della_gara(gara: Any, partite: Iterable[Any]):
    """L'albero del tabellone da mostrare, o None se non ce n'è.

    Lo stesso `costruisci_tabellone` (ADR-038) per i due tabelloni: in quello
    dopo i gironi le colonne cominciano dopo i turni dei gironi, e la finalina
    è quella della gara.
    """
    from models.competition.tabellone_view import costruisci_tabellone

    tutte = list(partite)
    t = tabellone_della_gara(gara, tutte)
    if not t.da_mostrare:
        return None
    return costruisci_tabellone(
        tutte,
        strategy=gara.matchmaking_strategy,
        finalina=bool(getattr(gara, "third_place_match", False)),
        turni_prima=t.turni_prima,
    )


def nomi_delle_partite(gara: Any, partite: Iterable[Any]) -> Dict[int, Any]:
    """Il nome di ogni partita del tabellone, per id: «finale», «semifinali»…

    Una fonte sola per chi nomina una partita fuori dal disegno del
    tabellone — le caselle dei tavoli sullo schermo in sala, la tessera in
    dashboard («La tua partita · Semifinale»): `nome_del_nodo` sull'albero
    della gara. I nomi sono simbolici (`NomeRound`), le parole le mette il
    template. Le partite dei gironi del girone all'italiana non ci sono; nelle
    gare senza tabellone il dizionario è vuoto.

    Le **finali per piazzamento** non hanno un albero: il nome viene dalla
    coppia (`bracket_slot`), «Finale 1°/2° posto» per la 0, «Finale 3°/4°
    posto» per la 1 — `NomeRound("piazzamento", coppia + 1)`.
    """
    from models.competition.tabellone_view import NomeRound
    from models.matchmaking.bracket import BRACKET_PLACEMENT

    tutte = list(partite)
    nomi = nomi_dei_nodi(albero_della_gara(gara, tutte))
    for m in tutte:
        if (
            getattr(m, "bracket_type", None) == BRACKET_PLACEMENT
            and m.id is not None
            and m.bracket_slot is not None
        ):
            nomi[m.id] = NomeRound("piazzamento", m.bracket_slot + 1)
    return nomi


def nomi_dei_nodi(albero: Any) -> Dict[int, Any]:
    """`nomi_delle_partite` per chi ha già l'albero (None: nessun nome)."""
    from models.competition.tabellone_view import nome_del_nodo

    if albero is None:
        return {}
    return {
        n.match.id: nome_del_nodo(albero, n)
        for n in albero.nodi
        if n.match is not None and n.match.id is not None
    }


__all__ = [
    "FaseDellaGara",
    "NESSUN_TABELLONE",
    "TabelloneDellaGara",
    "albero_della_gara",
    "nomi_dei_nodi",
    "nomi_delle_partite",
    "tabellone_della_gara",
]
