"""Cambia la disciplina di una gara **già iniziata**, che l'interfaccia non tocca.

**Perché serve uno script.** La disciplina si modifica da `edit_gara`, che è
protetta da `Gara.can_be_modified()`: quella diventa falsa appena arriva la
prima iscrizione. È la scelta giusta per una gara viva — cambiare specialità a
iscrizioni aperte sposterebbe le regole sotto i piedi di chi si è iscritto — ma
lascia senza rimedio il caso opposto: la gara è finita, e la disciplina scritta
non è quella che si è giocata. Succede quando la specialità non esisteva ancora
in elenco e il direttore ha scelto la più vicina, scrivendo quella vera nelle
note.

**Cosa cambia.** Solo `gara.discipline`. Le partite e i turni la ereditano:
`Match.discipline` e `RoundConfiguration.discipline` sono override *nullable*,
e valgono NULL quando nessuno ha scelto diversamente per quel turno.

**Cosa NON cambia da solo.** Gli override che nominano ancora la disciplina
vecchia. Un override non dice se è una scelta del direttore per quel turno o la
vecchia impostazione materializzata: lo script li **elenca** e li tocca solo con
`--propagate-overrides`, e anche allora sposta soltanto quelli uguali al valore
che si sta lasciando. Un override che nomina una terza disciplina resta dov'è.

Non tocca lo spareggio: `tiebreaker.discipline` è la disciplina con cui lo
spareggio *è stato giocato*, non quella della gara.

    # 1. INVENTARIO (default): sola lettura, dice cosa cambierebbe
    venv/bin/python scripts/set_gara_discipline.py --gara 38 --discipline 7_ball

    # 2. ESECUZIONE
    venv/bin/python scripts/set_gara_discipline.py --gara 38 --discipline 7_ball \
        --commit

In produzione (PythonAnywhere) va lanciato con la web app su **Disabled**: lo
storage è NFS e i lock di SQLite non sono affidabili (vedi CLAUDE.md).
"""

import argparse
import logging
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# Servono entrambe: la radice del progetto (per `app`, `models`) e la cartella
# scripts (per `prod_env`). La radice va inserita per ultima così da restare
# davanti a `scripts/` in sys.path.
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from prod_env import bootstrap_and_create_app  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _label(discipline_value):
    """`8_ball` → `Palla 8 (8_ball)`, e il valore grezzo se fuori vocabolario."""
    from models.status_enum import Discipline

    if not discipline_value:
        return "—"
    member = Discipline.normalize(discipline_value)
    if member is None:
        return f"?? ({discipline_value})"
    return f"{member.display_name} ({member.value})"


def _overrides(gara_id: int):
    """Gli override di disciplina della gara, per turno / partita / set."""
    from models.base import db
    from models.competition.round_configuration import RoundConfiguration
    from models.match.models import Match
    from models.match.set_models import Set

    rounds = (
        db.session.query(RoundConfiguration.round_number, RoundConfiguration.discipline)
        .filter(
            RoundConfiguration.gara_id == gara_id,
            RoundConfiguration.discipline.isnot(None),
        )
        .order_by(RoundConfiguration.round_number)
        .all()
    )

    matches = (
        db.session.query(Match.discipline, db.func.count(Match.id))
        .filter(Match.gara_id == gara_id, Match.discipline.isnot(None))
        .group_by(Match.discipline)
        .all()
    )

    sets = (
        db.session.query(Set.discipline, db.func.count(Set.id))
        .join(Match, Set.match_id == Match.id)
        .filter(Match.gara_id == gara_id, Set.discipline.isnot(None))
        .group_by(Set.discipline)
        .all()
    )

    return {"rounds": rounds, "matches": matches, "sets": sets}


def _print_report(gara, target: str, overrides, propagate: bool) -> None:
    print("=" * 72)
    print(f"Gara {gara.id} «{gara.name}» — stato: {gara.status}")
    print(f"Disciplina attuale: {_label(gara.discipline)}")
    print(f"Disciplina nuova:   {_label(target)}")
    print("=" * 72)

    old = gara.discipline
    print("\nOVERRIDE PER TURNO (RoundConfiguration.discipline)")
    if overrides["rounds"]:
        for round_number, value in overrides["rounds"]:
            sorte = (
                "→ spostato"
                if propagate and value == old
                else (
                    "resta (disciplina diversa)" if value != old else "RESTA INDIETRO"
                )
            )
            print(f"  turno {round_number}: {_label(value)}  {sorte}")
    else:
        print("  (nessuno: i turni ereditano dalla gara)")

    for chiave, etichetta in (
        ("matches", "OVERRIDE PER PARTITA (Match.discipline)"),
        ("sets", "OVERRIDE PER SET (Set.discipline)"),
    ):
        print(f"\n{etichetta}")
        if overrides[chiave]:
            for value, count in overrides[chiave]:
                sorte = (
                    "→ spostati"
                    if propagate and value == old
                    else (
                        "restano (disciplina diversa)"
                        if value != old
                        else "RESTANO INDIETRO"
                    )
                )
                print(f"  {count:>4}  {_label(value)}  {sorte}")
        else:
            print("  (nessuno: si eredita dalla gara)")

    rimasti = (
        [value for _, value in overrides["rounds"]]
        + [value for value, _ in overrides["matches"]]
        + [value for value, _ in overrides["sets"]]
    )
    if not propagate and any(value == old for value in rimasti):
        print(
            "\n⚠️  Restano override che nominano la disciplina vecchia: la gara "
            "direbbe una cosa\n    e quei turni/partite un'altra. Rilancia con "
            "--propagate-overrides per spostarli."
        )


def _propagate(gara_id: int, old: str, target: str) -> dict:
    """Sposta al nuovo valore i soli override uguali a quello vecchio."""
    from models.base import db
    from models.competition.round_configuration import RoundConfiguration
    from models.match.models import Match
    from models.match.set_models import Set

    moved = {}
    moved["round_configuration"] = (
        db.session.query(RoundConfiguration)
        .filter(
            RoundConfiguration.gara_id == gara_id,
            RoundConfiguration.discipline == old,
        )
        .update({RoundConfiguration.discipline: target}, synchronize_session=False)
    )
    moved["match"] = (
        db.session.query(Match)
        .filter(Match.gara_id == gara_id, Match.discipline == old)
        .update({Match.discipline: target}, synchronize_session=False)
    )
    set_ids = [
        row[0]
        for row in db.session.query(Set.id)
        .join(Match, Set.match_id == Match.id)
        .filter(Match.gara_id == gara_id, Set.discipline == old)
        .all()
    ]
    moved["set"] = (
        db.session.query(Set)
        .filter(Set.id.in_(set_ids))
        .update({Set.discipline: target}, synchronize_session=False)
        if set_ids
        else 0
    )
    return moved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gara", type=int, required=True, help="ID della gara")
    parser.add_argument(
        "--discipline",
        required=True,
        help="Valore canonico della disciplina, es. 7_ball",
    )
    parser.add_argument(
        "--propagate-overrides",
        action="store_true",
        help=(
            "Sposta anche gli override per turno/partita/set che nominano la "
            "disciplina vecchia. Quelli che ne nominano una terza restano."
        ),
    )
    parser.add_argument(
        "--commit", action="store_true", help="Scrive davvero (default: sola lettura)"
    )
    parser.add_argument(
        "--database",
        help="URI SQLAlchemy alternativo, per provare su una copia del file .db",
    )
    args = parser.parse_args()

    if args.database:
        # Prima di costruire l'app: la config legge l'ambiente all'avvio.
        os.environ["DATABASE_URL"] = args.database

    # L'app si costruisce DOPO aver caricato le env: importare `app` in cima al
    # file congelerebbe un ambiente vuoto (presidio: test_script_import_order).
    app = bootstrap_and_create_app()

    from models.base import db
    from models.competition.models import Gara
    from models.status_enum import Discipline

    with app.app_context():
        print(f"Database: {app.config.get('SQLALCHEMY_DATABASE_URI')}\n")

        # `print` e non `logger.error`: un argomento sbagliato è un errore di
        # chi digita, non un guasto dell'applicazione, e da uno script gli
        # eventi di log finiscono davvero su GlitchTip.
        target = Discipline.normalize(args.discipline)
        if target is None:
            valide = ", ".join(d.value for d in Discipline)
            print(
                f"Disciplina sconosciuta: {args.discipline!r}. Valori validi: {valide}"
            )
            return 1

        gara = db.session.get(Gara, args.gara)
        if gara is None:
            print(f"Gara {args.gara} non trovata")
            return 1

        old = gara.discipline
        overrides = _overrides(gara.id)
        _print_report(gara, target.value, overrides, args.propagate_overrides)

        if old == target.value and not args.propagate_overrides:
            print("\nLa gara è già su questa disciplina: niente da fare.")
            return 0

        if not args.commit:
            print("\n(sola lettura: niente è stato scritto — rilancia con --commit)")
            return 0

        gara.discipline = target.value
        moved = (
            _propagate(gara.id, old, target.value) if args.propagate_overrides else {}
        )
        db.session.commit()

        print(f"\nScritto: gara {gara.id} → {_label(target.value)}")
        for tabella, count in moved.items():
            if count:
                print(f"  override spostati in {tabella}: {count}")
        logger.info(
            "Disciplina gara %s: %s → %s (override spostati: %s)",
            gara.id,
            old,
            target.value,
            moved or "nessuno",
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
