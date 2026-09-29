"""Le regole di una partita si fissano quando la partita nasce (ADR-075).

Fino al 2026-09-29 molte regole la partita le rileggeva dalla gara a ogni
accesso: «al N» o «esattamente N», disciplina, triangoli per set, chi apre, chi
spacca, handicap, categorie per l'ELO. Finché la gara non si poteva toccare
dopo l'avvio non cambiava niente; con la modifica tracciata, un cambio di regola
arriverebbe anche alle partite già giocate o in corso — un ricalcolo dell'ELO
rileggerebbe le categorie di oggi sulle partite di ieri.

Ora ogni partita porta con sé le sue regole, scritte una volta sola:

* `fissa_regole` riempie i campi ancora vuoti con le regole **effettive** della
  gara in quel momento (quelle del turno, se il turno le ha già scritte);
* un ascoltatore di `before_flush` la chiama su **ogni** partita nuova, così
  nessuna strada di creazione — turni, spareggi, X con prova, script — può
  dimenticarla. Stessa idea per il trio: quando nasce, le categorie della
  partita si completano col terzo giocatore.

Una **correzione** di un dato (lo script che corregge la categoria, la
riassegnazione di un partecipante, ADR-048) non è un cambio di regola: tocca
anche le partite già giocate. Per quello ci sono `correggi_categoria` e
`sposta_categoria`.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import event
from sqlalchemy.orm import Session


def _categorie_iscritti(session: Session, gara_id: int, user_ids: Iterable[int]):
    from models.competition.models import Inscription

    ids = [uid for uid in user_ids if uid]
    if not ids:
        return {}
    righe = (
        session.query(Inscription.user_id, Inscription.categoria_id)
        .filter(Inscription.gara_id == gara_id, Inscription.user_id.in_(ids))
        # Se le righe sono due (una ritirata e una valida) vince la valida,
        # come in `RatingEligibility`.
        .order_by(Inscription.is_withdrawn.desc(), Inscription.id.asc())
        .all()
    )
    return {user_id: categoria_id for user_id, categoria_id in righe}


def leggi_categorie(match: Any) -> Optional[Dict[int, Optional[int]]]:
    """Le categorie fissate sulla partita, o None se non sono mai state fissate."""
    grezzo = getattr(match, "categories_snapshot", None)
    if not grezzo:
        return None
    try:
        dati = json.loads(grezzo)
    except ValueError:
        return None
    return {int(uid): cat for uid, cat in dati.items()}


def _scrivi_categorie(match: Any, categorie: Dict[int, Optional[int]]) -> None:
    match.categories_snapshot = json.dumps(
        {str(uid): cat for uid, cat in sorted(categorie.items())}
    )


def fissa_categorie(session: Session, match: Any, extra_ids: Iterable[int] = ()):
    """Scrive (o completa) le categorie dei giocatori della partita."""
    if not match.gara_id:
        return
    ids = [match.player1_id, match.player2_id, *extra_ids]
    ids = [uid for uid in ids if uid]
    if not ids:
        return
    esistenti = leggi_categorie(match) or {}
    mancanti = [uid for uid in ids if uid not in esistenti]
    if not mancanti and match.categories_snapshot:
        return
    trovate = _categorie_iscritti(session, match.gara_id, mancanti)
    for uid in mancanti:
        esistenti[uid] = trovate.get(uid)
    _scrivi_categorie(match, esistenti)


def fissa_regole(session: Session, match: Any) -> None:
    """Riempie le regole ancora vuote con quelle effettive della gara."""
    from models.competition.models import Gara
    from models.matchmaking.configuration import OddNumberPolicy

    if not match.gara_id:
        return
    gara = session.get(Gara, match.gara_id)
    if gara is None:
        return

    if match.is_race_to is None:
        match.is_race_to = gara.is_race_to
    if match.is_race_to_sets is None:
        match.is_race_to_sets = getattr(gara, "is_race_to_sets", True)
    if not match.discipline:
        match.discipline = gara.discipline
    if match.has_handicap is None:
        match.has_handicap = gara.effective_has_handicap
    if match.start_rule is None:
        match.start_rule = gara.effective_start_rule.value
    if match.break_rule is None:
        match.break_rule = gara.effective_break_rule.value
    if match.is_multi_set and match.set_distance is None:
        match.set_distance = gara.distance
    if match.is_bye and match.x_with_challenge is None:
        match.x_with_challenge = (
            gara.odd_number_policy == OddNumberPolicy.BYE_WITH_CHALLENGE.value
        )
    fissa_categorie(session, match)


def correggi_categoria(gara_id: int, user_id: int, categoria_id: Optional[int]) -> int:
    """Una **correzione** della categoria arriva anche alle partite già giocate.

    Chiamata da chi corregge un dato scritto male (`force=True` in
    `CategoriaService`: lo script di riparazione, la riassegnazione di un
    partecipante). Un cambio di categoria a gara in corso, invece, vale solo
    per le partite che nasceranno: non passa di qui. Restituisce quante
    partite ha toccato.
    """
    from models.base import db
    from models.match.models import Match

    toccate = 0
    for match in Match.query.filter(
        Match.gara_id == gara_id, Match.categories_snapshot.isnot(None)
    ).all():
        categorie = leggi_categorie(match)
        if categorie is None or user_id not in categorie:
            continue
        if categorie[user_id] != categoria_id:
            categorie[user_id] = categoria_id
            _scrivi_categorie(match, categorie)
            toccate += 1
    db.session.flush()
    return toccate


def sposta_categoria(gara_id: int, source_id: int, target_id: int) -> int:
    """Riassegnazione (ADR-048): le partite giocate da `source` ora sono di `target`.

    La categoria segue la partita: resta quella con cui è stata giocata, sotto
    il nome del giocatore che l'ha giocata davvero. Se poi la riassegnazione
    corregge anche la categoria, ci pensa `correggi_categoria`.
    """
    from models.base import db
    from models.match.models import Match

    toccate = 0
    for match in Match.query.filter(
        Match.gara_id == gara_id, Match.categories_snapshot.isnot(None)
    ).all():
        categorie = leggi_categorie(match)
        if categorie is None or source_id not in categorie:
            continue
        categorie[target_id] = categorie.pop(source_id)
        _scrivi_categorie(match, categorie)
        toccate += 1
    db.session.flush()
    return toccate


def _prima_del_flush(session: Session, _flush_context, _instances) -> None:
    from models.match.models import Match, TrioMatch

    nuove = [obj for obj in session.new if isinstance(obj, (Match, TrioMatch))]
    if not nuove:
        return
    with session.no_autoflush:
        for obj in nuove:
            if isinstance(obj, Match):
                fissa_regole(session, obj)
        for obj in nuove:
            if isinstance(obj, TrioMatch):
                match = obj.match or (
                    session.get(Match, obj.match_id) if obj.match_id else None
                )
                if match is not None:
                    fissa_categorie(
                        session,
                        match,
                        extra_ids=(obj.player1_id, obj.player2_id, obj.player3_id),
                    )


_REGISTRATO = False


def registra_ascoltatore() -> None:
    """Aggancia `fissa_regole` al flush di ogni sessione. Idempotente."""
    global _REGISTRATO
    if _REGISTRATO:
        return
    event.listen(Session, "before_flush", _prima_del_flush)
    _REGISTRATO = True
