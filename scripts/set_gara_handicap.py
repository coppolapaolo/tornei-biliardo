"""Imposta (o rimuove) l'handicap mode su una gara specifica.

Uso tipico — la gara 19 in produzione (https://www.torneibiliardo.it/admin/gara/19)
deve avere l'handicap:

    python scripts/set_gara_handicap.py --gara 19            # dry-run
    python scripts/set_gara_handicap.py --gara 19 --commit   # applica
    python scripts/set_gara_handicap.py --gara 19 --off --commit  # disattiva

Imposta `gara.has_handicap`. I match della gara che hanno `has_handicap=NULL`
(default) erediteranno automaticamente il valore via Match.effective_has_handicap,
quindi non aggiorneranno più i rating. Non tocca i match con override esplicito.

Idempotente: rilanciarlo non cambia nulla se il valore è già quello voluto.
"""

import sys
import os
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models.competition.models import Gara  # noqa: E402


def set_handicap(gara_id: int, value: bool, commit: bool) -> int:
    app = create_app()
    with app.app_context():
        gara = db.session.get(Gara, gara_id)
        if not gara:
            print(f"❌ Gara {gara_id} non trovata.")
            return 1

        old = gara.has_handicap
        print(f"Gara {gara_id} — '{gara.name}'")
        print(f"  has_handicap: {old!r} → {value!r}")
        print(f"  effective_has_handicap (pre): {gara.effective_has_handicap}")

        if old == value:
            print("  ⏭️  Nessuna modifica necessaria (valore già impostato).")
            return 0

        gara.has_handicap = value
        db.session.add(gara)

        if commit:
            db.session.commit()
            print("  ✓ Modifica committata.")
        else:
            db.session.rollback()
            print("  ℹ️  DRY RUN: nessuna modifica salvata (usa --commit).")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Imposta handicap mode su una gara.")
    parser.add_argument("--gara", type=int, required=True, help="ID della gara")
    parser.add_argument(
        "--off",
        action="store_true",
        help="Disattiva l'handicap (default: attiva).",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Applica le modifiche (default: dry-run).",
    )
    args = parser.parse_args()

    sys.exit(set_handicap(args.gara, value=not args.off, commit=args.commit))
