"""Il TPA di carriera di un giocatore, ricavato dai suoi referti.

Non c'e' nessun totale salvato: si rileggono i referti e si sommano. E' la
stessa scelta del resto del dominio (ADR-044) — un totale su colonna diverge
al primo annulla — e a questa scala non costa niente: qualche decina di
referti, qualche centinaio di comandi ciascuno.

**Il TPA di carriera non e' la media dei TPA delle partite.** Si sommano bilie
ed errori di tutti i referti e si divide una volta sola: una partita da
quaranta bilie deve pesare piu' di una da quattro, altrimenti un rack fortunato
in una partita corta vale quanto un'ora di gioco pulito.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from models.base import db
from models.individual_match.match_models import IndividualMatch
from models.tpa.engine import PlayerTally, total_errors, tpa_score
from models.user.models import User
from models.tpa.models import TpaReferto
from models.tpa.services import FEATURE_CODE, TpaRefertoService


class TpaStatsService:
    """Aggregati TPA per il profilo e per le statistiche personali."""

    @staticmethod
    def referti_for_user(user_id: int) -> List[TpaReferto]:
        """I referti delle partite giocate da un utente, dal piu' recente."""
        return (
            TpaReferto.query.join(
                IndividualMatch, TpaReferto.individual_match_id == IndividualMatch.id
            )
            .filter(
                or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                )
            )
            .order_by(TpaReferto.created_at.desc())
            .all()
        )

    @staticmethod
    def is_visible_for(user_id: int, user=None) -> bool:
        """Se il TPA va mostrato nel profilo di questo utente.

        Due strade, e la seconda e' quella che conta davvero: si vede il TPA se
        si e' sbloccata la funzione, **oppure** se qualcuno ha gia' tenuto il
        referto di una tua partita. Nel secondo caso il dato esiste e ti
        riguarda: nasconderlo perche' non hai ancora sbloccato il pulsante per
        compilarlo sarebbe assurdo.
        """
        if user is None:
            user = db.session.get(User, user_id)
        if user is not None and user.can_access(FEATURE_CODE):
            return True
        return db.session.query(
            TpaReferto.query.join(
                IndividualMatch, TpaReferto.individual_match_id == IndividualMatch.id
            )
            .filter(
                or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                )
            )
            .exists()
        ).scalar()

    @staticmethod
    def _numbers(tally: PlayerTally) -> Dict[str, Any]:
        """I numeri di un conto, nella forma che le pagine mostrano.

        Non conta niente di nuovo: legge i contatori del motore. L'unica
        somma e' ``closed_in_one_turn``: nel motore ``run_outs`` e
        ``break_and_runs`` sono **disgiunti**, ma per chi gioca lo «spacca e
        chiude» e' un triangolo chiuso in un turno come gli altri. Stampare il
        solo ``run_outs`` sotto quell'etichetta ne perde uno per ogni spaccata
        vincente.
        """
        return {
            "tpa": tpa_score(tally),
            "balls_potted": tally.balls_potted,
            "errors": total_errors(tally),
            "errors_by_kind": {
                "miss": tally.miss_errors,
                "break": tally.break_errors,
                "kick": tally.kick_errors,
                "safety": tally.safety_errors,
                "position": tally.position_errors,
            },
            "racks_won": tally.racks_won,
            "break_and_runs": tally.break_and_runs,
            "run_outs": tally.run_outs,
            "closed_in_one_turn": tally.run_outs + tally.break_and_runs,
            "perfect_racks": tally.perfect_racks,
        }

    @staticmethod
    def referto_summary(referto: TpaReferto) -> Dict[str, Any]:
        """Il racconto di un referto: i due conti, chi ha vinto, quanti triangoli.

        E' cio' che mostra la pagina del referto chiuso. I turni uno per uno
        restano nello stato del referto; qui ci sono solo i totali.
        """
        state = TpaRefertoService.build_state(referto)
        match = referto.match
        names = {
            1: match.player1.username if match and match.player1 else "",
            2: match.player2.username if match and match.player2 else "",
        }
        players = {}
        for seat in (1, 2):
            players[seat] = TpaStatsService._numbers(state.tally(seat))
            players[seat]["name"] = names[seat]

        one, two = players[1]["racks_won"], players[2]["racks_won"]
        return {
            "players": players,
            "racks_played": one + two,
            "winner": 1 if one > two else 2 if two > one else None,
        }

    @staticmethod
    def career_stats(user_id: int) -> Optional[Dict[str, Any]]:
        """I numeri TPA di un giocatore, o ``None`` se non ha nessun referto.

        Il TPA vale ``None`` finche' non c'e' nulla da dividere: «zero su zero»
        non e' zero, e un giocatore appena sbloccato non merita un `.000`.
        """
        referti = TpaStatsService.referti_for_user(user_id)
        if not referti:
            return None

        career = PlayerTally()
        per_match: List[Dict[str, Any]] = []

        for referto in referti:
            seat = referto.player_number(user_id)
            if seat is None:
                continue
            tally = TpaRefertoService.build_state(referto).tally(seat)

            career.balls_potted += tally.balls_potted
            career.miss_errors += tally.miss_errors
            career.break_errors += tally.break_errors
            career.kick_errors += tally.kick_errors
            career.safety_errors += tally.safety_errors
            career.position_errors += tally.position_errors
            career.racks_won += tally.racks_won
            career.break_and_runs += tally.break_and_runs
            career.run_outs += tally.run_outs
            career.perfect_racks += tally.perfect_racks

            match = referto.match
            opponent_id = referto.user_id_for(2 if seat == 1 else 1)
            opponent = db.session.get(User, opponent_id) if opponent_id else None
            per_match.append(
                {
                    "match_id": referto.individual_match_id,
                    "date": match.scheduled_at if match else None,
                    "discipline": match.discipline if match else None,
                    "opponent": opponent.username if opponent else None,
                    "tpa": tpa_score(tally),
                    "balls_potted": tally.balls_potted,
                    "errors": total_errors(tally),
                    "racks_won": tally.racks_won,
                    "closed": referto.is_closed,
                }
            )

        scored = [entry for entry in per_match if entry["tpa"] is not None]
        numbers = TpaStatsService._numbers(career)
        return {
            **numbers,
            "referti": len(per_match),
            "best_tpa": max((entry["tpa"] for entry in scored), default=None),
            "matches": per_match,
        }

    @staticmethod
    def profile_summary(user_id: int, user=None) -> Optional[Dict[str, Any]]:
        """Cosa mostrare nel profilo, o ``None`` se il TPA li' non ci va.

        Restituisce un riassunto anche quando i referti non ci sono ancora, ma
        solo a chi ha sbloccato la funzione: e' il modo di dire «c'e', usala»
        senza inventarsi un numero.
        """
        if not TpaStatsService.is_visible_for(user_id, user=user):
            return None
        stats = TpaStatsService.career_stats(user_id)
        if stats is None:
            return {"tpa": None, "referti": 0, "balls_potted": 0, "errors": 0}
        return stats


__all__ = ["TpaStatsService"]
