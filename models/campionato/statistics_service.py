# models/campionato/statistics_service.py
"""Statistics and classification logic for Campionato.

Extracted from services.py for maintainability (Round 4 P4).
Contains: TournamentStatisticsService, compute_campionato_status.
"""

from __future__ import annotations

from typing import List, Dict, Any

from models.base import db
from models.match.models import Match
from models.status_enum import TournamentStatus, GaraStatus, MatchStatus
from models.matchmaking.configuration import MatchmakingStrategy
from .models import Campionato
from ..transaction.manager import read_only


class TournamentStatisticsService:
    """Statistics and classification operations for Campionati."""

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

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise ValueError("Campionato not found")

        # Get all provas for this campionato
        gare = Gara.query.filter_by(campionato_id=campionato_id).all()
        gara_ids = [p.id for p in gare]

        # Calculate statistics
        total_garas = len(gare)
        total_inscriptions = (
            Inscription.query.filter(Inscription.gara_id.in_(gara_ids)).count()
            if gara_ids
            else 0
        )
        total_matches = (
            Match.query.filter(Match.gara_id.in_(gara_ids)).count() if gara_ids else 0
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
                # Solo gare con iscrizioni aperte
                Gara.status == GaraStatus.INSCRIPTION.value,
            )
        )
        currently_inscribed_players = active_inscriptions_query.count()

        # Match totali completati in tutte le gare
        completed_matches_query = (
            db.session.query(func.count(Match.id))
            .join(Gara, Match.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Match.status == MatchStatus.COMPLETED.value,
            )
        )
        total_completed_matches = completed_matches_query.scalar() or 0

        # Rack totali giocati (somma dei punteggi di tutti i match completati)
        rack_sum_query = (
            db.session.query(func.sum(Match.player1_score + Match.player2_score))
            .join(Gara, Match.gara_id == Gara.id)
            .filter(
                Gara.campionato_id == campionato_id,
                Match.status == MatchStatus.COMPLETED.value,
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
        from sqlalchemy import tuple_
        from sqlalchemy.orm import joinedload

        player_totals: Dict[int, Dict[str, Any]] = {}
        if not garas:
            return player_totals

        # N+1 fix (hot path homepage anonima): invece di una query
        # RoundClassification + un lazy-load user PER OGNI gara, batcha tutto in
        # un'unica query sulle coppie (gara_id, round-finale) con user eager.
        final_round_by_gara = {g.id: g.rounds_count for g in garas}
        rc_rows = (
            db.session.query(RoundClassification)
            .filter(
                tuple_(
                    RoundClassification.gara_id, RoundClassification.round_number
                ).in_(list(final_round_by_gara.items()))
            )
            .options(joinedload(RoundClassification.user))
            .order_by(RoundClassification.position)
            .all()
        )
        rc_by_gara: Dict[int, List[Any]] = {}
        for rc in rc_rows:
            rc_by_gara.setdefault(rc.gara_id, []).append(rc)

        # SSR (Random): un'unica query GaraClassification per tutte le gare.
        ssr_by_gara: Dict[int, Dict[int, int]] = {}
        if campionato_type == MatchmakingStrategy.RANDOM.value:
            gc_rows = (
                db.session.query(GaraClassification)
                .filter(GaraClassification.gara_id.in_(final_round_by_gara.keys()))
                .all()
            )
            for gc in gc_rows:
                ssr_by_gara.setdefault(gc.gara_id, {})[gc.user_id] = (
                    gc.spot_shot_wins or 0
                )

        for gara in garas:
            classifications = rc_by_gara.get(gara.id, [])
            gara_ssr_scores = ssr_by_gara.get(gara.id, {})

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
                player_totals[user_id]["total_spot_shot_wins"] += gara_ssr_scores.get(
                    user_id, 0
                )
                player_totals[user_id]["participations"] += 1

        # Per sistemi a punti, calcola i punti
        if campionato_type not in [
            MatchmakingStrategy.AMALFI.value,
            MatchmakingStrategy.RANDOM.value,
        ]:
            position_points = {
                1: 10,
                2: 7,
                3: 5,
                4: 4,
                5: 3,
                6: 2,
                7: 2,
                8: 1,
                9: 1,
                10: 1,
            }
            for gara in garas:
                # Riusa i dati già batch-caricati sopra (niente nuove query).
                for classification in rc_by_gara.get(gara.id, []):
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
        """Classifica generale del campionato su tutte le gare completate.

        Include il calcolo del trend (previous_position) confrontando la classifica
        attuale con quella calcolata escludendo l'ultima gara completata.
        """
        from models.competition.models import Gara
        from models.campionato.models import Campionato

        # Trova il campionato per verificare il tipo
        campionato = db.session.query(Campionato).filter_by(id=campionato_id).first()
        if not campionato:
            return []

        # Tutte le gare completate del campionato (incl. "playing" ma finite)
        all_garas = (
            db.session.query(Gara)
            .filter_by(campionato_id=campionato_id)
            .filter(
                Gara.status.in_([GaraStatus.COMPLETED.value, GaraStatus.PLAYING.value])
            )
            .order_by(Gara.number)
            .all()
        )

        # Filtra le gare che sono realmente completate
        completed_garas = []
        for gara in all_garas:
            if gara.status == GaraStatus.COMPLETED.value:
                completed_garas.append(gara)
            elif (
                gara.status == GaraStatus.PLAYING.value
                and gara.current_round > gara.rounds_count
            ):
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
            # previous_position solo se il giocatore era in classifica prima
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
        if (
            hasattr(campionato, "has_playoff_configurations")
            and campionato.has_playoff_configurations()
        ):
            # TERMINATED until all playoffs completed, then COMPLETED
            from models.playoff.models import PlayoffTournament, PlayoffConfiguration

            active_configs = PlayoffConfiguration.query.filter_by(
                campionato_id=campionato.id, is_active=True
            ).all()
            if active_configs:
                all_completed = all(
                    (
                        t := PlayoffTournament.query.filter_by(
                            configuration_id=cfg.id
                        ).first()
                    )
                    is not None
                    and t.status == "completed"
                    for cfg in active_configs
                )
                if all_completed:
                    return TournamentStatus.COMPLETED.value
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


# -----------------------------
# Partizione per presentazione: attivi vs completati/terminati
# -----------------------------


_TERMINAL_TOURNAMENT_STATUSES = frozenset(
    {
        TournamentStatus.COMPLETED.value,
        TournamentStatus.TERMINATED.value,
    }
)


def partition_campionati_by_status(
    campionati: list[Campionato],
    completed_limit: int,
) -> dict:
    """Partiziona campionati in attivi vs completati/terminati per la UI.

    Le viste pubbliche (homepage guest, dashboard player/director) mostrano
    tutti gli attivi e una "coda recente" di completati limitata a
    `completed_limit`. Il resto resta accessibile via pagina archivio
    (`/campionati` con filtri).

    Args:
        campionati: lista pre-filtrata (es. is_active=True, oppure scopata
            al singolo utente). L'ordinamento viene preservato.
        completed_limit: numero massimo di completati da includere in `to_show`.

    Returns:
        Dict con:
        - `active`: lista di campionati con status non-terminale
        - `completed`: lista completa dei campionati COMPLETED/TERMINATED
        - `completed_shown`: prefisso di `completed` con al più
          `completed_limit` elementi (preserva l'ordine in input)
        - `to_show`: `active + completed_shown` (lista renderizzabile)
        - `completed_total`: `len(completed)`, utile al template per
          decidere se mostrare "Vedi tutti".
    """
    active: list[Campionato] = []
    completed: list[Campionato] = []
    for c in campionati:
        if c.get_status() in _TERMINAL_TOURNAMENT_STATUSES:
            completed.append(c)
        else:
            active.append(c)

    completed_shown = completed[:completed_limit]
    return {
        "active": active,
        "completed": completed,
        "completed_shown": completed_shown,
        "to_show": active + completed_shown,
        "completed_total": len(completed),
    }
