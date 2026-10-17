"""L'ELO della vista «Tutte» segue le firme delle sfide (ADR-083).

Il pool ``ELO_ALL`` conta anche le sfide firmate da uno solo. Una sfida ci
**entra** alla prima firma e ci **resta** alla seconda; ne **esce** quando
torna senza firme (risultato rifiutato, triangolo tolto), con un forfait o con
un annullamento.

Perché un ascoltatore della sessione e non una chiamata nei servizi
-------------------------------------------------------------------
Le firme si scrivono in tanti punti: la firma d'ufficio di chi arriva alla
distanza (`IndividualRackService`), la conferma, il rifiuto, il triangolo
tolto, il referto TPA che si chiude, il forfait, il rifiuto per giocatore
della partita di altri due (ADR-084). Ognuno è un posto dove
dimenticarsi del rating. Qui si guarda il **risultato**: a fine transazione,
per ogni sfida toccata, si confronta «conta?» (`sfida_conta_per_elo`) con
«è già nel pool?» (`MatchRatingHistory`). È lo stesso schema di
``models/match/regole_fissate.py``.

Entrare e uscire non costano uguale
-----------------------------------
* **Entrare** è un'aggiunta in coda, come fa l'evento della seconda firma per
  ``ELO_GLOBAL``: la sfida appena firmata è quasi sempre l'ultima partita dei
  due.
* **Uscire** è un ricalcolo da zero del solo pool: l'ELO dipende dall'ordine,
  e sottrarre il delta di una partita lascerebbe sbagliati i rating di tutte
  quelle venute dopo. Succede di rado — un rifiuto, un forfait dopo la firma.

Il rating è solo da mostrare: se il suo aggiornamento fallisce, l'azione del
giocatore si salva lo stesso. Il lavoro gira in un savepoint, e un errore
finisce nel log — come negli altri gestori del rating.
"""

from __future__ import annotations

import logging
from typing import Set

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CHIAVE = "elo_tutte_sfide_toccate"

#: Le colonne che possono far entrare o uscire una sfida dal pool.
_COLONNE = (
    "status",
    "player1_confirmed",
    "player2_confirmed",
    "player1_score",
    "player2_score",
    # Il rifiuto per giocatore della partita di altri due (ADR-084).
    "player1_rejected_at",
    "player2_rejected_at",
)


def sincronizza(sfide_ids: Set[int]) -> None:
    """Allinea il pool ``ELO_ALL`` allo stato di queste sfide."""
    from models.base import db
    from models.certificazione import sfida_conta_per_elo
    from models.individual_match.match_models import IndividualMatch
    from models.rating.calculation_service import RatingCalculationService
    from models.rating.models import MatchRatingHistory, RatingSystem

    sistema = RatingSystem.ELO_ALL
    da_aggiungere = []
    uscite = False
    for sfida_id in sorted(sfide_ids):
        sfida = db.session.get(IndividualMatch, sfida_id)
        nel_pool = MatchRatingHistory.exists_for_individual_match(sfida_id, sistema)
        conta = sfida is not None and sfida_conta_per_elo(sfida)
        if conta and not nel_pool:
            da_aggiungere.append(sfida)
        elif nel_pool and not conta:
            uscite = True

    if uscite:
        # Il ricalcolo ritrova da solo anche le sfide appena entrate.
        RatingCalculationService.recalculate_all_elo_all()
        return
    for sfida in da_aggiungere:
        RatingCalculationService.process_individual_match_result(sfida, sistema)


def _dopo_il_flush(session: Session, _flush_context) -> None:
    from models.individual_match.match_models import IndividualMatch
    from models.tpa.models import TpaReferto

    toccate = session.info.setdefault(_CHIAVE, set())
    for obj in list(session.new) + list(session.dirty):
        # La partita di altri due entra nel pool quando chi la segna chiude il
        # referto (ADR-084): il fatto sta sul referto, non sulla partita.
        if isinstance(obj, TpaReferto) and obj.individual_match_id is not None:
            if inspect(obj).attrs["closed_at"].history.has_changes():
                toccate.add(obj.individual_match_id)
            continue
        if not isinstance(obj, IndividualMatch) or obj.id is None:
            continue
        stato = inspect(obj)
        if obj in session.new or any(
            stato.attrs[colonna].history.has_changes() for colonna in _COLONNE
        ):
            toccate.add(obj.id)


def _prima_del_commit(session: Session) -> None:
    from models.individual_match.match_models import IndividualMatch
    from models.tpa.models import TpaReferto

    in_sospeso = any(
        isinstance(obj, (IndividualMatch, TpaReferto))
        for obj in list(session.new) + list(session.dirty)
    )
    if not session.info.get(_CHIAVE) and not in_sospeso:
        return
    # Il flush che il commit farebbe subito dopo, fatto **qui e fuori dal
    # `try`**: un errore delle modifiche del chiamante — un vincolo violato —
    # deve arrivargli come da un commit qualsiasi. Dentro il savepoint lo
    # avrebbe inghiottito l'`except` sotto, lasciando la transazione morta.
    session.flush()
    toccate = session.info.pop(_CHIAVE, None)
    if not toccate:
        return
    from models.transaction.manager import savepoint

    try:
        with savepoint():
            sincronizza(toccate)
    except Exception:  # pragma: no cover - rete di sicurezza, vedi docstring
        logger.exception("ELO della vista Tutte non aggiornato per %s", toccate)


def _dopo_il_rollback(session: Session) -> None:
    session.info.pop(_CHIAVE, None)


_REGISTRATO = False


def registra_ascoltatore() -> None:
    """Aggancia la sincronizzazione al commit di ogni sessione. Idempotente."""
    global _REGISTRATO
    if _REGISTRATO:
        return
    event.listen(Session, "after_flush", _dopo_il_flush)
    event.listen(Session, "before_commit", _prima_del_commit)
    event.listen(Session, "after_rollback", _dopo_il_rollback)
    _REGISTRATO = True
