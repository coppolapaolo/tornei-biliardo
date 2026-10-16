"""Chi dirige una gara: il titolare e i co-direttori, in un elenco solo.

Il titolare non sta dove stanno i co-direttori. `Gara.directors` legge le
assegnazioni sulla **gara**, cioè i co-direttori; il titolare è
`gara.director_id` in una gara singola, e i direttori del **campionato** in
una gara di campionato (gli stessi che `PermissionChecker.can_manage_competition`
lascia gestire la gara). Chi leggeva solo `gara.directors` mostrava come
organizzatore il co-direttore e non il direttore: la vetrina, fino al
16/10/2026.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class Direttore:
    utente: Any
    #: Il titolare della gara (o un direttore del campionato), non un
    #: co-direttore aggiunto sulla gara.
    titolare: bool


def direzione_della_gara(gara: Any) -> List[Direttore]:
    """I titolari prima, poi i co-direttori; ognuno una volta sola."""
    titolari: List[Any] = []
    if getattr(gara, "campionato_id", None):
        campionato = getattr(gara, "campionato", None)
        titolari = list(getattr(campionato, "directors", None) or [])
    elif getattr(gara, "director", None) is not None:
        titolari = [gara.director]

    elenco: List[Direttore] = []
    visti = set()
    for utente, titolare in [(u, True) for u in titolari] + [
        (u, False) for u in (getattr(gara, "directors", None) or [])
    ]:
        if utente.id in visti:
            continue
        visti.add(utente.id)
        elenco.append(Direttore(utente=utente, titolare=titolare))
    return elenco


__all__ = ["Direttore", "direzione_della_gara"]
