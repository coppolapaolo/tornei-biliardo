# amalfi/engine.py - Core algoritmi Sistema Amalfi
from __future__ import annotations

import random
from typing import List, Optional, Dict

from models import (
    db,
    Match,
    Prova,
    Inscription,
    PlayerEncounter,
    RoundClassification,
    TrioMatch,
)


class AmalfiEngine:
    """Engine principale per gestione abbinamenti Sistema Amalfi"""

    def __init__(self, prova: Prova):
        self.prova = prova
        self.tournament = prova.tournament

    # ────────────────────────────────────────────────────────────────────────────
    # Entry point
    # ────────────────────────────────────────────────────────────────────────────
    def create_round_matches(self, round_number: int) -> List[Match]:
        """
        Crea abbinamenti per un turno specifico secondo algoritmo Amalfi.
        Ritorna la lista di Match **persistiti**
        (alcuni potrebbero avere status "pending").
        """
        if round_number == 1:
            matches = self._create_first_round()
        else:
            matches = self._create_amalfi_round(round_number)

        # Persistenza atomica dei match creati (l'engine storico già aggiungeva i match)
        db.session.commit()
        return matches

    # ────────────────────────────────────────────────────────────────────────────
    # Primo turno
    # ────────────────────────────────────────────────────────────────────────────
    def _create_first_round(self) -> List[Match]:
        inscriptions = Inscription.query.filter_by(prova_id=self.prova.id).all()
        if len(inscriptions) < self.prova.min_participants:
            raise ValueError(f"Servono almeno {self.prova.min_participants} iscritti")

        # Sorteggio casuale e memorizzazione ordine
        random.shuffle(inscriptions)
        for i, inscription in enumerate(inscriptions, 1):
            inscription.initial_order = i

        matches = self._create_first_round_matches(inscriptions)

        # 🔧 FIX contratto: registra incontri con ordine corretto
        # (prova_id, p1, p2, round)
        for match in matches:
            if not getattr(match, "is_bye", False):
                PlayerEncounter.record_encounter(
                    self.prova.id, match.player1_id, match.player2_id, 1
                )

        return matches

    def _create_first_round_matches(
        self, inscriptions: List[Inscription]
    ) -> List[Match]:
        players = [insc.user for insc in inscriptions]
        matches: List[Match] = []

        # Dispari → bye oppure trasformazione in trio a seconda della modalità
        if len(players) % 2 == 1:
            bye_player = players[-1]
            bye_score = (
                self.prova.get_winning_score()
                if self.prova.best_of
                else self.prova.distance
            )
            match = Match(
                prova_id=self.prova.id,
                round_number=1,
                player1_id=bye_player.id,
                is_bye=True,
                player1_score=bye_score,
                winner_id=bye_player.id,
                status="completed",
                amalfi_round=1,
            )
            matches.append(match)
            players = players[:-1]

        # Coppie rimanenti
        for i in range(0, len(players), 2):
            match = Match(
                prova_id=self.prova.id,
                round_number=1,
                player1_id=players[i].id,
                player2_id=players[i + 1].id,
                amalfi_round=1,
            )
            matches.append(match)

        db.session.add_all(matches)
        return matches

    # ────────────────────────────────────────────────────────────────────────────
    # Turni successivi (salto Amalfi)
    # ────────────────────────────────────────────────────────────────────────────
    def _create_amalfi_round(self, round_number: int) -> List[Match]:
        # Calcola/aggiorna classifica del turno precedente e poi carica le righe
        RoundClassification.calculate_classification_after_round(
            self.prova.id, round_number - 1
        )
        classification = (
            RoundClassification.query.filter_by(
                prova_id=self.prova.id, round_number=round_number - 1
            )
            .order_by(RoundClassification.position)
            .all()
        )

        salto = self.prova.rounds_count - round_number
        matches = self._apply_amalfi_algorithm(classification, round_number, salto)

        # 🔧 FIX contratto: registra incontri con ordine corretto + copri i trii
        for match in matches:
            if getattr(match, "is_bye", False):
                continue
            if getattr(match, "is_trio", False):
                trio = match.trio_match
                PlayerEncounter.record_encounter(
                    self.prova.id, trio.player1_id, trio.player2_id, round_number
                )
                PlayerEncounter.record_encounter(
                    self.prova.id, trio.player1_id, trio.player3_id, round_number
                )
                PlayerEncounter.record_encounter(
                    self.prova.id, trio.player2_id, trio.player3_id, round_number
                )
            else:
                PlayerEncounter.record_encounter(
                    self.prova.id, match.player1_id, match.player2_id, round_number
                )

        return matches

    def _apply_amalfi_algorithm(
        self,
        classification: List[RoundClassification],
        round_number: int,
        salto: int,
    ) -> List[Match]:
        matched_players: set[int] = set()
        matches: List[Match] = []

        for current_class in classification:
            if current_class.user_id in matched_players:
                continue

            target_class = self._find_amalfi_target(
                current_class, classification, matched_players, salto
            )

            if target_class:
                match = Match(
                    prova_id=self.prova.id,
                    round_number=round_number,
                    player1_id=current_class.user_id,
                    player2_id=target_class.user_id,
                    amalfi_round=round_number,
                    salto_applied=salto,
                )
                db.session.add(match)
                matches.append(match)
                matched_players.update({current_class.user_id, target_class.user_id})

        # Gestisci disparità
        unmatched = [c for c in classification if c.user_id not in matched_players]
        if unmatched:
            self._handle_unmatched_player(unmatched[0], matches, round_number)

        return matches

    def _find_amalfi_target(
        self,
        current_class: RoundClassification,
        classification: List[RoundClassification],
        matched_players: set[int],
        salto: int,
    ) -> Optional[RoundClassification]:
        players_count = len(classification)
        current_position = current_class.position
        target_position = current_position + salto

        attempts = 0
        max_attempts = players_count * 2  # due giri completi max

        while attempts < max_attempts:
            if target_position > players_count:
                target_position -= players_count

            target_class = next(
                (c for c in classification if c.position == target_position), None
            )

            if target_class and self._is_valid_pairing(
                current_class.user_id, target_class.user_id, matched_players
            ):
                return target_class

            # prova posizione successiva
            target_position += 1
            attempts += 1

        return None

    def _is_valid_pairing(
        self, p1_id: int, p2_id: int, matched_players: set[int]
    ) -> bool:
        if p1_id == p2_id:
            return False
        if p1_id in matched_players or p2_id in matched_players:
            return False
        # 🔧 usa correttamente l’API anti‑reincontro
        if PlayerEncounter.have_played(self.prova.id, p1_id, p2_id):
            return False
        return True

    def _handle_unmatched_player(
        self,
        unmatched_class: RoundClassification,
        matches: List[Match],
        round_number: int,
    ) -> None:
        """Gestisce l'ultimo giocatore rimasto (bye oppure trasformazione in trio)."""
        if self.tournament.without_x and matches:
            # trasforma l'ultimo match in trio
            last_match = matches[-1]
            self._convert_to_trio(last_match, unmatched_class.user_id, round_number)
        else:
            # crea un bye (X)
            self._create_bye_match(unmatched_class.user_id, round_number)

    def _convert_to_trio(
        self, base_match: Match, third_player_id: int, round_number: int
    ) -> None:
        base_match.is_trio = True
        trio = TrioMatch(
            match_id=base_match.id,
            player1_id=base_match.player1_id,
            player2_id=base_match.player2_id,
            player3_id=third_player_id,
            target_score=self.prova.get_winning_score()
            if self.prova.best_of
            else self.prova.distance,
        )
        db.session.add(trio)

    def _create_bye_match(self, player_id: int, round_number: int) -> None:
        score = (
            self.prova.get_winning_score()
            if self.prova.best_of
            else self.prova.distance
        )
        bye = Match(
            prova_id=self.prova.id,
            round_number=round_number,
            player1_id=player_id,
            is_bye=True,
            player1_score=score,
            winner_id=player_id,
            status="completed",
            amalfi_round=round_number,
        )
        db.session.add(bye)

    # ────────────────────────────────────────────────────────────────────────────
    # Preview (solo helper legacy; migra in Strategy allo Sprint 2)
    # ────────────────────────────────────────────────────────────────────────────
    def preview_next_round_matches(self, next_round: int) -> List[Dict]:
        if next_round == 1:
            return self._preview_first_round()

        # aggiorna classifica round precedente e poi carica le righe
        RoundClassification.calculate_classification_after_round(
            self.prova.id, next_round - 1
        )
        classification = (
            RoundClassification.query.filter_by(
                prova_id=self.prova.id, round_number=next_round - 1
            )
            .order_by(RoundClassification.position)
            .all()
        )

        salto = self.prova.rounds_count - next_round
        matched: set[int] = set()
        preview_matches: List[Dict] = []

        for current in classification:
            if current.user_id in matched:
                continue
            target = self._find_amalfi_target(current, classification, matched, salto)
            if target:
                preview_matches.append(
                    {
                        "player1": current.user,
                        "player2": target.user,
                        "type": "normal",
                        "salto_applied": salto,
                    }
                )
                matched.update({current.user_id, target.user_id})

        # eventuale disparità
        rest = [c for c in classification if c.user_id not in matched]
        if rest:
            if self.tournament.without_x and preview_matches:
                last = preview_matches[-1]
                last["type"] = "trio"
                last["player3"] = rest[0].user
            else:
                preview_matches.append(
                    {"player1": rest[0].user, "player2": None, "type": "bye"}
                )

        return preview_matches

    def _preview_first_round(self) -> List[Dict]:
        inscriptions = Inscription.query.filter_by(prova_id=self.prova.id).all()
        users = [insc.user for insc in inscriptions]
        users_copy = users.copy()
        random.shuffle(users_copy)

        preview_matches: List[Dict] = []
        for i in range(0, len(users_copy), 2):
            if i + 1 < len(users_copy):
                preview_matches.append(
                    {
                        "player1": users_copy[i],
                        "player2": users_copy[i + 1],
                        "type": "normal",
                    }
                )
            else:
                if self.tournament.without_x and preview_matches:
                    preview_matches[-1]["type"] = "trio"
                    preview_matches[-1]["player3"] = users_copy[i]
                else:
                    preview_matches.append(
                        {"player1": users_copy[i], "player2": None, "type": "bye"}
                    )
        return preview_matches


# Utility functions per compat con codice esistente


def create_amalfi_round_matches(prova: Prova, round_number: int) -> List[Match]:
    engine = AmalfiEngine(prova)
    return engine.create_round_matches(round_number)


def get_amalfi_classification(
    prova_id: int, round_number: int
) -> List[RoundClassification]:
    return (
        RoundClassification.query.filter_by(
            prova_id=prova_id, round_number=round_number
        )
        .order_by(RoundClassification.position)
        .all()
    )


def validate_amalfi_configuration(prova: Prova) -> Dict[str, object]:
    from models import Inscription  # late import per evitare cicli

    inscriptions = Inscription.query.filter_by(prova_id=prova.id).count()
    validation: Dict[str, object] = {"is_valid": True, "warnings": [], "errors": []}

    if inscriptions < prova.min_participants:
        validation["errors"].append(
            f"Servono almeno {prova.min_participants} "
            f"iscritti (attuali: {inscriptions})"
        )
        validation["is_valid"] = False

    if prova.rounds_count < 2:
        validation["warnings"].append(
            "Con meno di 2 turni l'algoritmo Amalfi ha efficacia limitata"
        )

    max_encounters = (inscriptions * (inscriptions - 1)) // 2
    required_encounters = inscriptions * (prova.rounds_count - 1)
    if required_encounters > max_encounters:
        validation["errors"].append(
            f"Troppi turni per {inscriptions} giocatori. Massimo "
            f"consigliato: {max_encounters // inscriptions + 1}"
        )
        validation["is_valid"] = False

    return validation
