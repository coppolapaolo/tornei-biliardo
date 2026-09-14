"""Com'è finito un campionato: se è concluso, chi l'ha vinto, chi ha vinto le gare.

Canvas «campionato-concluso» (forma A, 2026-09-14): la vetrina e la pagina del
direttore mettono il campione in cima, con secondo e terzo sotto, e ogni gara
conclusa dice chi l'ha vinta. Le due pagine leggono da qui, così non possono
dire due cose diverse.

Tre scelte, tutte deliberate:

* **concluso** è un campionato terminato che non ha playoff da giocare —
  nessuna configurazione, oppure playoff conclusi (`fase_playoff`). Durante la
  fase playoff non si sa ancora chi vince, e la pagina non lo deve dire;
* il **campione** è il primo della classifica generale calcolata
  (`calculate_general_classification`), che applica già la modalità di
  classifica finale (ADR-053). **Non** è il vincitore della gara di playoff:
  con «campionato + playoff» la finale si somma alla stagione, e chi la vince
  può restare secondo. È la stessa classifica che la pagina mostra sotto, quindi
  il nome in cima e la prima riga coincidono sempre;
* le posizioni si prendono come la classifica le dà: quella calcolata numera
  in sequenza e non espone pari merito.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.base import db
from models.competition.showcase_view import gara_ha_finito
from models.playoff.fase import FasePlayoff, fase_playoff

#: Il campione più secondo e terzo.
POSTI_DEL_PODIO = 3


@dataclass(frozen=True)
class PostoPodio:
    """Un posto sul podio del campionato."""

    posizione: int
    user_id: Optional[int]
    nome: str

    @property
    def iniziali(self) -> str:
        """Come le mostra l'avatar in tutta l'app: le prime due lettere."""
        return self.nome[:2].upper()


def campionato_concluso(campionato: Any) -> bool:
    """Il campionato è finito e si sa chi l'ha vinto?

    Terminato **e** senza playoff da giocare. `fase_playoff` risponde `None`
    per un campionato terminato senza configurazioni: la stessa regola con
    cui la pagina del direttore decide se mostrare la fase playoff, quindi le
    due non possono divergere.
    """
    if not getattr(campionato, "terminated_at", None):
        return False
    return fase_playoff(campionato) in (None, FasePlayoff.CONCLUSI)


def podio_da_classifica(
    classifica: Optional[Sequence[Tuple[int, Dict[str, Any]]]],
) -> List[PostoPodio]:
    """I primi tre di `calculate_general_classification`, così come li ordina."""
    return [
        PostoPodio(
            posizione=posizione,
            user_id=dati.get("user_id"),
            nome=str(dati.get("username") or "—"),
        )
        for posizione, dati in list(classifica or [])[:POSTI_DEL_PODIO]
    ]


def vincitori_delle_gare(gare: Iterable[Any]) -> Dict[int, str]:
    """Chi ha vinto ciascuna gara conclusa, in **una** query.

    Si legge la riga in prima posizione della classifica dell'ultimo turno,
    che è la stessa fonte che la pagina della gara mostra davvero. Batchare
    sulle coppie `(gara_id, ultimo_turno)` invece di interrogare gara per gara
    è ciò che tiene le pagine a query costanti anche su un campionato di
    dodici prove: la vetrina la aprono i crawler, e un N+1 qui si paga a ogni
    passaggio.
    """
    from sqlalchemy import tuple_
    from sqlalchemy.orm import joinedload
    from models.classification.models import RoundClassification

    coppie = [
        (g.id, g.rounds_count) for g in gare if gara_ha_finito(g) and g.rounds_count
    ]
    if not coppie:
        return {}

    righe = (
        db.session.query(RoundClassification)
        .filter(
            tuple_(RoundClassification.gara_id, RoundClassification.round_number).in_(
                coppie
            ),
            RoundClassification.position == 1,
        )
        .options(joinedload(RoundClassification.user))
        .all()
    )
    vincitori = {}
    for riga in righe:
        if riga.user is not None:
            nome = getattr(riga.user, "display_name", None) or riga.user.username
            vincitori[riga.gara_id] = nome
    return vincitori


__all__ = [
    "POSTI_DEL_PODIO",
    "PostoPodio",
    "campionato_concluso",
    "podio_da_classifica",
    "vincitori_delle_gare",
]
