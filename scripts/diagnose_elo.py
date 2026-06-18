"""
Script diagnostico (READ-ONLY) per l'ELO.

Verifica l'impatto del bug di `recalc_elo.py`, che riprocessa solo i match in
stato `completed` e SALTA quelli in stato `validated` (lo stato finale normale
di un match confermato da entrambi i giocatori). Lo script NON scrive nulla sul
DB: esegue solo SELECT e termina con un rollback esplicito.

Usage:
    python scripts/diagnose_elo.py                # panoramica aggregata
    python scripts/diagnose_elo.py --user-id 42   # dettaglio di un giocatore

Su PythonAnywhere è read-only, quindi NON serve disabilitare la web app.
Se gli username risultassero offuscati serve `ENCRYPTION_KEY='...'` davanti al
comando, ma lo script funziona comunque mostrando gli id.
"""

import sys
import os
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import db, User  # noqa: E402
from models.match.models import Match  # noqa: E402
from models.status_enum import MatchStatus  # noqa: E402


def _eligible_for_rating(match):
    """True se il match dovrebbe contribuire all'ELO.

    Replica i filtri di RatingEventHandlers.handle_match_completed:
    niente walkover, niente handicap.
    """
    try:
        if match.is_walkover:
            return False
        if match.effective_has_handicap:
            return False
    except Exception:
        # In caso di dati incompleti, conservativo: non eleggibile.
        return False
    return True


def _player_ids(match):
    """Restituisce gli id dei giocatori coinvolti (gestisce anche i trio)."""
    if match.is_trio and match.trio_match:
        t = match.trio_match
        return [t.player1_id, t.player2_id, t.player3_id]
    return [match.player1_id, match.player2_id]


def _safe_username(user):
    try:
        return user.username
    except Exception:
        return f"<id {user.id}>"


def diagnose(user_id=None):
    app = create_app()
    with app.app_context():
        completed = MatchStatus.COMPLETED.value
        validated = MatchStatus.VALIDATED.value

        finished = Match.query.filter(Match.status.in_([completed, validated])).all()

        n_completed = sum(1 for m in finished if m.status == completed)
        n_validated = sum(1 for m in finished if m.status == validated)

        # Per ogni utente: quanti match eleggibili al rating, e di questi
        # quanti in stato `validated` (= saltati dal recalc).
        eligible_total = {}  # user_id -> n match eleggibili
        eligible_validated = {}  # user_id -> n eleggibili ma validated (saltati)

        skipped_eligible = 0
        for m in finished:
            if not _eligible_for_rating(m):
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
        print(f"  Match 'validated' (SALTATI dal recalc):      {n_validated}")
        print(
            f"  Match eleggibili al rating ma 'validated' "
            f"(persi nel backfill): {skipped_eligible}"
        )
        print()

        # Vittime: utenti con elo NULL che però hanno >=1 match eleggibile.
        users = User.query.all()
        victims = []
        for u in users:
            if u.elo_rating is None and eligible_total.get(u.id, 0) > 0:
                victims.append(u)

        print("=" * 60)
        print("GIOCATORI CON elo_rating = NULL MA CON MATCH ELEGGIBILI")
        print("=" * 60)
        print(f"  Totale 'vittime' del backfill: {len(victims)}")
        for u in sorted(
            victims, key=lambda x: eligible_total.get(x.id, 0), reverse=True
        )[:30]:
            tot = eligible_total.get(u.id, 0)
            val = eligible_validated.get(u.id, 0)
            print(
                f"    id={u.id:<5} {_safe_username(u):<20} "
                f"eleggibili={tot:<3} di cui validated(saltati)={val}"
            )
        if len(victims) > 30:
            print(f"    ... e altri {len(victims) - 30}")
        print()

        # Dettaglio singolo giocatore.
        if user_id is not None:
            u = db.session.get(User, user_id)
            if not u:
                print(f"Utente id={user_id} non trovato.")
            else:
                print("=" * 60)
                print(f"DETTAGLIO GIOCATORE id={u.id} ({_safe_username(u)})")
                print("=" * 60)
                print(f"  elo_rating attuale: {u.elo_rating!r}")
                mine = [m for m in finished if user_id in _player_ids(m)]
                print(f"  match conclusi: {len(mine)}")
                for m in mine:
                    elig = _eligible_for_rating(m)
                    reason = ""
                    if not elig:
                        if m.is_walkover:
                            reason = "walkover"
                        elif m.effective_has_handicap:
                            reason = "handicap"
                        else:
                            reason = "non eleggibile"
                    flag = "OK" if (elig and m.status == validated) else ""
                    print(
                        f"    match id={m.id:<5} status={m.status:<10} "
                        f"eleggibile={str(elig):<5} {reason}"
                        f"{'  <- saltato dal recalc' if flag else ''}"
                    )

        # Read-only: annulla qualsiasi stato di sessione, per sicurezza.
        db.session.rollback()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnosi ELO (read-only).")
    parser.add_argument(
        "--user-id", type=int, default=None, help="Dettaglia un singolo giocatore"
    )
    args = parser.parse_args()
    diagnose(user_id=args.user_id)
