"""A che punto sono i playoff di un campionato terminato.

La pagina del campionato per chi lo dirige (canvas 7.1–7.4) racconta i playoff
in quattro momenti: da avviare, inviti, finale in corso, conclusi. Fino al
2026-09-13 ne distingueva solo i primi due: a finale cominciata gli invitati
restavano in pagina, e a finale conclusa la fascia diceva ancora «Inviti
chiusi · Vai alla gara playoff» invece di constatare che il campionato è
concluso.

«Conclusi» usa gli stessi fatti di `compute_campionato_status` quando dice
Completato (`models/campionato/statistics_service.py`): ogni configurazione
attiva ha una gara non eliminata e conclusa. Le due risposte non possono
divergere, e il test le confronta. Nessuno stato nuovo e nessuna chiusura in
più: a playoff finiti la pagina constata (SPECIFICHE.md, «Stati di un
campionato»).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from models.status_enum import GaraStatus


class FasePlayoff(str, Enum):
    DA_AVVIARE = "da_avviare"
    INVITI = "inviti"
    IN_CORSO = "in_corso"
    CONCLUSI = "conclusi"


#: La gara di playoff non è ancora cominciata.
_PRIMA_DEL_VIA = (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value)


def fase_playoff(campionato: Any) -> Optional[FasePlayoff]:
    """La fase dei playoff, o `None` se il campionato non è in fase playoff.

    Non è in fase playoff un campionato non ancora terminato, o senza
    configurazioni. Poi, dal più avanzato al meno:

    * **conclusi**: ogni configurazione attiva ha la sua gara, conclusa;
    * **in corso**: almeno una gara di playoff è partita — gli inviti sono
      chiusi e non vanno più mostrati;
    * **inviti**: gli inviti sono partiti, nessuna gara è ancora avviata;
    * **da avviare**: nessun invito.
    """
    if not getattr(campionato, "terminated_at", None):
        return None
    if not campionato.has_playoff_configurations():
        return None

    attive = [c for c in (campionato.playoff_configurations or []) if c.is_active]
    gare = [c.gara for c in attive if c.gara is not None and not c.gara.is_deleted]

    if (
        attive
        and len(gare) == len(attive)
        and all(g.status == GaraStatus.COMPLETED.value for g in gare)
    ):
        return FasePlayoff.CONCLUSI
    if any((g.current_round or 0) > 0 or g.status not in _PRIMA_DEL_VIA for g in gare):
        return FasePlayoff.IN_CORSO
    if any(q.invited_at is not None for c in attive for q in (c.qualifications or [])):
        return FasePlayoff.INVITI
    return FasePlayoff.DA_AVVIARE


__all__ = ["FasePlayoff", "fase_playoff"]
