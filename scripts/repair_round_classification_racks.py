"""Ricalcola dai match le due colonne di triangoli di `round_classification`.

**Perché serve.** Fino al 2026-07-28 la colonna `rack_difference` aveva due
significati a seconda di `gara.classification_system`: differenza triangoli
nelle gare a vittorie, *totale* nelle gare a triangoli. La migration
`20260728_split_round_classification_racks` ha separato i due significati
(`racks_won` = sempre il totale, `rack_difference` = sempre la differenza) ma
ha deliberatamente lasciato indietro le righe storiche, affidandosi a
`RoundClassification.ranking_rack_value` per mascherarle **in lettura**.

Quel mascheramento copre solo il totale. In DB restano quindi due difetti:

* gare a triangoli chiuse prima della separazione → `rack_difference` contiene
  ancora un totale, non una differenza;
* gare a vittorie chiuse prima della separazione → `racks_won` è NULL, e il
  totale non è ricostruibile dalle sole colonne.

Finché la classifica generale sommava `rack_difference` chiamandolo "triangoli
totali" (issue #89) il secondo difetto non si vedeva e il primo si compensava
per caso. Con la classifica corretta (ADR-047) le due colonne vengono lette per
quello che dichiarano di essere, e vanno rese vere.

**Come.** Non si indovina quali righe siano stantie — non sono distinguibili:
una riga corretta di chi ha vinto tutti i triangoli ha comunque
`racks_won == rack_difference`. Si ricalcola invece il valore dai match con
`ScoreAggregator.aggregate_round_scores`, **la stessa funzione** che alimenta
il calcolo di produzione (`GaraClassificationService.calculate_round_classification`):
sulle righe già giuste è un no-op, e l'operazione è idempotente.

**Cosa NON tocca.** `position` e `previous_position` restano come sono. Da
luglio sono cambiati il fix B14, i parimerito e ADR-040, quindi un ricalcolo
completo potrebbe muovere piazzamenti storici già comunicati ai giocatori — e
quei piazzamenti alimentano i punti-posizione e il seeding dei playoff. Il
dry-run segnala **se** l'ordine cambierebbe, così la decisione si prende
guardando i numeri invece che a scatola chiusa.

Usage:
    python scripts/repair_round_classification_racks.py              # dry-run
    python scripts/repair_round_classification_racks.py --apply      # scrive
    python scripts/repair_round_classification_racks.py --campionato 3
    python scripts/repair_round_classification_racks.py --gara 12 --apply

In produzione va lanciato con la web app su **Disabled** (SQLite su NFS), e con
l'interprete del venv:

    venv/bin/python scripts/repair_round_classification_racks.py
"""

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
# Servono entrambe: la radice del progetto (per `app`, `models`) e la cartella
# scripts (per `prod_env`), anche quando il file viene caricato per path invece
# che eseguito, come fanno i test. La radice va inserita per ultima così da
# restare davanti a `scripts/` in sys.path.
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from prod_env import bootstrap_and_create_app  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class RowFix:
    """Una riga da correggere, con il prima e il dopo."""

    __slots__ = (
        "gara_id",
        "gara_name",
        "round_number",
        "user_id",
        "old_racks_won",
        "new_racks_won",
        "old_difference",
        "new_difference",
    )

    def __init__(
        self,
        gara_id: int,
        gara_name: str,
        round_number: int,
        user_id: int,
        old_racks_won: Optional[int],
        new_racks_won: int,
        old_difference: Optional[int],
        new_difference: int,
    ) -> None:
        self.gara_id = gara_id
        self.gara_name = gara_name
        self.round_number = round_number
        self.user_id = user_id
        self.old_racks_won = old_racks_won
        self.new_racks_won = new_racks_won
        self.old_difference = old_difference
        self.new_difference = new_difference

    @property
    def racks_won_changes(self) -> bool:
        return self.old_racks_won != self.new_racks_won

    @property
    def difference_changes(self) -> bool:
        return self.old_difference != self.new_difference

    def describe(self) -> str:
        parts = []
        if self.racks_won_changes:
            parts.append(f"racks_won {self.old_racks_won} → {self.new_racks_won}")
        if self.difference_changes:
            parts.append(
                f"rack_difference {self.old_difference} → {self.new_difference}"
            )
        return ", ".join(parts)


def _collect_fixes(
    gara_ids: Optional[List[int]] = None,
) -> Tuple[List[RowFix], List[str]]:
    """Confronta le righe salvate con quelle ricalcolate dai match.

    Returns:
        (righe da correggere, avvisi sull'ordine che cambierebbe)
    """
    from models.base import db
    from models.classification.models import RoundClassification
    from models.classification.score_aggregator import ScoreAggregator
    from models.competition.models import Gara
    from models.status_enum import ClassificationSystem

    aggregator = ScoreAggregator()
    fixes: List[RowFix] = []
    order_warnings: List[str] = []

    query = db.session.query(Gara)
    if gara_ids:
        query = query.filter(Gara.id.in_(gara_ids))
    gare = query.order_by(Gara.id).all()

    for gara in gare:
        rows = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara.id)
            .order_by(RoundClassification.round_number, RoundClassification.position)
            .all()
        )
        if not rows:
            continue

        is_rack = (
            ClassificationSystem.resolve(getattr(gara, "classification_system", None))
            == ClassificationSystem.RACK
        )

        rows_by_round: Dict[int, List[RoundClassification]] = {}
        for row in rows:
            rows_by_round.setdefault(row.round_number, []).append(row)

        for round_number, round_rows in sorted(rows_by_round.items()):
            # Stessa funzione che alimenta il calcolo di produzione: se qui
            # servisse una formula propria, questo script sarebbe una seconda
            # implementazione destinata a divergere.
            scores = {
                score.player_id: score
                for score in aggregator.aggregate_round_scores(gara.id, round_number)
            }

            round_fixes: List[RowFix] = []
            for row in round_rows:
                score = scores.get(row.user_id)
                if score is None:
                    # Il giocatore non ha match validi fino a questo turno: la
                    # riga è orfana e la ripulisce il ricalcolo normale, non
                    # questo script (che non cancella nulla).
                    continue
                fix = RowFix(
                    gara_id=gara.id,
                    gara_name=gara.name,
                    round_number=round_number,
                    user_id=row.user_id,
                    old_racks_won=row.racks_won,
                    new_racks_won=score.racks_won,
                    old_difference=row.rack_difference,
                    new_difference=score.rack_difference,
                )
                if fix.racks_won_changes or fix.difference_changes:
                    round_fixes.append(fix)

            if not round_fixes:
                continue
            fixes.extend(round_fixes)

            warning = _order_warning(gara, round_number, round_rows, scores, is_rack)
            if warning:
                order_warnings.append(warning)

    return fixes, order_warnings


def _order_warning(
    gara,
    round_number: int,
    round_rows: List,
    scores: Dict,
    is_rack: bool,
) -> Optional[str]:
    """Segnala se i valori corretti indurrebbero un ordine diverso da quello salvato.

    È un'**indicazione**, non il ricalcolo ufficiale: quello passa da parimerito,
    SSR e ordine del turno precedente. Serve solo a sapere se la riparazione
    delle sole colonne lascia le posizioni coerenti o no.
    """

    def key(row):
        score = scores.get(row.user_id)
        if score is None:
            return (0, 0)
        if is_rack:
            return (-score.racks_won, -score.matches_won)
        return (-score.matches_won, -score.rack_difference)

    saved_order = [row.user_id for row in sorted(round_rows, key=lambda r: r.position)]
    recomputed_order = [row.user_id for row in sorted(round_rows, key=key)]
    if saved_order == recomputed_order:
        return None
    return (
        f"  ⚠️  gara {gara.id} «{gara.name}», turno {round_number}: "
        f"i valori corretti indurrebbero un ordine diverso da quello salvato "
        f"(salvato {saved_order} → indotto {recomputed_order}). "
        f"Le posizioni NON vengono toccate."
    )


def _apply(fixes: List[RowFix]) -> int:
    """Scrive le correzioni. Ritorna il numero di righe toccate."""
    from models.base import db
    from models.classification.models import RoundClassification

    touched = 0
    for fix in fixes:
        row = (
            db.session.query(RoundClassification)
            .filter_by(
                gara_id=fix.gara_id,
                round_number=fix.round_number,
                user_id=fix.user_id,
            )
            .one_or_none()
        )
        if row is None:
            continue
        row.racks_won = fix.new_racks_won
        row.rack_difference = fix.new_difference
        touched += 1

    db.session.commit()
    return touched


def _report(fixes: List[RowFix], order_warnings: List[str], applied: bool) -> None:
    if not fixes:
        logger.info(
            "Nessuna riga da correggere: le colonne sono già coerenti con i match."
        )
        return

    by_gara: Dict[int, List[RowFix]] = {}
    for fix in fixes:
        by_gara.setdefault(fix.gara_id, []).append(fix)

    verb = "corrette" if applied else "da correggere"
    logger.info("%d righe %s in %d gare:", len(fixes), verb, len(by_gara))
    for gara_id, gara_fixes in sorted(by_gara.items()):
        logger.info(
            "  gara %d «%s»: %d righe",
            gara_id,
            gara_fixes[0].gara_name,
            len(gara_fixes),
        )
        for fix in gara_fixes[:5]:
            logger.info(
                "    turno %d, utente %d: %s",
                fix.round_number,
                fix.user_id,
                fix.describe(),
            )
        if len(gara_fixes) > 5:
            logger.info("    … e altre %d righe", len(gara_fixes) - 5)

    racks_won_only = sum(
        1 for f in fixes if f.racks_won_changes and not f.difference_changes
    )
    difference_only = sum(
        1 for f in fixes if f.difference_changes and not f.racks_won_changes
    )
    both = sum(1 for f in fixes if f.difference_changes and f.racks_won_changes)
    logger.info(
        "Riepilogo: %d solo racks_won, %d solo rack_difference, %d entrambe.",
        racks_won_only,
        difference_only,
        both,
    )

    if order_warnings:
        logger.info("")
        logger.info(
            "%d turni in cui l'ordine salvato non corrisponde ai valori corretti:",
            len(order_warnings),
        )
        for warning in order_warnings:
            logger.info(warning)
    else:
        logger.info(
            "Nessun turno cambierebbe ordine: le posizioni salvate restano coerenti."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Scrive le correzioni. Senza questo flag lo script è di sola lettura.",
    )
    parser.add_argument(
        "--gara",
        type=int,
        action="append",
        dest="gare",
        help="Limita a una gara (ripetibile).",
    )
    parser.add_argument(
        "--campionato",
        type=int,
        help="Limita alle gare di un campionato.",
    )
    args = parser.parse_args()

    app = bootstrap_and_create_app()
    with app.app_context():
        from models.base import db
        from models.competition.models import Gara

        gara_ids = list(args.gare or [])
        if args.campionato:
            gara_ids.extend(
                gid
                for (gid,) in db.session.query(Gara.id)
                .filter(Gara.campionato_id == args.campionato)
                .all()
            )

        scope = f"{len(gara_ids)} gare" if gara_ids else "tutte le gare"
        logger.info(
            "%s su %s…", "Riparazione" if args.apply else "Analisi (dry-run)", scope
        )

        fixes, order_warnings = _collect_fixes(gara_ids or None)

        if args.apply and fixes:
            touched = _apply(fixes)
            logger.info("Scritte %d righe.", touched)

        _report(fixes, order_warnings, applied=args.apply)

        if not args.apply and fixes:
            logger.info("")
            logger.info("Dry-run: nulla è stato scritto. Rilancia con --apply.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
