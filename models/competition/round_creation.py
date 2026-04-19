"""
Module: models/competition/round_creation.py
Purpose: Round creation logic (create_round_with_strategy, start_next_round, _create_round_impl)
"""

from __future__ import annotations

from typing import Optional, Set

from models.base import db, transactional
from models.status_enum import GaraStatus
from .models import Gara


def create_matches_from_pairings(
    gara: Gara,
    pairings: list,
    round_number: int,
    round_distance: int,
    round_discipline: Optional[str] = None,
    forfeit_user_ids: Optional[Set[int]] = None,
) -> None:
    """Create Match (and TrioMatch) objects from strategy pairings.

    Centralizes match creation logic to avoid duplication across
    round_service.py and round_creation.py.
    """
    from models.match.models import Match, TrioMatch

    if forfeit_user_ids is None:
        forfeit_user_ids = set()

    for pairing in pairings:
        if len(pairing.players) == 1 and pairing.is_bye:
            bye_score = round_distance
            match = Match(
                gara_id=gara.id,
                round_number=round_number,
                player1_id=pairing.players[0],
                player2_id=None,
                is_bye=True,
                player1_score=bye_score,
                winner_id=pairing.players[0],
                status="completed",
                discipline=round_discipline,
                match_distance=round_distance,
            )
            db.session.add(match)
        elif len(pairing.players) == 2 and not pairing.is_bye:
            player1_forfeit = pairing.players[0] in forfeit_user_ids
            player2_forfeit = pairing.players[1] in forfeit_user_ids

            if player1_forfeit or player2_forfeit:
                winning_score = round_distance
                if player1_forfeit and player2_forfeit:
                    winner_id = pairing.players[0]
                    player1_score = winning_score
                    player2_score = 0
                elif player1_forfeit:
                    winner_id = pairing.players[1]
                    player1_score = 0
                    player2_score = winning_score
                else:
                    winner_id = pairing.players[0]
                    player1_score = winning_score
                    player2_score = 0

                match = Match(
                    gara_id=gara.id,
                    round_number=round_number,
                    player1_id=pairing.players[0],
                    player2_id=pairing.players[1],
                    is_bye=False,
                    player1_score=player1_score,
                    player2_score=player2_score,
                    winner_id=winner_id,
                    status="completed",
                    discipline=round_discipline,
                    match_distance=round_distance,
                    is_multi_set=gara.is_multi_set,
                )
                db.session.add(match)
            else:
                match = Match(
                    gara_id=gara.id,
                    round_number=round_number,
                    player1_id=pairing.players[0],
                    player2_id=pairing.players[1],
                    is_bye=False,
                    discipline=round_discipline,
                    match_distance=round_distance,
                    is_multi_set=gara.is_multi_set,
                )
                db.session.add(match)
        elif len(pairing.players) == 3:
            p0, p1, p2 = pairing.players
            n_forfeit = sum(1 for p in pairing.players if p in forfeit_user_ids)

            if n_forfeit == 0:
                match = Match(
                    gara_id=gara.id,
                    round_number=round_number,
                    player1_id=p0,
                    player2_id=p1,
                    is_bye=False,
                    is_trio=True,
                    discipline=round_discipline,
                    match_distance=round_distance,
                )
                db.session.add(match)
                db.session.flush()

                trio_match = TrioMatch(
                    match_id=match.id,
                    player1_id=p0,
                    player2_id=p1,
                    player3_id=p2,
                )
                db.session.add(trio_match)
                db.session.flush()
                trio_match.initialize_matchup()
            elif n_forfeit == 1:
                survivors = [p for p in pairing.players if p not in forfeit_user_ids]
                match = Match(
                    gara_id=gara.id,
                    round_number=round_number,
                    player1_id=survivors[0],
                    player2_id=survivors[1],
                    is_bye=False,
                    is_trio=False,
                    discipline=round_discipline,
                    match_distance=round_distance,
                    is_multi_set=gara.is_multi_set,
                )
                db.session.add(match)
            else:
                if n_forfeit == 2:
                    winner_id = next(
                        p for p in pairing.players if p not in forfeit_user_ids
                    )
                else:
                    winner_id = p0

                match = Match(
                    gara_id=gara.id,
                    round_number=round_number,
                    player1_id=p0,
                    player2_id=p1,
                    is_bye=False,
                    is_trio=True,
                    player1_score=round_distance,
                    player2_score=0,
                    winner_id=winner_id,
                    status="completed",
                    discipline=round_discipline,
                    match_distance=round_distance,
                )
                db.session.add(match)
                db.session.flush()

                trio_match = TrioMatch(
                    match_id=match.id,
                    player1_id=p0,
                    player2_id=p1,
                    player3_id=p2,
                    winner_id=winner_id,
                    is_completed=True,
                )
                db.session.add(trio_match)


class RoundCreationService:
    """Round creation and match generation logic."""

    @staticmethod
    @transactional(domain="competition")
    def create_round_with_strategy(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int]:
        """Crea un turno usando la strategia configurata nella gara.

        Returns:
            Tuple con (total_matches, normal_matches, bye_matches, trio_matches)
        """
        return RoundCreationService._create_round_impl(
            gara_id, round_number, discipline_override
        )

    @staticmethod
    @transactional(domain="competition")
    def start_next_round(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int, int]:
        """Create a round and advance the gara state.

        Combines round creation, state transition to PLAYING,
        current_round update, and table assignment in one transaction.

        Returns:
            Tuple: (total, normal, bye, trio, tables_assigned)
        """
        from models.competition.state_service import StateService
        from models.match.table_assignment_service import TableAssignmentService

        total, n_normal, n_bye, n_trio = RoundCreationService._create_round_impl(
            gara_id, round_number, discipline_override
        )

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if gara.status != GaraStatus.PLAYING.value:
            StateService.start_playing(gara)
            db.session.refresh(gara)

        gara.current_round = round_number

        tables_assigned = TableAssignmentService.assign_tables_to_round(
            gara_id, round_number
        )

        return total, n_normal, n_bye, n_trio, tables_assigned

    @staticmethod
    def _create_round_impl(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int]:
        """Core round creation logic (no @transactional — called within a transaction)."""
        from models.match.models import Match, TrioMatch

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Verifica precondizioni
        if round_number < 1 or round_number > gara.rounds_count:
            raise ValueError(f"Turno {round_number} non valido")

        # Verifica se esistono già match per questo turno
        existing_matches = (
            db.session.query(Match)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .count()
        )
        if existing_matches > 0:
            # I match esistono già, ritorna i conteggi attuali
            matches = (
                db.session.query(Match)
                .filter_by(gara_id=gara_id, round_number=round_number)
                .all()
            )
            normal_matches = sum(
                1 for m in matches if not m.is_bye and not getattr(m, "is_trio", False)
            )
            bye_matches = sum(1 for m in matches if m.is_bye)
            trio_matches = sum(1 for m in matches if getattr(m, "is_trio", False))
            return (len(matches), normal_matches, bye_matches, trio_matches)

        # Ottieni la strategia configurata
        strategy_name = gara.matchmaking_strategy or "amalfi"

        # Usa il registry per tutte le strategie
        from models.matchmaking.bootstrap import get_registry

        registry = get_registry()

        # Mappatura nome strategia: enum -> registry
        strategy_mapping = {
            "random": "random_anti_rematch",
            "amalfi": "amalfi",
            "advanced_amalfi": "amalfi",  # Alias per compatibilità
            "round_robin": "round_robin",
            "direct_elimination": "direct_elimination",
            "double_knockout": "double_knockout",
        }

        registry_name = strategy_mapping.get(strategy_name, strategy_name)
        strategy = registry.get(registry_name)
        if not strategy:
            raise ValueError(f"Strategia '{strategy_name}' non trovata")

        # Genera gli abbinamenti usando l'interfaccia della strategia
        pairings = strategy.create_round(gara, round_number)

        # Get forfeit players for this gara to handle completed matches
        from models.competition.withdraw_policy_service import WithdrawPolicyService

        forfeit_user_ids = set(
            inscription.user_id
            for inscription in WithdrawPolicyService.get_forfeit_inscriptions(gara_id)
        )

        # Get round configuration for distance override
        from models.competition.round_configuration import RoundConfiguration

        round_config = RoundConfiguration.get_for_gara_round(gara_id, round_number)
        round_distance = (
            round_config.get_effective_distance(gara.distance)
            if round_config
            else gara.distance
        )
        # Use discipline_override if provided, otherwise check round_config
        effective_discipline = discipline_override or (
            round_config.discipline if round_config else None
        )

        # Crea i match nel database
        create_matches_from_pairings(
            gara=gara,
            pairings=pairings,
            round_number=round_number,
            round_distance=round_distance,
            round_discipline=effective_discipline,
            forfeit_user_ids=forfeit_user_ids,
        )

        # Conta i risultati
        matches = (
            db.session.query(Match)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .all()
        )
        normal_matches = sum(1 for m in matches if not m.is_bye and not m.is_trio)
        bye_matches = sum(1 for m in matches if m.is_bye)
        trio_matches = (
            db.session.query(TrioMatch)
            .join(Match)
            .filter(Match.gara_id == gara_id, Match.round_number == round_number)
            .count()
        )
        total_matches = len(matches)

        # Lock previous round matches when creating a new round
        if round_number > 1:
            previous_round_matches = (
                db.session.query(Match)
                .filter_by(gara_id=gara_id, round_number=round_number - 1)
                .all()
            )
            for match in previous_round_matches:
                match.round_locked = True
                db.session.add(match)

        return (total_matches, normal_matches, bye_matches, trio_matches)
