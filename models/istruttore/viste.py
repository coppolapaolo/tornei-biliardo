"""«I miei istruttori» e «I miei allievi»: una riga letta dai due lati.

Entrambe le pagine rispondono alla stessa domanda — *quali schede legge chi* —
e cambia solo da che parte la si guarda. Per questo il lavoro vero lo fa una
funzione sola, `_legami`, e le due pubbliche dicono soltanto quale colonna è
la persona e quale è «l'altro».

Due scelte che si vedono nei risultati:

* entrano solo le schede **attive**. Una archiviata è uscita dall'elenco del
  suo proprietario, e continuare a mostrarla all'istruttore vorrebbe dire
  mandarlo a guardare un allenamento che non si fa più. Il permesso non si
  tocca: se la scheda tornasse, tornerebbe anche il legame;
* l'ordine è quello in cui i permessi sono stati dati, dal più vecchio. Chi ti
  segue da settembre sta sopra chi è arrivato ieri — e un elenco che si
  riordina da sé a ogni apertura non è un elenco.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

from ..base import db
from ..training_sheet.models import TrainingSheet, TrainingSheetReader
from ..user.models import User


@dataclass(frozen=True)
class Legame:
    """Una persona, e le schede che vi legano a lei.

    Dalla parte dell'allievo la persona è l'istruttore; dalla parte
    dell'istruttore è l'allievo. Le schede sono sempre quelle **dell'allievo**:
    è lui che le possiede, in tutti e due i casi.
    """

    persona: User
    schede: List[TrainingSheet]
    dal: datetime

    @property
    def quante(self) -> int:
        return len(self.schede)


def _legami(*, chiave, condizione) -> List[Legame]:
    """Raggruppa i permessi correnti per persona, in ordine di concessione.

    ``chiave`` dice quale colonna del permesso è «l'altra persona»;
    ``condizione`` restringe la query al lato che interessa.
    """
    righe: List[Tuple[TrainingSheetReader, TrainingSheet]] = (
        db.session.query(TrainingSheetReader, TrainingSheet)
        .join(TrainingSheet, TrainingSheet.id == TrainingSheetReader.sheet_id)
        .filter(
            TrainingSheetReader.revoked_at.is_(None),
            TrainingSheet.is_active.is_(True),
            condizione,
        )
        .order_by(TrainingSheetReader.granted_at.asc(), TrainingSheetReader.id.asc())
        .all()
    )
    if not righe:
        return []

    # Le persone in una query sola, e non una per riga: `User.query` porta con
    # sé il filtro sulle anonimizzate, che così restano fuori da entrambe le
    # pagine senza doverlo ricordare qui.
    ids = {chiave(permesso, scheda) for permesso, scheda in righe}
    persone: Dict[int, User] = {
        utente.id: utente for utente in User.query.filter(User.id.in_(ids)).all()
    }

    ordine: List[int] = []
    schede: Dict[int, List[TrainingSheet]] = {}
    dal: Dict[int, datetime] = {}
    for permesso, scheda in righe:
        persona_id = chiave(permesso, scheda)
        if persona_id not in persone:
            continue
        if persona_id not in schede:
            ordine.append(persona_id)
            schede[persona_id] = []
            dal[persona_id] = permesso.granted_at
        schede[persona_id].append(scheda)

    return [
        Legame(persona=persone[pid], schede=schede[pid], dal=dal[pid]) for pid in ordine
    ]


def istruttori_di(user_id: int) -> List[Legame]:
    """Chi legge le schede di questo giocatore, e quali.

    Un istruttore compare perché gli è stata aperta almeno una scheda, e
    sparisce quando gli si toglie l'ultima: non c'è un elenco a parte da tenere
    in pari.
    """
    return _legami(
        chiave=lambda permesso, scheda: permesso.user_id,
        condizione=TrainingSheet.owner_id == user_id,
    )


def allievi_di(instructor_id: int) -> List[Legame]:
    """Di chi questo istruttore legge le schede, e quali."""
    return _legami(
        chiave=lambda permesso, scheda: scheda.owner_id,
        condizione=TrainingSheetReader.user_id == instructor_id,
    )
