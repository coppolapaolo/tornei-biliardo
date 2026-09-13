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
    """Una zona per ogni configurazione playoff attiva del campionato.

    Prima degli inviti la zona e' chi `PlayoffService.candidati_per_posizione`
    sceglierebbe adesso — la stessa funzione di `start_playoff`, fascia di
    posizioni e rimpiazzi compresi — dalle righe `Classification` gia'
    calcolate, senza scrivere niente. Le configurazioni senza fascia (criteri
    JSON) ripiegano su `evaluate_qualifications`, come `start_playoff`.

    Gli inviti sono «partiti» quando almeno una qualificazione ha `invited_at`:
    le righe possono esistere prima della notifica. Dopo, la zona e' chi ha un
    invito valido: confermato, o in attesa e non ancora scaduto — la pagina
    pubblica non fa scadere gli inviti, quindi la scadenza si guarda qui.
    """
    from models.base import utc_now
    from models.classification.models import Classification
    from models.playoff.models import (
        PlayoffConfiguration,
        PlayoffQualification,
        QualificationStatus,
    )
    from models.playoff.services import PlayoffService

    configurazioni = (
        PlayoffConfiguration.query.filter_by(
            campionato_id=campionato.id, is_active=True
        )
        .order_by(PlayoffConfiguration.id)
        .all()
    )
    adesso = utc_now()
    classifica = None
    zone: List[ZonaPlayoff] = []
    for cfg in configurazioni:
        invitate = [
            q
            for q in PlayoffQualification.query.filter_by(configuration_id=cfg.id).all()
            if q.invited_at is not None
        ]
        if invitate:
            dentro = frozenset(
                q.user_id
                for q in invitate
                if q.status == QualificationStatus.CONFIRMED
                or (
                    q.status == QualificationStatus.PENDING
                    and (q.expires_at is None or q.expires_at > adesso)
                )
            )
            partiti = True
        elif cfg.positions_from is not None and cfg.positions_to is not None:
            if classifica is None:
                classifica = (
                    Classification.query.filter_by(campionato_id=campionato.id)
                    .order_by(Classification.position)
                    .all()
                )
            dentro = frozenset(
                user_id
                for user_id, _pos, _motivo in PlayoffService.candidati_per_posizione(
                    cfg, classifica
                )
            )
            partiti = False
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
