"""Sposta la partecipazione a UNA gara da un giocatore a un altro.

Serve quando il direttore ha iscritto la persona sbagliata — due account con
nomi che si somigliano — e la gara è ormai finita: iscrizione, partite, rack,
esercizi, XP, ELO e classifica sono attribuiti a chi non ha giocato.

    # 1. INVENTARIO (default): sola lettura, dice cosa si muoverebbe
    venv/bin/python scripts/reassign_gara_participant.py \
        --gara 35 --from 16 --to 58 --by <ID_ADMIN>

    # 2. PROVA GENERALE su una copia del database (mostra la classifica finale)
    cp instance/billiard_campionato.db /tmp/prova.db
    venv/bin/python scripts/reassign_gara_participant.py \
        --gara 35 --from 16 --to 58 --by <ID_ADMIN> \
        --database sqlite:////tmp/prova.db --commit

    # 3. ESECUZIONE sul database vero
    venv/bin/python scripts/reassign_gara_participant.py \
        --gara 35 --from 16 --to 58 --by <ID_ADMIN> --commit

**La categoria non si eredita: si dichiara.** L'iscrizione si sposta intera,
quindi il destinatario si ritrova la categoria di chi era iscritto per errore —
la categoria di un'altra persona. In una gara con handicap è l'interruttore che
decide quali partite entrano nell'ELO (ADR-049), quindi va detta:

    ... --gara 38 --from 12 --to 52 --by <ID_ADMIN> --categoria E

L'inventario mostra **quali partite cambiano idoneità** con la categoria nuova:
è l'effetto più importante dello spostamento, e senza guardarlo lì lo si scopre
a rating già rigiocato.

**Perché la prova si fa su una copia e non con un rollback.** Un
``@transactional`` annidato chiama ``db.session.commit()``, e da SQLAlchemy 1.4
quel commit chiude la transazione *esterna* invece di rilasciare il savepoint:
i ricalcoli di gamification scrivono per davvero, e un annullamento finale non
troverebbe più niente da annullare. Con SQLite la copia del file è la prova
generale più onesta che ci sia — ed è anche il backup.

In produzione (PythonAnywhere) va lanciato con la **web app su Disabled** e con
un backup fresco: lo storage è NFS e SQLite non regge scritture concorrenti
(vedi CLAUDE.md). Il ricalcolo dell'ELO tocca tutti gli utenti per costruzione:
è path-dependent, non si corregge in un punto solo.
"""

import argparse
import json
import logging
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# Servono entrambe: la radice del progetto (per `app`, `models`) e la cartella
# scripts (per `prod_env`). L'ordine non è indifferente: la radice va inserita
# per ultima così da restare davanti a `scripts/` in sys.path.
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from prod_env import PRODUCTION_REQUIRED, bootstrap_and_create_app  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _print_classification(title, rows, highlight):
    print(f"\n  {title}")
    if not rows:
        print("    (vuota)")
        return
    for row in rows:
        mark = "  <<<" if row["user_id"] in highlight else ""
        extra = " ".join(
            f"{k}={v}"
            for k, v in row.items()
            if k not in ("position", "user_id", "username")
        )
        print(
            f"    {row['position']:>2}. {row['username']} (#{row['user_id']}) "
            f"{extra}{mark}"
        )


def _print_snapshot(label, snap, highlight):
    print(f"\n--- {label} ---")
    _print_classification("Classifica di gara", snap["gara_classification"], highlight)
    _print_classification(
        "Classifica di campionato", snap["campionato_classification"], highlight
    )
    print(f"\n  ELO: {snap['elo']}")
    print(f"  Livello/XP: {snap['level']}")


def _print_categoria(cat):
    """La categoria e — se cambia — quali partite entrano o escono dall'ELO."""
    corrente = cat["current"]["name"] if cat["current"] else "—"
    print(f"\nCATEGORIA nella gara: {corrente}")

    if cat["requested"] is None:
        print("  (non richiesta: resta quella ereditata dal sorgente)")
        return

    if cat["target"] is None:
        print("  → assegnazione TOLTA")
    else:
        nuova = cat["target"]["name"]
        nota = "" if cat["target"]["exists"] else "  (voce nuova, verrà creata)"
        print(f"  → {nuova}{nota}")

    applied = cat.get("applied")
    if applied and not applied["skipped"]:
        print(f"  scritta su {applied['touched']} iscrizione/i")

    if not cat["elo_effect"]:
        print("  Idoneità ELO delle partite: invariata.")
        return

    print("\n  PARTITE CHE CAMBIANO IDONEITÀ ELO")
    for riga in cat["elo_effect"]:
        prima = riga["before"] or "CONTAVA"
        dopo = riga["after"] or "CONTA"
        print(
            f"    turno {riga['round_number']} vs {riga['opponent']} "
            f"(match {riga['match_id']}): {prima} → {dopo}"
        )
    print(
        "\n  ⚠️  L'ELO è path-dependent: far entrare o uscire una partita "
        "sposta il rating\n      di tutti, non solo di chi vi ha giocato."
    )


def _print_report(report):
    source_id = report["source"]["id"]
    target_id = report["target"]["id"]
    highlight = {source_id, target_id}

    mode = (
        "INVENTARIO (sola lettura, niente è stato scritto)"
        if report["read_only"]
        else "ESEGUITO"
    )
    print("=" * 72)
    print(mode)
    print(
        f"Gara {report['gara_id']} «{report['gara_name']}» "
        f"(campionato {report['campionato_id']})"
    )
    print(
        f"{report['source']['username']} (#{source_id})  →  "
        f"{report['target']['username']} (#{target_id})"
    )
    print("=" * 72)

    print("\nRIGHE DA SPOSTARE" if report["read_only"] else "\nRIGHE SPOSTATE")
    if report["moved_rows"]:
        for key, count in sorted(report["moved_rows"].items()):
            print(f"  {count:>4}  {key}")
    else:
        print("  (nessuna)")

    if report["deleted_rows"]:
        print("\nRIGHE DA CANCELLARE (preferenze di visibilità del sorgente)")
        for key, count in sorted(report["deleted_rows"].items()):
            print(f"  {count:>4}  {key}")

    xp = report["moved_xp"]
    print(f"\nXP: {xp['count']} movimenti, {xp['xp_amount']} XP totali")

    _print_categoria(report["categoria"])

    if not report["read_only"]:
        gam = report["gamification"]
        revoked = gam["source_revoked_achievements"]
        print(
            f"\nTRAGUARDI TOLTI a #{source_id}: "
            f"{', '.join(revoked) if revoked else '(nessuno)'}"
        )
        for who, label in ((source_id, "source"), (target_id, "target")):
            state = gam[label]
            print(
                f"  #{who}: livello {state['current_level']}, "
                f"traguardi sbloccati ora {state['achievements_unlocked']}"
            )

    _print_snapshot("PRIMA", report["before"], highlight)
    if not report["read_only"]:
        _print_snapshot("DOPO", report["after"], highlight)

    if report["manual_review"]:
        print("\nDA GUARDARE A MANO")
        for note in report["manual_review"]:
            print(f"  - {note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gara", type=int, required=True, help="ID della gara")
    parser.add_argument(
        "--from", dest="source", type=int, required=True, help="ID iscritto per errore"
    )
    parser.add_argument(
        "--to", dest="target", type=int, required=True, help="ID che doveva giocare"
    )
    parser.add_argument(
        "--by", type=int, required=True, help="ID dell'admin che esegue la correzione"
    )
    parser.add_argument(
        "--categoria",
        default=None,
        help=(
            "Categoria da assegnare al destinatario in questa gara, creandola "
            "se non è in elenco. Senza il flag la categoria resta quella "
            "ereditata dal sorgente — che è di un'altra persona. Stringa vuota "
            "per toglierla."
        ),
    )
    parser.add_argument(
        "--commit", action="store_true", help="Scrive davvero (default: sola lettura)"
    )
    parser.add_argument(
        "--database",
        help="URI SQLAlchemy alternativo, per la prova generale su una copia",
    )
    parser.add_argument("--json", action="store_true", help="Report in JSON")
    args = parser.parse_args()

    if args.database:
        # Prima di costruire l'app: la config legge l'ambiente all'avvio.
        os.environ["DATABASE_URL"] = args.database

    # L'app si costruisce DOPO aver caricato le env: importare `app` in cima al
    # file congelerebbe un ambiente vuoto (presidio: test_script_import_order).
    app = bootstrap_and_create_app(required=PRODUCTION_REQUIRED + ("ENCRYPTION_KEY",))

    from models import db
    from models.competition.participant_reassign_service import (
        GaraParticipantReassignService,
    )

    with app.app_context():
        print(f"Database: {app.config.get('SQLALCHEMY_DATABASE_URI')}\n")
        try:
            if args.commit:
                report = GaraParticipantReassignService.reassign(
                    gara_id=args.gara,
                    source_id=args.source,
                    target_id=args.target,
                    performed_by_id=args.by,
                    categoria=args.categoria,
                )
                db.session.commit()
            else:
                report = GaraParticipantReassignService.plan(
                    gara_id=args.gara,
                    source_id=args.source,
                    target_id=args.target,
                    performed_by_id=args.by,
                    categoria=args.categoria,
                )
        except Exception as exc:
            db.session.rollback()
            logger.error("Spostamento annullato: %s", exc)
            return 1

        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        else:
            _print_report(report)

        if not args.commit:
            print(
                "\nSola lettura: niente è stato scritto. Prova generale su una "
                "copia con --database, poi --commit sul database vero."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
