"""Quanti runout ha fatto un giocatore, e quanti di quelli erano break and run.

**Un numero, due fonti** (ADR-056):

* il flag sul triangolo, per le partite segnate col tabellone — tutte le gare,
  e le sfide senza referto TPA;
* il tally derivato dal referto, per le sfide col referto TPA.

Non serve una precedenza fra le due, e non è una svista: i due segnapunti **non
convivono mai** sulla stessa partita. `TpaReferto` ha solo
`individual_match_id`, e sulle sfide il tabellone sta già dietro
`{% if user_is_player and not tpa_live %}` (ADR-044); sui match di gara il
referto non esiste proprio. Quindi le due fonti non possono contare lo stesso
triangolo due volte, e si sommano.

TRAPPOLA — I DUE CONTATORI DEL TPA SONO DISGIUNTI
-------------------------------------------------
Qui «runout» è l'**insieme** e break and run un suo sottoinsieme, che è come
parlano i giocatori: «26, di cui 9 break and run». Nel motore TPA no:
`is_run_out = not is_break_and_run and …`, quindi `tally.run_outs` conta solo
quelli **senza** spaccata. Il totale è `run_outs + break_and_runs`: chi
leggesse `tally.run_outs` e lo stampasse come «runout totali» mostrerebbe 17
invece di 26.

I **triangoli perfetti** restano fuori di proposito: contarli vuol dire contare
gli errori, e il tabellone gli errori non li vede. Continuano a vivere nella
pagina del referto.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import case, func

from models.base import db

__all__ = ["runout_summary"]


def runout_summary(
    user_id: int, tpa_stats: Optional[Dict[str, Any]] = None
) -> Dict[str, int]:
    """``{"total": n, "break_and_runs": m}`` per questo giocatore.

    Args:
        user_id: il giocatore.
        tpa_stats: il riassunto TPA già calcolato dalla pagina, se c'è. Il
            profilo lo chiede comunque (`TpaStatsService.profile_summary`), e
            ricalcolarlo qui vorrebbe dire rigiocare ogni referto una seconda
            volta. Passandolo si paga una volta sola.
    """
    dal_tabellone = _dai_triangoli(user_id)
    dal_referto = _dal_referto(tpa_stats)

    return {
        "total": dal_tabellone["total"] + dal_referto["total"],
        "break_and_runs": (
            dal_tabellone["break_and_runs"] + dal_referto["break_and_runs"]
        ),
    }


def _dai_triangoli(user_id: int) -> Dict[str, int]:
    """I triangoli marcati col trattino, sulle due tabelle dei triangoli.

    Il break and run non è un secondo flag: è un runout che ha aperto chi l'ha
    vinto. Si deduce qui come si deduce ovunque — è la stessa condizione di
    `Rack.is_break_and_run` e di `check_break_and_run()` nel motore TPA.

    `break_player_id IS NULL` non conta come break and run, ed è la risposta
    onesta: sui triangoli scritti prima dell'ADR-056, e su quelli nati da un
    risultato inserito in blocco dal direttore, chi ha aperto non lo sa
    nessuno.
    """
    from models.individual_match.match_models import IndividualRack
    from models.match.models import Rack

    totale = 0
    con_spaccata = 0
    for modello in (Rack, IndividualRack):
        riga = (
            db.session.query(
                func.count(modello.id),
                func.coalesce(
                    func.sum(
                        case(
                            (modello.break_player_id == modello.winner_id, 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .filter(
                modello.winner_id == user_id,
                modello.is_run_out.is_(True),
                modello.is_deleted.is_(False),
            )
            .one()
        )
        totale += int(riga[0] or 0)
        con_spaccata += int(riga[1] or 0)

    return {"total": totale, "break_and_runs": con_spaccata}


def _dal_referto(tpa_stats: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """I runout riconosciuti dal motore TPA, rimessi insieme.

    `run_outs + break_and_runs` e non `run_outs`: vedi la trappola in cima al
    modulo.
    """
    if not tpa_stats:
        return {"total": 0, "break_and_runs": 0}

    senza_spaccata = int(tpa_stats.get("run_outs") or 0)
    con_spaccata = int(tpa_stats.get("break_and_runs") or 0)
    return {
        "total": senza_spaccata + con_spaccata,
        "break_and_runs": con_spaccata,
    }
