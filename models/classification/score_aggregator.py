"""
Module: models/classification/score_aggregator.py
Purpose: Aggregates match/set/rack data into PlayerScore objects
Data Structures: ScoreAggregator
Dependencies: typing, .strategies.base, models.base
"""

from dataclasses import replace
from typing import List, Dict, Any, Optional
from .punti import Punti
from .strategies.base import PlayerScore
from models.status_enum import ClassificationSystem, MatchStatus

#: Gli esiti di una partita per la classifica a punti (`punti.py`).
VITTORIA, PAREGGIO, SCONFITTA = "vittoria", "pareggio", "sconfitta"


def _nuove_statistiche() -> Dict[str, int]:
    return {
        "matches_won": 0,
        "matches_lost": 0,
        "matches_drawn": 0,
        "racks_won": 0,
        "racks_lost": 0,
        "sets_won": 0,
        "sets_lost": 0,
        "points": 0,
    }


class ScoreAggregator:
    """Aggregates match data into PlayerScore objects for classification.

    Separates data collection from ranking logic - the aggregator produces
    the raw stats, strategies decide how to rank them.

    Handles:
    - Regular matches (single and multi-set)
    - Bye matches (player1 gets automatic win)
    - Cumulative stats across multiple rounds

    Nella classifica a punti (POINTS) ogni partita dà anche i **punti** del
    suo esito (`punti.py`): vittoria, pareggio o sconfitta. Gli esiti si
    contano sempre, i punti solo in quel sistema: altrove restano zero.
    """

    #: I punti della gara che si sta aggregando, None se non è a punti. Lo
    #: imposta `aggregate_round_scores`; chi processa una partita da sola
    #: (`_process_*`) conta gli esiti senza punti.
    _punti: Optional[Punti] = None

    def _esito(
        self, player_stats: Dict[int, Dict[str, int]], pid: int, esito: str
    ) -> None:
        """Registra l'esito di una partita per la classifica a punti.

        Le vittorie e le sconfitte le conta già chi chiama (`matches_won`,
        `matches_lost`, con le regole di sempre); qui si contano i pareggi e
        si sommano i punti.
        """
        if esito == PAREGGIO:
            player_stats[pid]["matches_drawn"] += 1
        if self._punti is None:
            return
        player_stats[pid]["points"] += {
            VITTORIA: self._punti.vittoria,
            PAREGGIO: self._punti.pareggio,
            SCONFITTA: self._punti.sconfitta,
        }[esito]

    def aggregate_round_scores(
        self,
        gara_id: int,
        up_to_round: int,
        *,
        escludi_x: bool = False,
    ) -> List[PlayerScore]:
        """Aggregate scores from matches up to specified round.

        Args:
            gara_id: ID of the gara
            up_to_round: Include matches up to and including this round
            escludi_x: lascia fuori la X: sono le **partite giocate**, con cui
                si confrontano giocatori di gironi diversi (ADR-076)

        Returns:
            List of PlayerScore objects for all players with matches
        """
        from models.competition.models import Gara
        from models.match.models import Match
        from models.base import db

        gara = db.session.get(Gara, gara_id)
        self._punti = None
        if gara is not None and (
            ClassificationSystem.resolve(gara.classification_system)
            is ClassificationSystem.POINTS
        ):
            from .punti import punti_della_gara

            self._punti = punti_della_gara(gara)

        # Include both 'completed' (admin) and 'validated' (player confirmation)
        matches = (
            db.session.query(Match)
            .filter(
                Match.gara_id == gara_id,
                Match.round_number <= up_to_round,
                Match.status.in_(MatchStatus.finished_values()),
            )
            .all()
        )

        player_stats: Dict[int, Dict[str, int]] = {}

        for match in matches:
            if match.is_bye:
                if not escludi_x:
                    self._process_bye_match(match, player_stats)
            elif match.is_trio and match.trio_match:
                self._process_trio_match(match, player_stats)
            else:
                self._process_regular_match(match, player_stats)

        # Convert to PlayerScore objects
        return [
            PlayerScore(
                player_id=pid,
                matches_won=stats.get("matches_won", 0),
                matches_lost=stats.get("matches_lost", 0),
                matches_drawn=stats.get("matches_drawn", 0),
                points=stats.get("points", 0),
                racks_won=stats.get("racks_won", 0),
                racks_lost=stats.get("racks_lost", 0),
                rack_difference=stats.get("racks_won", 0) - stats.get("racks_lost", 0),
                sets_won=stats.get("sets_won", 0),
                sets_lost=stats.get("sets_lost", 0),
            )
            for pid, stats in player_stats.items()
        ]

    def aggregate_gara_final_scores(
        self,
        gara_id: int,
        spot_shot_results: Optional[Dict[int, int]] = None,
    ) -> List[PlayerScore]:
        """Aggregate final gara scores including tiebreaker data.

        Args:
            gara_id: ID of the gara
            spot_shot_results: Optional spot shot rally results (player_id -> wins)

        Returns:
            List of PlayerScore objects with spot_shot_wins populated
        """
        from models.competition.models import Gara
        from models.base import db

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        # Get all rounds stats
        scores = self.aggregate_round_scores(gara_id, gara.current_round or 1)

        # Enrich with spot shot results if provided
        if spot_shot_results:
            enriched = []
            for score in scores:
                spot_wins = spot_shot_results.get(score.player_id, 0)
                if spot_wins > 0:
                    enriched.append(replace(score, spot_shot_wins=spot_wins))
                else:
                    enriched.append(score)
            return enriched

        return scores

    def get_gara_position_results(
        self,
        campionato_id: int,
    ) -> Dict[int, List[int]]:
        """Get final positions for each player across all gare.

        Used for point-based campionato classification.

        Args:
            campionato_id: ID of the campionato

        Returns:
            Dict mapping player_id -> list of positions in each gara
        """
        from models.competition.models import Gara
        from .models import RoundClassification
        from models.base import db

        gare = db.session.query(Gara).filter_by(campionato_id=campionato_id).all()

        player_positions: Dict[int, List[int]] = {}

        for gara in gare:
            if not gara.current_round:
                continue

            # Get final round classification for this gara
            classifications = (
                db.session.query(RoundClassification)
                .filter_by(gara_id=gara.id, round_number=gara.current_round)
                .all()
            )

            for classification in classifications:
                if classification.user_id not in player_positions:
                    player_positions[classification.user_id] = []
                player_positions[classification.user_id].append(classification.position)

        return player_positions

    def _process_regular_match(
        self,
        match: Any,
        player_stats: Dict[int, Dict[str, int]],
    ) -> None:
        """Process a regular (non-bye) match.

        Args:
            match: Match model instance
            player_stats: Dict to accumulate stats into
        """
        # Initialize players if not seen
        for pid in [match.player1_id, match.player2_id]:
            if pid and pid not in player_stats:
                player_stats[pid] = _nuove_statistiche()

        if not match.player1_id or not match.player2_id:
            return

        # Determine winner (handle ties - neither gets a win)
        vincitore = perdente = None
        if match.player1_score > match.player2_score:
            vincitore, perdente = match.player1_id, match.player2_id
        elif match.player2_score > match.player1_score:
            vincitore, perdente = match.player2_id, match.player1_id
        elif getattr(match, "winner_id", None) in (match.player1_id, match.player2_id):
            # Pari con chi passa indicato dal direttore: una partita del
            # tabellone interrotta a tempo (ADR-077). Fuori dal tabellone il
            # pari non ha vincitore, e qui non arriva.
            vincitore = match.winner_id
            perdente = (
                match.player2_id if vincitore == match.player1_id else match.player1_id
            )
        if vincitore is not None and perdente is not None:
            player_stats[vincitore]["matches_won"] += 1
            player_stats[perdente]["matches_lost"] += 1
            self._esito(player_stats, vincitore, VITTORIA)
            self._esito(player_stats, perdente, SCONFITTA)
        else:
            # Pareggio: esattamente N pari, o interrotta a tempo a parità
            # fuori dal tabellone (ADR-077). Nessuna vittoria, i punti del
            # pareggio a entrambi.
            self._esito(player_stats, match.player1_id, PAREGGIO)
            self._esito(player_stats, match.player2_id, PAREGGIO)

        # Process racks (handle multi-set)
        if match.is_multi_set:
            # Multi-set: player1_score/player2_score are SETS won, not racks
            # Sum racks from all sets
            for set_obj in match.sets:
                player_stats[match.player1_id]["racks_won"] += set_obj.player1_racks
                player_stats[match.player1_id]["racks_lost"] += set_obj.player2_racks
                player_stats[match.player2_id]["racks_won"] += set_obj.player2_racks
                player_stats[match.player2_id]["racks_lost"] += set_obj.player1_racks

            # Track sets won/lost
            player_stats[match.player1_id]["sets_won"] += match.player1_score
            player_stats[match.player1_id]["sets_lost"] += match.player2_score
            player_stats[match.player2_id]["sets_won"] += match.player2_score
            player_stats[match.player2_id]["sets_lost"] += match.player1_score
        else:
            # Single-set: player1_score/player2_score are racks won
            player_stats[match.player1_id]["racks_won"] += match.player1_score
            player_stats[match.player1_id]["racks_lost"] += match.player2_score
            player_stats[match.player2_id]["racks_won"] += match.player2_score
            player_stats[match.player2_id]["racks_lost"] += match.player1_score

    def _process_bye_match(
        self,
        match: Any,
        player_stats: Dict[int, Dict[str, int]],
    ) -> None:
        """Process a bye match (player gets automatic win).

        Args:
            match: Match model instance (with is_bye=True)
            player_stats: Dict to accumulate stats into
        """
        pid = match.player1_id
        if not pid:
            return

        if pid not in player_stats:
            player_stats[pid] = _nuove_statistiche()

        # Bye player gets automatic win. La X vale una vittoria anche a punti
        # (SPECIFICHE.md, «Strategia di abbinamento»).
        player_stats[pid]["matches_won"] += 1
        self._esito(player_stats, pid, VITTORIA)
        player_stats[pid]["racks_won"] += match.player1_score or 0
        # No rack_lost for bye matches

    def _process_trio_match(
        self,
        match: Any,
        player_stats: Dict[int, Dict[str, int]],
    ) -> None:
        """Process a trio match using round-robin format (ADR-005).

        In trio, 3 players play round-robin matches within "gironi" (rounds).
        Classification is based on total racks won, with bonus racks added
        to equalize with normal matches (bonus = 1 if distance is odd).

        Winner is optional - ties are allowed for rack-based classification.

        Args:
            match: Match model instance (with is_trio=True and trio_match)
            player_stats: Dict to accumulate stats into
        """
        trio = match.trio_match
        if not trio:
            return

        player_ids = [trio.player1_id, trio.player2_id, trio.player3_id]
        # ADR-027: usa la distanza effettiva del match (rispetta override per
        # turno). Il trio_config dentro trio_match risale alla gara originale,
        # ma per l'aggregazione qui ci basta il numero di rack-per-girone.
        distance = match.effective_distance

        # Initialize all three players if not seen
        for pid in player_ids:
            if pid and pid not in player_stats:
                player_stats[pid] = _nuove_statistiche()

        winner_id = match.winner_id

        # Walkover branch: completed trio with no racks played.
        # Credit the nominal winner with `distance` racks (parallel to 2-player
        # walkover where `Match.player1_score = round_distance`). Others get
        # matches_lost but no rack movement — they didn't play.
        if trio.is_completed and trio.total_racks_played == 0 and winner_id:
            for pid in player_ids:
                if not pid:
                    continue
                if pid == winner_id:
                    player_stats[pid]["matches_won"] += 1
                    player_stats[pid]["racks_won"] += distance
                    self._esito(player_stats, pid, VITTORIA)
                else:
                    player_stats[pid]["matches_lost"] += 1
                    self._esito(player_stats, pid, SCONFITTA)
            return

        racks = [trio.player1_racks, trio.player2_racks, trio.player3_racks]
        # Senza vincitore, chi è a pari merito in testa prende i punti del
        # pareggio e il terzo, se staccato, quelli della sconfitta
        # (SPECIFICHE.md, «Classifica»). Nessuna vittoria, come a WINS. Chi si
        # è ritirato non è mai in testa: il pari si guarda fra gli altri due,
        # come per il vincitore (`trio_punteggio.vincitore_del_trio`).
        ritirato = getattr(trio, "forfeit_player_id", None)
        in_gara = [
            r or 0 for pid, r in zip(player_ids, racks) if pid and pid != ritirato
        ]
        massimo = max(in_gara) if in_gara else 0
        bonus_racks = distance % 2  # 1 for distance 3,5; 0 for distance 2,4

        # Process each player
        for i, pid in enumerate(player_ids):
            if not pid:
                continue

            player_racks = racks[i]
            from models.match.trio_config import trio_racks_lost

            opponent_racks = trio_racks_lost(player_racks, distance)

            # Add bonus racks to each player (equalization with normal matches)
            player_stats[pid]["racks_won"] += player_racks + bonus_racks
            player_stats[pid]["racks_lost"] += opponent_racks

            # Winner exists: winner gets match_won, others get match_lost
            # No winner (tie): no one gets match_won or match_lost
            if winner_id:
                if pid == winner_id:
                    player_stats[pid]["matches_won"] += 1
                    self._esito(player_stats, pid, VITTORIA)
                else:
                    player_stats[pid]["matches_lost"] += 1
                    self._esito(player_stats, pid, SCONFITTA)
            else:
                in_testa = pid != ritirato and (player_racks or 0) == massimo
                self._esito(player_stats, pid, PAREGGIO if in_testa else SCONFITTA)


__all__ = ["ScoreAggregator"]
