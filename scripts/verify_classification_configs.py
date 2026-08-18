#!/usr/bin/env python3
"""Verifica le configurazioni delle gare e come sono state classificate.

Due controlli distinti, entrambi di sola lettura:

1. **Configurazioni valide** — ogni gara contro le regole di
   `models/competition/validators.py`.
2. **Criterio storico** — quali gare sono state classificate con un criterio
   diverso da quello che il direttore aveva scelto. Fino al 2026-05-21 il
   calcolatore sceglieva la strategia di classifica dalla **strategia di
   accoppiamento** invece che dal **sistema di classifica** (commit `ca3829b8`,
   «fix B14»): dove le due configurazioni divergono, la classifica mostrata
   allora ordinava per il criterio sbagliato. Il fix è arrivato in due tempi —
   un secondo percorso di calcolo è stato allineato solo il 2026-07-28
   (`335e544f`) — e lo stesso equivoco è stato corretto a livello di campionato
   il 2026-08-18 (ADR-047).

Usage:
    python scripts/verify_classification_configs.py           # solo lettura
    python scripts/verify_classification_configs.py --fix     # corregge (interattivo)

In produzione, con l'interprete del venv:

    venv/bin/python scripts/verify_classification_configs.py
"""

import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
# Servono entrambe: la radice del progetto (per `models`) e la cartella scripts
# (per `prod_env`). La radice per ultima, così resta davanti in sys.path.
sys.path.insert(0, _HERE)
sys.path.insert(0, str(Path(__file__).parent.parent))

# NB: `app` non si importa qui. `bootstrap_and_create_app` carica le env dal
# file WSGI e **poi** importa l'app: console e scheduled task non ereditano
# quelle variabili, e un import in cima congelerebbe un ambiente vuoto.
# Invariante presidiata da tests/new/unit/test_script_import_order.py.
from prod_env import bootstrap_and_create_app  # noqa: E402
from models.base import db  # noqa: E402
from models.competition.models import Gara  # noqa: E402
from models.status_enum import ClassificationSystem  # noqa: E402
from models.matchmaking.configuration import MatchmakingStrategy  # noqa: E402
from models.competition.validators import validate_gara  # noqa: E402


def verify_all_gare(fix_mode: bool = False) -> tuple[int, int, int]:
    """Verify all gare configurations.

    Returns:
        Tuple of (total, valid, invalid) counts
    """
    gare = Gara.query.all()
    total = len(gare)
    valid = 0
    invalid = 0

    print(f"\n{'='*60}")
    print(f"Verifying {total} gare...")
    print(f"{'='*60}\n")

    invalid_gare = []

    for gara in gare:
        # `resolve` conosce il plurale storico "RACKS" e ripiega su WINS.
        # Il costruttore secco sollevava su quel valore, e il ripiego
        # silenzioso faceva validare come "a vittorie" una gara a triangoli.
        class_sys = ClassificationSystem.resolve(gara.classification_system)

        errors, warnings = validate_gara(gara, classification_system=class_sys)

        if errors:
            invalid += 1
            invalid_gare.append((gara, errors, warnings))
            print(f"❌ Gara {gara.id}: {gara.name or f'Gara #{gara.number}'}")
            print(
                f"   Config: strategy={gara.matchmaking_strategy}, "
                f"odd={gara.odd_number_policy}, "
                f"class={gara.classification_system}"
            )
            for error in errors:
                print(f"   ERROR: {error}")
            if warnings:
                for warning in warnings:
                    print(f"   WARNING: {warning}")
            print()
        else:
            valid += 1
            if warnings:
                print(f"⚠️  Gara {gara.id}: {gara.name or f'Gara #{gara.number}'}")
                for warning in warnings:
                    print(f"   WARNING: {warning}")

    print(f"\n{'='*60}")
    print(f"Results: {valid} valid, {invalid} invalid out of {total} gare")
    print(f"{'='*60}\n")

    if fix_mode and invalid_gare:
        print("Fix mode enabled. Attempting to fix invalid configurations...\n")
        for gara, errors, _ in invalid_gare:
            fix_gara(gara, errors)

    return total, valid, invalid


def fix_gara(gara: Gara, errors: list[str]) -> None:
    """Attempt to fix an invalid gara configuration.

    Common fixes:
    - RACK + bye -> bye_with_challenge
    - Missing classification_system -> WINS
    """
    print(f"Fixing Gara {gara.id}: {gara.name or f'Gara #{gara.number}'}")

    changes = []

    # Fix: RACK + bye semplice -> bye_with_challenge
    if gara.classification_system == "RACK" and gara.odd_number_policy == "bye":
        gara.odd_number_policy = "bye_with_challenge"
        changes.append("odd_number_policy: bye -> bye_with_challenge")

    # Fix: Missing classification_system -> WINS
    if not gara.classification_system:
        gara.classification_system = "WINS"
        changes.append("classification_system: NULL -> WINS")

    if changes:
        print(f"   Changes: {', '.join(changes)}")
        try:
            db.session.commit()
            print("   ✅ Fixed successfully")
        except Exception as e:
            db.session.rollback()
            print(f"   ❌ Failed to fix: {e}")
    else:
        print("   ⚠️  No automatic fix available")
    print()


def verify_campionati() -> None:
    """Verify campionato configurations."""
    from models.campionato.models import Campionato

    campionati = Campionato.query.all()
    print(f"\n{'='*60}")
    print(f"Verifying {len(campionati)} campionati...")
    print(f"{'='*60}\n")

    for camp in campionati:
        class_sys = camp.default_classification_system or "WINS"
        odd_policy = camp.default_odd_policy or "bye"

        # Check compatibility
        issues = []
        if class_sys == "RACK" and odd_policy == "bye":
            issues.append("RACK + bye semplice non compatibili")

        if issues:
            print(f"⚠️  Campionato {camp.id}: {camp.name}")
            print(f"   Config: class={class_sys}, odd={odd_policy}")
            for issue in issues:
                print(f"   ISSUE: {issue}")
        else:
            print(f"✅ Campionato {camp.id}: {camp.name} (class={class_sys})")

    print()


# Data in cui il calcolatore ha smesso di scegliere il criterio dalla strategia
# di accoppiamento (commit ca3829b8). Serve solo per il testo del report: quali
# classifiche siano davvero rimaste indietro si legge dai dati, non dalla data.
DATA_FIX_B14 = "2026-05-21"


def _criterio_applicato_allora(gara) -> ClassificationSystem:
    """Il criterio che il calcolatore usava prima del fix B14.

    La mappa era `{"random": "random_round"}` con default `amalfi_round`: la
    strategia di accoppiamento decideva, e tutto ciò che non era accoppiamento
    casuale veniva classificato a vittorie.
    """
    if gara.matchmaking_strategy == MatchmakingStrategy.RANDOM.value:
        return ClassificationSystem.RACK
    return ClassificationSystem.WINS


def report_criterio_storico() -> int:
    """Elenca le gare in cui accoppiamento e sistema di classifica divergono.

    Sono le gare che, se calcolate prima del fix B14, mostravano una classifica
    ordinata con un criterio diverso da quello scelto dal direttore.

    Returns:
        Numero di gare discordanti trovate.
    """
    from models.classification.models import RoundClassification

    print(f"\n{'='*60}")
    print("CRITERIO STORICO DI CLASSIFICA")
    print(f"{'='*60}")
    print(
        f"Fino al {DATA_FIX_B14} il criterio veniva scelto dalla strategia di\n"
        "accoppiamento invece che dal sistema di classifica. Dove le due\n"
        "divergono, la classifica di allora ordinava per il criterio sbagliato.\n"
    )

    discordanti = []
    for gara in Gara.query.order_by(Gara.date).all():
        scelto = ClassificationSystem.resolve(gara.classification_system)
        applicato = _criterio_applicato_allora(gara)
        if scelto != applicato:
            discordanti.append((gara, scelto, applicato))

    if not discordanti:
        print("✅ Nessuna gara discordante: in ogni gara il criterio applicato")
        print("   allora coincideva con quello scelto dal direttore.\n")
        return 0

    etichette = {
        ClassificationSystem.RACK: "triangoli totali",
        ClassificationSystem.WINS: "vittorie",
        ClassificationSystem.POSITION: "punti per piazzamento",
    }

    for gara, scelto, applicato in discordanti:
        # Una classifica riscritta dopo la separazione delle colonne
        # (2026-07-28) ha `racks_won` valorizzato: quella gara è già stata
        # ricalcolata col criterio corretto, comunque fosse nata.
        ricalcolata = (
            db.session.query(RoundClassification)
            .filter(
                RoundClassification.gara_id == gara.id,
                RoundClassification.racks_won.isnot(None),
            )
            .first()
            is not None
        )
        stato = (
            "già ricalcolata col criterio corretto"
            if ricalcolata
            else "MAI ricalcolata: le classifiche salvate sono quelle di allora"
        )
        nome = gara.name or f"Gara #{gara.number}"
        print(f"⚠️  Gara {gara.id}: {nome}")
        print(f"   Data: {gara.date}  |  Stato: {gara.status}")
        print(f"   Accoppiamento: {gara.matchmaking_strategy}")
        print(
            f"   Sistema scelto: {etichette[scelto]}  →  "
            f"applicato allora: {etichette[applicato]}"
        )
        print(f"   {stato}")
        print()

    mai_ricalcolate = sum(
        1
        for gara, _, _ in discordanti
        if db.session.query(RoundClassification)
        .filter(
            RoundClassification.gara_id == gara.id,
            RoundClassification.racks_won.isnot(None),
        )
        .first()
        is None
    )
    print(f"{len(discordanti)} gare discordanti, di cui {mai_ricalcolate} mai")
    print("ricalcolate dopo il fix.\n")
    return len(discordanti)


def main():
    fix_mode = "--fix" in sys.argv

    app = bootstrap_and_create_app()
    with app.app_context():
        # Verify gare
        total, valid, invalid = verify_all_gare(fix_mode)

        # Verify campionati
        verify_campionati()

        # Come sono state classificate, storicamente
        discordanti = report_criterio_storico()

        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Gare: {valid}/{total} valid")
        if discordanti:
            print(f"Criterio storico: {discordanti} gare discordanti (vedi sopra)")
        if invalid > 0:
            print(f"⚠️  {invalid} gare need attention")
            if not fix_mode:
                print("   Run with --fix to attempt automatic fixes")
        else:
            print("✅ All configurations are valid!")
        print()

        return 0 if invalid == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
