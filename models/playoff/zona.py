"""La zona playoff nella classifica generale (canvas 7.1 e 7.3).

La classifica generale del campionato segna chi andrebbe ai playoff: una
barra sulle righe dentro la zona, un'etichetta sopra la prima e «fuori dai
playoff» dopo l'ultima. La domanda e' «chi viene invitato?», e la risposta
la da' il dominio, non un «primi N» scritto nel template:

* **prima degli inviti** e' chi `PlayoffConfiguration.evaluate_qualifications`
  sceglierebbe adesso, con i suoi criteri (posti, gare minime, fasce);
* **dopo gli inviti** e' chi ha un invito ancora valido, in attesa o
  confermato: chi ha rifiutato esce, e chi e' entrato al suo posto c'e'.

`evaluate_qualifications` legge le righe `Classification`, la pagina mostra
`calculate_general_classification`: sono i due percorsi della classifica
generale, e il test li confronta (vedi `test_zona_playoff.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, List


@dataclass(frozen=True)
class ZonaPlayoff:
    nome: str
    posti: int
    user_ids: FrozenSet[int]
    inviti_partiti: bool


def zone_playoff(campionato) -> List[ZonaPlayoff]:
    """Una zona per ogni configurazione playoff attiva del campionato."""
    from models.playoff.models import (
        PlayoffConfiguration,
        PlayoffQualification,
        QualificationStatus,
    )

    configurazioni = (
        PlayoffConfiguration.query.filter_by(
            campionato_id=campionato.id, is_active=True
        )
        .order_by(PlayoffConfiguration.id)
        .all()
    )
    zone: List[ZonaPlayoff] = []
    for cfg in configurazioni:
        qualificazioni = PlayoffQualification.query.filter_by(
            configuration_id=cfg.id
        ).all()
        if qualificazioni:
            dentro = frozenset(
                q.user_id
                for q in qualificazioni
                if q.status
                in (QualificationStatus.PENDING, QualificationStatus.CONFIRMED)
            )
            partiti = True
        else:
            dentro = frozenset(d["user_id"] for d in cfg.evaluate_qualifications())
            partiti = False
        zone.append(
            ZonaPlayoff(
                nome=cfg.name,
                posti=cfg.max_participants,
                user_ids=dentro,
                inviti_partiti=partiti,
            )
        )
    return zone


__all__ = ["ZonaPlayoff", "zone_playoff"]
