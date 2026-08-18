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

    @property
    def is_discrepancy(self) -> bool:
        """Vero se il numero salvato non discende dalle partite giocate.

        Distinzione che conta più di quanto sembri, perché senza di essa il
        report dà l'impressione che lo storico sia pieno di errori.

        La maggior parte delle righe da correggere **non** è sbagliata: prima
        della separazione delle due colonne un solo numero veniva interpretato
        secondo la convenzione del momento, e la classifica di allora mostrava
        il valore giusto. Tradurlo nelle due colonne di oggi cambia dove il
        numero è scritto, non quanto vale.

        Il criterio è indipendente da quale convenzione fosse in vigore — cosa
        che non è ricostruibile riga per riga, visto che è cambiata due volte
        (fix B14 sul calcolatore, poi la separazione delle colonne): se il
        valore salvato **coincide con uno dei due valori ricalcolati**, allora
        era un numero giusto in una casella con un'altra etichetta. Se non
        coincide con nessuno dei due, non veniva dalle partite.
        """
        recomputed = {self.new_racks_won, self.new_difference}
        if self.old_racks_won is not None and self.old_racks_won not in recomputed:
            return True
        if self.old_difference is not None and self.old_difference not in recomputed:
            return True
        return False

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
    """Segnala solo le **inversioni vere** fra posizione salvata e merito ricalcolato.

    Cioè: qualcuno sta sopra a qualcun altro che, coi valori corretti, ha un
    merito **strettamente migliore**. Chi lo supera a pari merito non è una
    divergenza — è uno spareggio deciso da criteri che questa funzione non
    conosce (SSR, ordine del turno precedente), e confrontare le due sequenze
    intere li segnalava tutti come problemi. La prima versione di questo
    controllo produceva così 15 avvisi su dati di produzione, di cui quasi
    tutti erano coppie a pari triangoli.
    """

    def merit(row):
        score = scores.get(row.user_id)
        if score is None:
            return None
        if is_rack:
            return (score.racks_won,)
        return (score.matches_won, score.rack_difference)

    ordered = sorted(round_rows, key=lambda r: r.position)
    inversioni = []
    for i, sopra in enumerate(ordered):
        merito_sopra = merit(sopra)
        if merito_sopra is None:
            continue
        for sotto in ordered[i + 1 :]:
            merito_sotto = merit(sotto)
            if merito_sotto is None:
                continue
            if merito_sotto > merito_sopra:
                inversioni.append(
                    f"utente {sotto.user_id} (pos. {sotto.position}) supera "
                    f"utente {sopra.user_id} (pos. {sopra.position})"
                )

    if not inversioni:
        return None
    dettaglio = "; ".join(inversioni[:3])
    if len(inversioni) > 3:
        dettaglio += f"; … e altre {len(inversioni) - 3}"
    return (
        f"   gara {gara.id} «{gara.name}», turno {round_number}: {dettaglio}. "
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


def _log_by_gara(fixes: List[RowFix], limit: int = 5) -> None:
    """Elenca le righe raggruppate per gara, troncando le più lunghe."""
    if not fixes:
        return
    by_gara: Dict[int, List[RowFix]] = {}
    for fix in fixes:
        by_gara.setdefault(fix.gara_id, []).append(fix)

    for gara_id, gara_fixes in sorted(by_gara.items()):
        logger.info(
            "   gara %d «%s»: %d righe",
            gara_id,
            gara_fixes[0].gara_name,
            len(gara_fixes),
        )
        for fix in gara_fixes[:limit]:
            logger.info(
                "     turno %d, utente %d: %s",
                fix.round_number,
                fix.user_id,
                fix.describe(),
            )
        if len(gara_fixes) > limit:
            logger.info("     … e altre %d righe", len(gara_fixes) - limit)


def _report(fixes: List[RowFix], order_warnings: List[str], applied: bool) -> None:
    if not fixes:
        logger.info(
            "Nessuna riga da correggere: le colonne sono già coerenti con i match."
        )
        return

    riscritture = [f for f in fixes if not f.is_discrepancy]
    scostamenti = [f for f in fixes if f.is_discrepancy]

    verb = "corrette" if applied else "da correggere"
    logger.info("%d righe %s in totale, divise in due gruppi.", len(fixes), verb)
    logger.info("")

    logger.info(
        "── %d righe: stesso numero, casella diversa ────────────────────",
        len(riscritture),
    )
    logger.info(
        "   Il valore salvato coincide con uno dei due ricalcolati: era giusto,"
    )
    logger.info(
        "   e la classifica di allora mostrava il numero corretto. Cambia dove è"
    )
    logger.info("   scritto, non quanto vale.")
    _log_by_gara(riscritture)

    logger.info("")
    if scostamenti:
        logger.info(
            "── %d righe: il numero non discende dalle partite ──────────────",
            len(scostamenti),
        )
        logger.info("   Qui il valore salvato non coincide né col totale né con la")
        logger.info(
            "   differenza ricalcolati dalle partite. Sono le righe da guardare."
        )
        _log_by_gara(scostamenti, limit=8)
    else:
        logger.info("── Nessuna riga con un numero che non discende dalle partite ───")
        logger.info("   Tutto lo scarto è dovuto al cambio di convenzione.")

    if order_warnings:
        logger.info("")
        logger.info(
            "── %d turni in cui la classifica apparirà fuori ordine ─────────",
            len(order_warnings),
        )
        logger.info(
            "   Qualcuno sta sopra a chi, coi valori corretti, ha fatto meglio."
        )
        logger.info("   Le posizioni restano quelle di allora: dopo la riparazione il")
        logger.info("   numero accanto al nome non giustificherà l'ordine mostrato.")
        for warning in order_warnings:
            logger.info(warning)
    else:
        logger.info("── Nessun turno apparirà fuori ordine ─────────────────────────")
        logger.info("   Ogni posizione salvata resta giustificata dai valori corretti.")


def _classifica_generale(campionato_id: int) -> List[tuple]:
    """La classifica generale come la vedrebbe un giocatore adesso."""
    from models.campionato.statistics_service import TournamentStatisticsService

    service = TournamentStatisticsService()
    return service.calculate_general_classification(campionato_id)


def _anteprima_campionato(campionato_id: int, fixes: List[RowFix]) -> None:
    """Mostra tutto ciò che cambia in un campionato, senza scrivere nulla.

    Applica le correzioni **nella sessione** e le annulla subito dopo: i numeri
    stampati sono quelli veri, calcolati dallo stesso codice che serve le
    pagine, non una stima.
    """
    from models.base import db
    from models.campionato.models import Campionato
    from models.classification.models import GaraClassification, RoundClassification
    from models.competition.models import Gara

    campionato = db.session.get(Campionato, campionato_id)
    if campionato is None:
        logger.info("Campionato %d non trovato.", campionato_id)
        return

    logger.info("")
    logger.info("=" * 66)
    logger.info("ANTEPRIMA — campionato %d «%s»", campionato.id, campionato.name)
    logger.info("=" * 66)
    logger.info(
        "Sistema di classifica: %s  |  Tipo: %s",
        campionato.classification_system.value,
        campionato.campionato_type,
    )

    # ── 1. Classifiche finali di gara: quelle dei premi ──────────────────
    gare = (
        db.session.query(Gara)
        .filter_by(campionato_id=campionato_id)
        .order_by(Gara.number)
        .all()
    )
    logger.info("")
    logger.info("1) RISULTATI FINALI DELLE GARE (quelli dei premi)")
    for gara in gare:
        finali = (
            db.session.query(GaraClassification)
            .filter_by(gara_id=gara.id)
            .order_by(GaraClassification.position)
            .all()
        )
        podio = ", ".join(f"{g.position}° u{g.user_id}" for g in finali[:3])
        logger.info(
            "   gara %d «%s»: %s%s",
            gara.id,
            gara.name,
            podio or "nessuna classifica finale salvata",
            "  → INVARIATO" if finali else "",
        )
    logger.info("   Questi risultati stanno in un archivio separato che lo script non")
    logger.info("   apre: nessuna riga qui sotto li tocca.")

    # ── 2. Classifiche di turno ──────────────────────────────────────────
    gara_ids = {g.id for g in gare}
    fixes_campionato = [f for f in fixes if f.gara_id in gara_ids]
    logger.info("")
    logger.info("2) CLASSIFICHE DI TURNO")
    if not fixes_campionato:
        logger.info("   Nessun numero da correggere in questo campionato.")
    else:
        riscritture = [f for f in fixes_campionato if not f.is_discrepancy]
        scostamenti = [f for f in fixes_campionato if f.is_discrepancy]
        logger.info(
            "   %d numeri cambiano: %d stessa cifra in altra casella, "
            "%d non discendono dalle partite.",
            len(fixes_campionato),
            len(riscritture),
            len(scostamenti),
        )
        logger.info("   Le posizioni (1°, 2°, 3°…) restano quelle salvate.")
        if scostamenti:
            logger.info("   Righe con un numero che non torna:")
            _log_by_gara(scostamenti, limit=20)

    # ── 3. Accoppiamenti ─────────────────────────────────────────────────
    logger.info("")
    logger.info("3) ACCOPPIAMENTI")
    non_concluse = [g for g in gare if g.status != "completed"]
    logger.info(
        "   L'algoritmo Amalfi legge la classifica del turno precedente " "ordinata"
    )
    logger.info(
        "   per posizione e ne estrae il solo elenco dei giocatori "
        "(amalfi.py:669-687):"
    )
    logger.info("   non guarda mai i triangoli. Le posizioni non cambiano →")
    logger.info("   gli accoppiamenti non cambiano.")
    if non_concluse:
        logger.info(
            "   ⚠️  %d gare non risultano concluse: lì il prossimo match " "ricalcola",
            len(non_concluse),
        )
        logger.info("      comunque tutta la classifica, posizioni comprese.")
    else:
        logger.info("   Tutte le gare sono concluse: non ci saranno altri sorteggi.")

    # ── 4. Classifica generale: prima e dopo, per davvero ────────────────
    prima = _classifica_generale(campionato_id)
    for fix in fixes_campionato:
        row = (
            db.session.query(RoundClassification)
            .filter_by(
                gara_id=fix.gara_id,
                round_number=fix.round_number,
                user_id=fix.user_id,
            )
            .one_or_none()
        )
        if row is not None:
            row.racks_won = fix.new_racks_won
            row.rack_difference = fix.new_difference
    db.session.flush()
    dopo = _classifica_generale(campionato_id)
    db.session.rollback()

    logger.info("")
    logger.info("4) CLASSIFICA GENERALE DEL CAMPIONATO")
    logger.info("   (è ricalcolata a ogni apertura di pagina, non è salvata)")
    logger.info("")
    logger.info(
        "   %-4s %-22s %-10s   →   %-4s %-10s",
        "pos",
        "giocatore",
        "valore",
        "pos",
        "valore",
    )

    chiave = (
        "total_racks_won"
        if campionato.classification_system.value == "RACK"
        else "total_matches_won"
    )
    dopo_per_utente = {dati["username"]: (pos, dati) for pos, dati in dopo}
    for pos_prima, dati_prima in prima:
        nome = dati_prima["username"]
        pos_dopo, dati_dopo = dopo_per_utente.get(nome, (None, {}))
        marca = ""
        if pos_dopo is not None and pos_dopo != pos_prima:
            marca = f"  ({'sale' if pos_dopo < pos_prima else 'scende'})"
        logger.info(
            "   %-4s %-22s %-10s   →   %-4s %-10s%s",
            f"{pos_prima}°",
            nome[:22],
            dati_prima.get(chiave, 0),
            f"{pos_dopo}°" if pos_dopo else "—",
            dati_dopo.get(chiave, 0),
            marca,
        )

    cambi = sum(
        1
        for pos_prima, dati in prima
        if dopo_per_utente.get(dati["username"], (None, {}))[0] != pos_prima
    )
    logger.info("")
    if cambi:
        logger.info("   %d giocatori cambiano posizione.", cambi)
    else:
        logger.info("   Nessun giocatore cambia posizione: solo i numeri.")
    logger.info("")


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
    parser.add_argument(
        "--anteprima",
        type=int,
        metavar="CAMPIONATO_ID",
        help=(
            "Mostra tutto ciò che cambierebbe in un campionato — risultati "
            "delle gare, classifiche di turno, accoppiamenti, classifica "
            "generale prima e dopo — senza scrivere nulla."
        ),
    )
    args = parser.parse_args()

    app = bootstrap_and_create_app()
    with app.app_context():
        from models.base import db
        from models.competition.models import Gara

        if args.anteprima:
            gara_ids = [
                gid
                for (gid,) in db.session.query(Gara.id)
                .filter(Gara.campionato_id == args.anteprima)
                .all()
            ]
            logger.info(
                "Anteprima (nessuna scrittura) sul campionato %d…", args.anteprima
            )
            fixes, _ = _collect_fixes(gara_ids or None)
            _anteprima_campionato(args.anteprima, fixes)
            return 0

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
