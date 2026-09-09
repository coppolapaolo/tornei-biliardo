"""Fonde le iscrizioni doppie dello stesso giocatore alla stessa gara.

    venv/bin/python scripts/fix_iscrizioni_duplicate.py             # prova generale
    venv/bin/python scripts/fix_iscrizioni_duplicate.py --commit    # scrive davvero

Fino ad agosto 2026 nulla impediva a un giocatore di risultare iscritto due
volte alla stessa gara: l'unicità di `(gara_id, user_id)` stava in
`InscriptionService.inscribe_user` e non nel database, e l'unione di due
account — che riassegna le chiavi esterne in SQL — la scavalcava. È così che
nella gara 39 di produzione lo stesso giocatore compariva due volte, una con la
categoria assegnata dal direttore e una senza.

La regola di fusione è quella di `models/competition/inscription_dedup.py`:
sopravvive la riga più vecchia, i campi vuoti si riempiono con quelli
dell'altra, lo stato si prende in blocco dalla riga più avanzata (attivo >
lista d'attesa > ritirato).

Serve **prima** della migration `20260901_inscription_unique_gara_user`, che fa
la stessa riparazione ma di notte e senza mostrare niente: questo script la
anticipa per far vedere cosa verrebbe toccato. Se lo si lancia con `--commit`,
la migration troverà zero doppioni e si limiterà a creare l'indice.

⚠️  In produzione va eseguito con la web app su **Disabled** (storage NFS, lock
SQLite inaffidabili), riabilitandola subito dopo.
"""

import sys
import os
import argparse
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.prod_env import bootstrap_and_create_app  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _descrivi(iscrizione) -> str:
    stato = (
        "ritirata"
        if iscrizione.is_withdrawn
        else ("lista d'attesa" if iscrizione.is_waitlist else "attiva")
    )
    return (
        f"    #{iscrizione.id} creata {iscrizione.created_at} — {stato}, "
        f"categoria {iscrizione.categoria_id}, squadra {iscrizione.squadra_id}, "
        f"ordine {iscrizione.initial_order}"
    )


def ripara(commit: bool = False) -> int:
    app = bootstrap_and_create_app()

    from models import db
    from models.competition.inscription_dedup import fondi_gruppo, trova_duplicati

    with app.app_context():
        if commit:
            logger.info("Le modifiche VERRANNO scritte sul database.")
        else:
            logger.info("PROVA GENERALE: non viene scritto niente.")

        gruppi = trova_duplicati()
        if not gruppi:
            logger.info("Nessuna iscrizione doppia trovata.")
            return 0

        for (gara_id, user_id), iscrizioni in sorted(gruppi.items()):
            logger.info(
                "Gara %s, giocatore %s: %s iscrizioni",
                gara_id,
                user_id,
                len(iscrizioni),
            )
            for iscrizione in iscrizioni:
                logger.info(_descrivi(iscrizione))

            piano = fondi_gruppo(iscrizioni)
            if piano is None:  # pragma: no cover - trova_duplicati dà ≥2 righe
                continue
            logger.info(
                "  → resta #%s%s; cancellate %s",
                piano.sopravvissuta_id,
                f", aggiornata con {piano.valori}" if piano.valori else "",
                ", ".join(f"#{i}" for i in piano.da_cancellare),
            )

        if commit:
            db.session.commit()
            logger.info("Scritto. Gruppi riparati: %s", len(gruppi))
        else:
            db.session.rollback()
            logger.info(
                "Prova generale conclusa, niente scritto. Gruppi trovati: %s",
                len(gruppi),
            )
        return len(gruppi)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fonde le iscrizioni doppie alla stessa gara."
    )
    parser.add_argument(
        "--commit", action="store_true", help="Scrive le modifiche sul database"
    )
    args = parser.parse_args()
    raise SystemExit(ripara(commit=args.commit))
