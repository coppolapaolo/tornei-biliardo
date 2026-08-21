"""Toglie gli XP incassati dalle quest-fantasma delle settimane passate.

Il difetto (PR #191): le quest settimanali delle settimane passate restavano
ACTIVE in colonna e arruolavano d'ufficio chi giocava, che le «completava»
tutte in un colpo — XP triplicati alla terza settimana dal varo. La logica di
individuazione e riparazione sta in `models/gamification/quest_repair.py`;
questo script è solo il volante: dry-run per default, `--apply` per scrivere.

Il livello degli utenti toccati viene ricostruito dal ledger ripulito; i
traguardi già sbloccati restano anche se il livello scende (scelta di
`rebuild_for_user`, documentata lì).

Usage:
    python scripts/rimborsa_quest_fantasma.py            # dry-run
    python scripts/rimborsa_quest_fantasma.py --apply    # scrive

In produzione va lanciato con la web app su **Disabled** (SQLite su NFS), e
con l'interprete del venv:

    venv/bin/python scripts/rimborsa_quest_fantasma.py
"""

import argparse
import logging
import os
import sys

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Scrive davvero. Senza, elenca soltanto cosa verrebbe tolto.",
    )
    args = parser.parse_args()

    app = bootstrap_and_create_app()

    with app.app_context():
        from models.gamification.quest_repair import (
            find_ghost_participations,
            repair_ghost_participations,
        )

        ghosts = find_ghost_participations()
        if not ghosts:
            logger.info("Nessuna partecipazione fantasma: niente da fare.")
            return 0

        logger.info("Partecipazioni fantasma trovate: %s", len(ghosts))
        for g in ghosts:
            logger.info(
                "  utente %-4s quest %-3s (settimana %s) «%s» — %s%s",
                g.user_id,
                g.quest_id,
                g.quest_week_start,
                g.quest_name,
                "COMPLETATA, -%s XP" % g.xp_awarded if g.completed else "solo iscritta",
                (
                    ""
                    if not g.completed or len(g.transaction_ids) == 1
                    else "  ⚠️ transazioni trovate: %s" % len(g.transaction_ids)
                ),
            )

        totale_xp = sum(g.xp_awarded for g in ghosts if g.completed)
        utenti = sorted({g.user_id for g in ghosts})
        logger.info("XP da rientrare: %s, utenti toccati: %s", totale_xp, utenti)

        if not args.apply:
            logger.info("Dry-run: nessuna modifica. Rilancia con --apply.")
            return 0

        report = repair_ghost_participations()
        logger.info("Fatto: %s", report)
        return 0


if __name__ == "__main__":
    sys.exit(main())
