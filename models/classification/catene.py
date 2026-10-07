"""Quale catena vale, e le partite dello scontro diretto (ADR-078).

Il motore (`ordinamento.py`) è puro; qui si leggono dal database le due cose
che gli servono e che solo la gara o il campionato sanno:

- **la catena** di ogni livello, normalizzata;
- **gli scontri**, cioè le partite a due chiuse, se la catena ha lo scontro
  diretto. Si caricano solo in quel caso: chi non usa il criterio non paga la
  query.

Un posto solo, così la classifica di turno, quella di gara, la ricerca dei pari
da spareggiare e la classifica generale leggono la stessa catena.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

from models.status_enum import ClassificationSystem, MatchStatus

from .ordinamento import (
    SSR_FINO_AL_DEFAULT,
    Catena,
    Criterio,
    Livello,
    Scontro,
    catena_di_default,
    normalizza_catena,
)


def sistema_della_gara(gara: Any) -> ClassificationSystem:
    """Il sistema della gara, ma per la catena: POSITION ripiega su WINS.

    Nel sistema POSITION la catena non si usa (ADR-040); ci si arriva solo
    per una gara a tabellone senza tabellone persistito, e lì l'ordine per
    vittorie è meglio di una classifica tutta a pari.
    """
    sistema = ClassificationSystem.resolve(getattr(gara, "classification_system", None))
    return sistema if ordina_con_la_catena(sistema) else ClassificationSystem.WINS


def sistema_dichiarato(gara: Any) -> ClassificationSystem:
    return ClassificationSystem.resolve(getattr(gara, "classification_system", None))


def ordina_con_la_catena(sistema: ClassificationSystem) -> bool:
    """Se quel sistema si ordina con la catena. POSITION no (ADR-040)."""
    return sistema in (ClassificationSystem.WINS, ClassificationSystem.RACK)


def ssr_fino_al_della_gara(gara: Any) -> Optional[int]:
    """Fin dove la gara scioglie i pari merito con lo spareggio, o None."""
    if not getattr(gara, "tiebreaker_enabled", False):
        return None
    return getattr(gara, "tiebreaker_until_position", None) or SSR_FINO_AL_DEFAULT


def catena_di_turno(gara: Any) -> Catena:
    sistema = sistema_della_gara(gara)
    return normalizza_catena(
        catena_di_default(Livello.TURNO, sistema), Livello.TURNO, sistema
    )


def catena_di_gara(gara: Any) -> Catena:
    sistema = sistema_della_gara(gara)
    catena = catena_di_default(
        Livello.GARA, sistema, ssr_fino_al=ssr_fino_al_della_gara(gara)
    )
    return normalizza_catena(catena, Livello.GARA, sistema)


def catena_generale(campionato: Any, sistema: ClassificationSystem) -> Catena:
    return normalizza_catena(
        catena_di_default(Livello.CAMPIONATO, sistema), Livello.CAMPIONATO, sistema
    )


def usa_scontri(catena: Iterable[Any]) -> bool:
    return any(v.criterio is Criterio.SCONTRI_DIRETTI for v in catena)


def _scontro(match: Any) -> Optional[Scontro]:
    """La partita come scontro diretto, o None se non lo è.

    Solo le partite a due: la X non è uno scontro, e nel trio il «vincitore»
    non dice chi ha battuto chi.
    """
    if match.is_bye or match.is_trio or not match.player1_id or not match.player2_id:
        return None
    # Stessa regola di `ScoreAggregator._process_regular_match`: decide il
    # punteggio; a pari punteggio solo chi il direttore ha fatto passare nel
    # tabellone (ADR-077), altrimenti è un pareggio.
    punti1, punti2 = match.player1_score or 0, match.player2_score or 0
    if punti1 > punti2:
        vincitore: Optional[int] = match.player1_id
    elif punti2 > punti1:
        vincitore = match.player2_id
    elif match.winner_id in (match.player1_id, match.player2_id):
        vincitore = match.winner_id
    else:
        vincitore = None
    rack1, rack2 = punti1, punti2
    if match.is_multi_set:
        rack1 = sum(s.player1_racks or 0 for s in match.sets)
        rack2 = sum(s.player2_racks or 0 for s in match.sets)
    return Scontro(match.player1_id, match.player2_id, rack1, rack2, vincitore)


def scontri_delle_gare(
    gare_ids: Iterable[int], fino_al_turno: Optional[int] = None
) -> List[Scontro]:
    """Le partite a due chiuse di quelle gare, fino al turno indicato."""
    from models.base import db
    from models.match.models import Match

    ids = list(gare_ids)
    if not ids:
        return []
    query = db.session.query(Match).filter(
        Match.gara_id.in_(ids),
        Match.status.in_(MatchStatus.finished_values()),
    )
    if fino_al_turno is not None:
        query = query.filter(Match.round_number <= fino_al_turno)
    scontri = (_scontro(m) for m in query.all())
    return [s for s in scontri if s is not None]
