# models/campionato/statistics_service.py
"""Statistics and classification logic for Campionato.

Extracted from services.py for maintainability (Round 4 P4).
Contains: TournamentStatisticsService, compute_campionato_status.
"""

from __future__ import annotations

from typing import List, Dict, Any

from models.base import db
from models.match.models import Match
from models.status_enum import TournamentStatus, GaraStatus
from models.matchmaking.configuration import MatchmakingStrategy
from .models import Campionato
from ..transaction.manager import (
    DomainService,
    read_only,
)


class TournamentStatisticsService(DomainService):
    """Statistics and classification operations for Campionati."""

    def __init__(self):
        super().__init__("campionato")

    @read_only(domain="campionato")
    def get_campionato_statistics(self, campionato_id: int) -> Dict[str, Any]:
        """
        Get campionato-level statistics.

        Args:
            campionato_id: ID of the campionato

        Returns:
            Dictionary containing campionato statistics
        """
        from models.competition.models import Gara, Inscription

        # Track domain access
        self._track_domain_access()

        campionato = self._execute_with_tracking(
            lambda: db.session.get(Campionato, campionato_id)
        )
        if not campionato:
            raise ValueError("Campionato not found")

        # Get all provas for this campionato
        gare = self._execute_with_tracking(
            lambda: Gara.query.filter_by(campionato_id=campionato_id).all()
        )
        gara_ids = [p.id for p in gare]

        # Calculate statistics
        total_garas = len(gare)
        total_inscriptions = self._execute_with_tracking(
            lambda: (
                Inscription.query.filter(Inscription.gara_id.in_(gara_ids)).count()
                if gara_ids
                else 0
            )
        )
        total_matches = self._execute_with_tracking(
            lambda: (
                Match.query.filter(Match.gara_id.in_(gara_ids)).count()
                if gara_ids
                else 0
            )
        )

        # Status distribution
        status_counts: Dict[str, int] = {}
        for gara in gare:
            status = getattr(gara, "status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_garas": total_garas,
            "total_inscriptions": total_inscriptions,
            "total_matches": total_matches,
            "status_distribution": status_counts,
        }

    @read_only(domain="campionato")
    def calculate_campionato_statistics(self, campionato_id: int) -> Dict[str, Any]:
        """Calcola statistiche avanzate del campionato."""
        from models.competition.models import Gara, Inscription
        from sqlalchemy import func, distinct

        # Trova tutte le gare del campionato
        gare = db.session.query(Gara).filter_by(campionato_id=campionato_id).all()

        # Giocatori unici che hanno mai partecipato al campionato
        unique_players_query = (
            db.session.query(distinct(Inscription.user_id))
            .join(Gara, Inscription.gara_id == Gara.id)
            .filter(Gara.campionato_id == campionato_id)
        )
        total_unique_players = unique_players_query.count()

        # Giocatori attualmente iscritti a gare con iscrizioni aperte
        active_inscriptions_query = (
            db.session.query(distinct(Inscription.user_id))
            .join(Gara, Inscription.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Gara.status == "inscription",  # Solo gare con iscrizioni aperte
            )
        )
        currently_inscribed_players = active_inscriptions_query.count()

        # Match totali completati in tutte le gare
        completed_matches_query = (
            db.session.query(func.count(Match.id))
            .join(Gara, Match.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Match.status == "completed",  # type: ignore[attr-defined]
            )
        )
        total_completed_matches = completed_matches_query.scalar() or 0

        # Rack totali giocati (somma dei punteggi di tutti i match completati)
        rack_sum_query = (
            db.session.query(func.sum(Match.player1_score + Match.player2_score))
            .join(Gara, Match.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Match.status == "completed",  # type: ignore[attr-defined]
            )
        )
        total_racks_played = rack_sum_query.scalar() or 0

        return {
            "total_unique_players": total_unique_players,
            "currently_inscribed_players": currently_inscribed_players,
            "total_completed_matches": total_completed_matches,
            "total_racks_played": total_racks_played,
        }

    def _aggregate_player_totals(
        self,
        garas: List,
        campionato_type: str,
    ) -> Dict[int, Dict[str, Any]]:
        """Aggrega i totali dei giocatori per un insieme di gare.

        Args:
            garas: Lista di gare da aggregare
            campionato_type: Tipo di campionato (amalfi, random, etc.)

        Returns:
            Dizionario user_id -> dati aggregati del giocatore
        """
        from models.classification.models import RoundClassification, GaraClassification

        player_totals: Dict[int, Dict[str, Any]] = {}

        for gara in garas:
            # Ottieni la classifica finale di questa gara (ultimo turno)
            final_round = gara.rounds_count
            classifications = (
                db.session.query(RoundClassification)
                .filter_by(gara_id=gara.id, round_number=final_round)
                .order_by(RoundClassification.position)
                .all()
            )

            # Per Random campionati, ottieni anche i punteggi SSR da GaraClassification
            gara_ssr_scores: Dict[int, int] = {}
            if campionato_type == MatchmakingStrategy.RANDOM.value:
                gara_classifications = (
                    db.session.query(GaraClassification)
                    .filter_by(gara_id=gara.id)
                    .all()
                )
                gara_ssr_scores = {
                    gc.user_id: gc.spot_shot_wins or 0
                    for gc in gara_classifications
                }

            for classification in classifications:
                user_id = classification.user_id
                if user_id not in player_totals:
                    player_totals[user_id] = {
                        "username": classification.user.username,
                        "total_matches_won": 0,
                        "total_rack_difference": 0,
                        "total_spot_shot_wins": 0,
                        "participations": 0,
                        "total_points": 0,
                    }

                # Per campionati Amalfi: somma match vinti e differenza rack
                player_totals[user_id]["total_matches_won"] += (
                    classification.matches_won or 0
                )
                player_totals[user_id]["total_rack_difference"] += (
                    classification.rack_difference or 0
                )
                # Aggiungi punteggio SSR per campionati Random
                player_totals[user_id]["total_spot_shot_wins"] += (
                    gara_ssr_scores.get(user_id, 0)
                )
                player_totals[user_id]["participations"] += 1

        # Per sistemi a punti, calcola i punti
        if campionato_type not in [
            MatchmakingStrategy.AMALFI.value,
            MatchmakingStrategy.RANDOM.value,
        ]:
            position_points = {
                1: 10, 2: 7, 3: 5, 4: 4, 5: 3, 6: 2, 7: 2, 8: 1, 9: 1, 10: 1
            }
            for gara in garas:
                final_round = gara.rounds_count
                classifications = (
                    db.session.query(RoundClassification)
                    .filter_by(gara_id=gara.id, round_number=final_round)
                    .order_by(RoundClassification.position)
                    .all()
                )
                for classification in classifications:
                    user_id = classification.user_id
                    if user_id in player_totals:
                        points = position_points.get(classification.position, 0)
                        player_totals[user_id]["total_points"] += points

        return player_totals

    def _sort_and_rank_players(
        self,
        player_totals: Dict[int, Dict[str, Any]],
        campionato_type: str,
    ) -> List[tuple]:
        """Ordina i giocatori e assegna le posizioni.

        Args:
            player_totals: Dizionario user_id -> dati aggregati
            campionato_type: Tipo di campionato

        Returns:
            Lista di tuple (posizione, user_id) ordinate
        """
        if campionato_type == MatchmakingStrategy.AMALFI.value:
            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1]["total_matches_won"],
                    -x[1]["total_rack_difference"],
                ),
            )
        elif campionato_type == MatchmakingStrategy.RANDOM.value:
            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1]["total_rack_difference"],
                    -x[1]["total_spot_shot_wins"],
                ),
            )
        else:
            sorted_players = sorted(
                player_totals.items(),
                key=lambda x: (
                    -x[1].get("total_points", 0),
                    -x[1]["total_rack_difference"],
                    -x[1]["total_matches_won"],
                ),
            )

        # Restituisce lista di (posizione, user_id)
        return [(pos, user_id) for pos, (user_id, _) in enumerate(sorted_players, 1)]

    @read_only(domain="campionato")
    def calculate_general_classification(self, campionato_id: int) -> List[tuple]:
        """Calcola la classifica generale del campionato basata su tutte le gare completate.

        Include il calcolo del trend (previous_position) confrontando la classifica
        attuale con quella calcolata escludendo l'ultima gara completata.
        """
        from models.competition.models import Gara
        from models.campionato.models import Campionato

        # Trova il campionato per verificare il tipo
        campionato = db.session.query(Campionato).filter_by(id=campionato_id).first()
        if not campionato:
            return []

        # Trova tutte le gare completate del campionato (incluse quelle "playing" ma finite)
        all_garas = (
            db.session.query(Gara)
            .filter_by(campionato_id=campionato_id)
            .filter(Gara.status.in_(["completed", "playing"]))
            .order_by(Gara.number)
            .all()
        )

        # Filtra le gare che sono realmente completate
        completed_garas = []
        for gara in all_garas:
            if gara.status == "completed":
                completed_garas.append(gara)
            elif gara.status == "playing" and gara.current_round > gara.rounds_count:
                # Gara con tutti i round completati
                completed_garas.append(gara)

        if not completed_garas:
            return []

        # Calcola posizioni precedenti (tutte le gare tranne l'ultima)
        previous_positions: Dict[int, int] = {}
        if len(completed_garas) > 1:
            previous_garas = completed_garas[:-1]
            previous_totals = self._aggregate_player_totals(
                previous_garas, campionato.campionato_type
            )
            previous_ranking = self._sort_and_rank_players(
                previous_totals, campionato.campionato_type
            )
            previous_positions = {user_id: pos for pos, user_id in previous_ranking}

        # Calcola classifica attuale (tutte le gare)
        player_totals = self._aggregate_player_totals(
            completed_garas, campionato.campionato_type
        )
        current_ranking = self._sort_and_rank_players(
            player_totals, campionato.campionato_type
        )

        # Costruisci risultato con posizione precedente
        result = []
        for position, user_id in current_ranking:
            data = player_totals[user_id]
            # Aggiungi previous_position solo se il giocatore era nella classifica precedente
            data["previous_position"] = previous_positions.get(user_id)
            result.append((position, data))

        return result


# -----------------------------
# Funzione *pura* per lo stato derivato del Campionato
# -----------------------------


def compute_campionato_status(campionato: Campionato) -> str:
    """Calcola lo stato derivato del campionato in base agli stati delle Gare.

    Regole:
    - Se terminated_at → TERMINATED (se playoff config) o COMPLETED (altrimenti)
    - Se non ci sono Gare → SETUP
    - Se almeno una Gara è in PLAYING → IN_PROGRESS
    - Altrimenti, se almeno una Gara è in INSCRIPTION → REGISTRATION_OPEN
    - Altrimenti, se tutte le Gare esistono e sono COMPLETED → COMPLETED
    - In tutti gli altri casi → SETUP

    Ritorna la stringa dello stato (compat con UI/template esistenti).
    """
    if getattr(campionato, "terminated_at", None):
        if hasattr(campionato, "has_playoff_configurations") and campionato.has_playoff_configurations():
            return TournamentStatus.TERMINATED.value
        return TournamentStatus.COMPLETED.value

    gare = getattr(campionato, "gare", []) or []
    if not gare:
        return TournamentStatus.SETUP.value

    # Normalizza valori (stringhe) e valuta
    values = [getattr(p, "status", GaraStatus.SETUP.value) for p in gare]

    if any(v == GaraStatus.PLAYING.value for v in values):
        return TournamentStatus.IN_PROGRESS.value
    if any(v == GaraStatus.INSCRIPTION.value for v in values):
        return TournamentStatus.REGISTRATION_OPEN.value
    if all(v == GaraStatus.COMPLETED.value for v in values):
        return TournamentStatus.COMPLETED.value

    return TournamentStatus.SETUP.value
