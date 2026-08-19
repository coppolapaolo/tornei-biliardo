"""
Script diagnostico (READ-ONLY) per l'ELO.

Misura l'impatto del bug PRE-FIX di `recalc_elo.py`: prima della correzione il
backfill riprocessava solo i match in stato `completed` e SALTAVA quelli in
stato `validated` (lo stato finale normale di un match confermato da entrambi i
giocatori). Avendo lo script azzerato prima tutti gli ELO, i giocatori i cui
match erano `validated` restavano a `elo_rating = NULL`. I conteggi qui sotto
quantificano i match che quella versione avrebbe saltato.

Lo script NON scrive nulla sul DB: esegue solo SELECT e garantisce il rollback
finale (anche in caso di errore) per restare read-only.

Usage:
    python scripts/diagnose_elo.py                # panoramica aggregata
    python scripts/diagnose_elo.py --user-id 42   # dettaglio di un giocatore

Su PythonAnywhere è read-only, quindi NON serve disabilitare la web app.
Identifica i giocatori solo tramite `id`: non legge gli `username` (PII
cifrati), così gira pulito anche senza `ENCRYPTION_KEY` in console.
"""

import sys
import os
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func  # noqa: E402

from app import create_app  # noqa: E402
from models import db, User  # noqa: E402
from models.match.models import Match, Rack  # noqa: E402
from models.status_enum import MatchStatus  # noqa: E402
from models.rating.eligibility import RatingEligibility  # noqa: E402


def _rack_counts():
    """Mappa {match_id: n_rack} in UNA query aggregata.

    Evita l'N+1 di `Match.is_walkover`, che farebbe un COUNT separato per ogni
    match. Come `is_walkover`, NON filtra `is_deleted` (conta tutti i rack).
    """
    rows = db.session.query(Rack.match_id, func.count(Rack.id)).group_by(Rack.match_id)
    return {match_id: n for match_id, n in rows}


def _is_walkover(match, rack_counts):
    """Replica `Match.is_walkover` usando i conteggi precalcolati (no query).

    Tiene la stessa invariante del modello: un walkover è sempre e solo in
    stato `completed` (vedi models/match/models.py:162).
    """
    if match.status != MatchStatus.CLOSED_UNILATERALLY.value or match.winner_id is None:
        return False
    if match.is_trio:
        return match.trio_match is not None and match.trio_match.total_racks_played == 0
    return rack_counts.get(match.id, 0) == 0


class _UnknownExclusion:
    """Segnaposto per i match che non si riescono nemmeno a valutare.

    Non è un membro di `RatingExclusion` di proposito: quell'enum elenca i
    motivi *del dominio* per cui una partita non conta, mentre questo dice
    "i dati sono incompleti e la diagnostica non se la sente di decidere".
    Metterlo nell'enum lo renderebbe un esito legittimo del motore di rating.
    """

    description = "non valutabile: dati incompleti"


_UNKNOWN_EXCLUSION = _UnknownExclusion()


def _exclusion(match, rack_counts):
    """Perché questo match non contribuisce all'ELO, o None se contribuisce.

    Delega a `RatingEligibility`, che è la stessa fonte usata dall'handler e
    dai ricalcoli. Prima qui c'era una copia dei filtri, e la docstring lo
    ammetteva: una diagnostica che replica la regola che deve diagnosticare
    smette di essere una diagnostica appena le due divergono.
    """
    try:
        return RatingEligibility.exclusion_reason(
            match, is_walkover=_is_walkover(match, rack_counts)
        )
    except Exception:
        # In caso di dati incompleti, conservativo: non eleggibile.
        return _UNKNOWN_EXCLUSION


def _eligible_for_rating(match, rack_counts):
    """True se il match dovrebbe contribuire all'ELO."""
    return _exclusion(match, rack_counts) is None


def _player_ids(match):
    """Restituisce gli id dei giocatori coinvolti (gestisce anche i trio)."""
    if match.is_trio and match.trio_match:
        t = match.trio_match
        return [t.player1_id, t.player2_id, t.player3_id]
    return [match.player1_id, match.player2_id]


def _run(user_id, validated):
    """Corpo della diagnosi (tutte SELECT). Chiamato dentro try/finally."""
    finished = Match.query.filter(Match.status.in_(MatchStatus.finished_values())).all()
    rack_counts = _rack_counts()

    n_completed = sum(1 for m in finished if m.status != validated)
    n_validated = sum(1 for m in finished if m.status == validated)

    # Per ogni utente: quanti match eleggibili al rating, e di questi
    # quanti in stato `validated` (= saltati dal recalc PRE-FIX).
    eligible_total = {}  # user_id -> n match eleggibili
    eligible_validated = {}  # user_id -> n eleggibili ma validated (saltati)

    skipped_eligible = 0
    for m in finished:
        if not _eligible_for_rating(m, rack_counts):
            continue
        is_validated = m.status == validated
        if is_validated:
            skipped_eligible += 1
        for pid in _player_ids(m):
            if pid is None:
                continue
            eligible_total[pid] = eligible_total.get(pid, 0) + 1
            if is_validated:
                eligible_validated[pid] = eligible_validated.get(pid, 0) + 1

    print("=" * 60)
    print("PANORAMICA MATCH CONCLUSI")
    print("=" * 60)
    print(f"  Match 'completed' (riprocessati dal recalc): {n_completed}")
    print(f"  Match 'validated' (saltati dal recalc PRE-FIX): {n_validated}")
    print(
        f"  Match eleggibili al rating ma 'validated' "
        f"(persi nel backfill PRE-FIX): {skipped_eligible}"
    )
    print()

    # Vittime: utenti con elo NULL che però hanno >=1 match eleggibile.
    victims = [
        u
        for u in User.query.all()
        if u.elo_rating is None and eligible_total.get(u.id, 0) > 0
    ]

    print("=" * 60)
    print("GIOCATORI CON elo_rating = NULL MA CON MATCH ELEGGIBILI")
    print("=" * 60)
    print(f"  Totale 'vittime' del backfill: {len(victims)}")
    for u in sorted(victims, key=lambda x: eligible_total.get(x.id, 0), reverse=True)[
        :30
    ]:
        tot = eligible_total.get(u.id, 0)
        val = eligible_validated.get(u.id, 0)
        print(
            f"    id={u.id:<5} "
            f"eleggibili={tot:<3} di cui validated (saltati pre-fix)={val}"
        )
    if len(victims) > 30:
        print(f"    ... e altri {len(victims) - 30}")
    print()

    # Dettaglio singolo giocatore.
    if user_id is None:
        return

    u = db.session.get(User, user_id)
    if not u:
        print(f"Utente id={user_id} non trovato.")
        return

    print("=" * 60)
    print(f"DETTAGLIO GIOCATORE id={u.id}")
    print("=" * 60)
    print(f"  elo_rating attuale: {u.elo_rating!r}")
    mine = [m for m in finished if user_id in _player_ids(m)]
    print(f"  match conclusi: {len(mine)}")
    for m in mine:
        motivo = _exclusion(m, rack_counts)
        elig = motivo is None
        reason = "" if elig else motivo.description
        flag = "OK" if (elig and m.status == validated) else ""
        print(
            f"    match id={m.id:<5} status={m.status:<10} "
            f"eleggibile={str(elig):<5} {reason}"
            f"{'  <- saltato dal recalc pre-fix' if flag else ''}"
        )


def diagnose(user_id=None):
    app = create_app()
    with app.app_context():
        try:
            _run(user_id, MatchStatus.CONFIRMED_BY_BOTH.value)
        finally:
            # Read-only: annulla qualsiasi stato di sessione anche su errore,
            # così la transazione non resta aperta a trattenere lock.
            db.session.rollback()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnosi ELO (read-only).")
    parser.add_argument(
        "--user-id", type=int, default=None, help="Dettaglia un singolo giocatore"
    )
    args = parser.parse_args()
    diagnose(user_id=args.user_id)
