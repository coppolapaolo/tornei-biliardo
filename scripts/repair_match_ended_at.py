"""Ricostruisce la data di fine delle partite di gara che ne sono prive.

**Perché serve.** `BaseMatchMixin._complete_match_after_confirmation` scriveva
la data di fine dentro un `if hasattr(self, "completed_at")`. La colonna era
stata rinominata `ended_at`, quindi da quel rinomino in poi il guard è sempre
stato falso e la riga non si è più eseguita: nessun errore, nessun test rosso,
solo partite senza data. Il difetto è corretto dal 2026-08-21; questo script
ripara le righe già scritte.

**Perché non è un dettaglio.** Le partite rimaste senza data non sono un
campione casuale: sono **quelle chiuse dai due giocatori con la doppia
conferma** (`CONFIRMED_BY_BOTH`). Quelle chiuse dal direttore passano da
`MatchStateService.to_completed`, che la data la scrive. In produzione erano
40 su 367 (censimento del 2026-08-21).

E un `ended_at` nullo non è solo un buco: SQLite ordina i NULL **per primi**,
quindi `RatingCalculationService.recalculate_all_elo`, che rigioca la storia
con `ORDER BY ended_at ASC`, processava quelle partite *prima di tutte le
altre*, quando ogni giocatore vale ancora il rating di partenza. Il pool
globale invece le spingeva in coda con un sentinel esplicito. I due pool
ricostruivano quindi due storie diverse, e l'Elo dipende dall'ordine.

**Da dove viene la data ricostruita**, in ordine di preferenza:

1. la **seconda conferma** (`max(player1_confirmed_at, player2_confirmed_at)`):
   è l'istante esatto in cui la partita si è chiusa, perché è la conferma
   stessa a chiuderla;
2. l'**ultimo rack** segnato (`Rack.created_at`): quando si è smesso di
   giocare. Approssima per difetto, di quanto ci mette il secondo a
   confermare;
3. l'ultimo rack **anche se cancellato**: per le partite corrette a posteriori;
4. **data e ora della gara**: ultimo appiglio, buono solo a collocare la
   partita nel mese giusto.

Chi non ha nemmeno quello resta com'è e viene elencato: inventare una data è
peggio che non averla.

**Dopo la riparazione va rifatto il ricalcolo dell'Elo** (`recalc_elo.py`):
cambia l'ordine cronologico, quindi cambiano i rating. Lo script lo ricorda
ma non lo fa da sé — è un'operazione diversa, con i suoi tempi.

⚠️ **Scrive sul DB**: in produzione va eseguito con la web app **Disabled**
(vedi CLAUDE.md, incidenti 2026-06-10 e 2026-08-17).

Uso::

    venv/bin/python scripts/repair_match_ended_at.py            # analisi
    venv/bin/python scripts/repair_match_ended_at.py --apply    # scrive
"""

import argparse
import logging
import os
import sys
from collections import Counter
from datetime import datetime
from typing import Any, List, Optional, Tuple

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

#: Le fonti da cui si ricava la data, dalla più precisa alla più grossolana.
FONTI = (
    "seconda conferma",
    "ultimo rack",
    "ultimo rack (anche cancellato)",
    "data della gara",
)


def ricostruisci(match: Any) -> Tuple[Optional[datetime], Optional[str]]:
    """La data di fine più credibile per questa partita, e da dove viene.

    Restituisce ``(None, None)`` quando non c'è alcun appiglio: una data
    inventata sarebbe peggio di un buco, perché smetterebbe di dichiararsi
    tale.
    """
    conferme = [
        quando
        for quando in (
            getattr(match, "player1_confirmed_at", None),
            getattr(match, "player2_confirmed_at", None),
        )
        if quando is not None
    ]
    if conferme:
        # La *seconda* conferma è quella che ha chiuso la partita.
        return max(conferme), FONTI[0]

    racks = list(match.racks or [])
    vivi = [r for r in racks if not getattr(r, "is_deleted", False)]
    for candidati, fonte in ((vivi, FONTI[1]), (racks, FONTI[2])):
        istanti = [
            t
            for r in candidati
            for t in (getattr(r, "created_at", None), getattr(r, "added_at", None))
            if t is not None
        ]
        if istanti:
            return max(istanti), fonte

    gara = getattr(match, "gara", None)
    if gara is not None and getattr(gara, "date", None) is not None:
        ora = getattr(gara, "time", None)
        return (
            datetime.combine(gara.date, ora)
            if ora
            else datetime.combine(gara.date, datetime.min.time())
        ), FONTI[3]

    return None, None


def _da_riparare() -> List[Any]:
    """Le partite finite a cui manca la data di fine."""
    from models.match.models import Match
    from models.status_enum import MatchStatus

    return (
        Match.query.filter(
            Match.status.in_(MatchStatus.finished_values()),
            Match.ended_at.is_(None),
        )
        .order_by(Match.id.asc())
        .all()
    )


def _analizza(matches: List[Any]) -> Tuple[List[Tuple[Any, datetime, str]], List[Any]]:
    riparabili: List[Tuple[Any, datetime, str]] = []
    persi: List[Any] = []
    for match in matches:
        quando, fonte = ricostruisci(match)
        if quando is None or fonte is None:
            persi.append(match)
        else:
            riparabili.append((match, quando, fonte))
    return riparabili, persi


def _applica(riparabili: List[Tuple[Any, datetime, str]]) -> int:
    from models.base import db

    for match, quando, _fonte in riparabili:
        match.ended_at = quando
        db.session.add(match)
    db.session.commit()
    return len(riparabili)


def _report(
    matches: List[Any],
    riparabili: List[Tuple[Any, datetime, str]],
    persi: List[Any],
    applied: bool,
) -> None:
    from models.status_enum import MatchStatus

    logger.info("")
    logger.info("Partite finite senza data di fine ... %d", len(matches))
    if not matches:
        logger.info("Niente da fare.")
        return

    stati = Counter(m.status for m in matches)
    for stato, quante in sorted(stati.items()):
        etichetta = (
            "chiusa dai due giocatori"
            if stato == MatchStatus.CONFIRMED_BY_BOTH.value
            else "chiusa dal direttore/forfait"
        )
        logger.info("    %-12s %-28s %d", stato, etichetta, quante)

    logger.info("")
    fonti = Counter(fonte for _m, _q, fonte in riparabili)
    logger.info("Data ricostruita da:")
    for fonte in FONTI:
        if fonti[fonte]:
            logger.info("    %-32s %d", fonte, fonti[fonte])
    if persi:
        logger.info("")
        logger.info(
            "Senza alcun appiglio (lasciate come sono): %d  →  id %s",
            len(persi),
            ", ".join(str(m.id) for m in persi[:20]),
        )

    if riparabili:
        logger.info("")
        logger.info("Esempi (id, data ricostruita, fonte):")
        for match, quando, fonte in riparabili[:5]:
            logger.info("    #%-6d %s   %s", match.id, quando, fonte)

    logger.info("")
    if applied:
        logger.info("Scritte %d righe.", len(riparabili))
        logger.info("")
        logger.info(
            "⚠ Ora l'ordine cronologico del replay è cambiato: rilancia il "
            "ricalcolo dell'Elo (scripts/recalc_elo.py), altrimenti i rating "
            "restano quelli calcolati sull'ordine sbagliato."
        )
    else:
        logger.info("Analisi (dry-run): nulla è stato scritto.")
        logger.info("Rilancia con --apply per scrivere le %d date.", len(riparabili))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="scrive le date ricostruite (senza, si limita ad analizzare)",
    )
    args = parser.parse_args()

    app = bootstrap_and_create_app()
    with app.app_context():
        matches = _da_riparare()
        riparabili, persi = _analizza(matches)
        if args.apply and riparabili:
            _applica(riparabili)
        _report(matches, riparabili, persi, applied=args.apply)

    return 0


if __name__ == "__main__":
    sys.exit(main())
