# amalfi/engine.py - Core algoritmi Sistema Amalfi
from __future__ import annotations

import random
from typing import List, Optional, Dict, TypedDict

from models import (
    db,
    Match,
    Gara,
    Inscription,
    PlayerEncounter,
    RoundClassification,
    TrioMatch,
)
from models.user.models import User
from models.matchmaking.policies import (
    anti_rematch_allowed,
    decide_trio_or_bye,
    OddResolution,
)
from models.competition.models import WithdrawPolicy
from models.status_enum import MatchStatus


class ValidationResult(TypedDict):
    is_valid: bool
    warnings: List[str]
    errors: List[str]


class AmalfiEngine:
    """Engine principale per gestione abbinamenti Sistema Amalfi"""

    def __init__(self, gara: Gara):
        self.gara = gara
        self.campionato = gara.campionato

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

        # Applica regole dominio aggiornate
        self._cleanup_cancelled_matches(matches)
        self._finalize_forfeit_matches(matches)

        # Persistenza atomica dei match creati (l'engine storico già aggiungeva i match)
        db.session.commit()
        return matches

    def preview_round_pairings(self, round_number: int) -> Dict:
        """
        Calcola gli abbinamenti per un turno senza persistere nel database.
        Ritorna un dictionary con matches, stats e informazioni per l'anteprima.
        """
        if round_number == 1:
            matches = self._preview_first_round()
        else:
            matches = self._preview_amalfi_round(round_number)
        
        # Calcola statistiche
        stats = {
            "total_matches": len(matches),
            "normal_matches": sum(1 for m in matches if m.get("type") == "normal"),
            "bye_matches": sum(1 for m in matches if m.get("type") == "bye"),
            "trio_matches": sum(1 for m in matches if m.get("type") == "trio"),
        }
        
        return {
            "matches": matches,
            "stats": stats,
            "salto": getattr(self, "_current_salto", 0)
        }

    def _preview_first_round(self) -> List[Dict]:
        """Genera l'anteprima del primo turno senza persistere"""
        inscriptions = self._inscriptions_for_pairing()
        if len(inscriptions) < self.gara.min_participants:
            raise ValueError(f"Servono almeno {self.gara.min_participants} iscritti")
        
        # Usa lo stesso seed del _create_first_round per avere gli stessi accoppiamenti
        rng = random.Random(self.gara.id)
        rng.shuffle(inscriptions)
        
        matches_data = []
        players = inscriptions
        
        # Usa la stessa logica del _create_first_round
        i = 0
        while i < len(players):
            if i + 1 < len(players):
                # Match normale
                matches_data.append({
                    "type": "normal",
                    "player1": {"id": players[i].user_id, "username": players[i].user.username},
                    "player2": {"id": players[i+1].user_id, "username": players[i+1].user.username}
                })
                i += 2
            else:
                # Player con bye
                matches_data.append({
                    "type": "bye",
                    "player1": {"id": players[i].user_id, "username": players[i].user.username},
                    "player2": None
                })
                i += 1
        
        return matches_data

    def _preview_amalfi_round(self, round_number: int) -> List[Dict]:
        """Genera l'anteprima di un turno Amalfi senza persistere"""
        # Per ora ritorniamo un'anteprima semplificata
        inscriptions = self._inscriptions_for_pairing()
        if len(inscriptions) < self.gara.min_participants:
            raise ValueError(f"Servono almeno {self.gara.min_participants} iscritti")
        
        matches_data = []
        players = [ins for ins in inscriptions]
        
        # Implementazione semplificata - in realtà dovrebbe usare l'algoritmo Amalfi completo
        i = 0
        while i < len(players):
            if i + 1 < len(players):
                matches_data.append({
                    "type": "normal",
                    "player1": {"id": players[i].user_id, "username": players[i].user.username},
                    "player2": {"id": players[i+1].user_id, "username": players[i+1].user.username}
                })
                i += 2
            else:
                matches_data.append({
                    "type": "bye",
                    "player1": {"id": players[i].user_id, "username": players[i].user.username},
                    "player2": None
                })
                i += 1
        
        # Salto fittizio per ora
        self._current_salto = round_number
        
        return matches_data

    # ────────────────────────────────────────────────────────────────────────────
    # Primo turno
    # ────────────────────────────────────────────────────────────────────────────
    def _create_first_round(self) -> List[Match]:
        inscriptions = self._inscriptions_for_pairing()
        if len(inscriptions) < self.gara.min_participants:
            raise ValueError(f"Servono almeno {self.gara.min_participants} iscritti")

        # Usa un seed basato sul gara_id per avere risultati deterministici
        # ma diversi per ogni gara
        rng = random.Random(self.gara.id)
        rng.shuffle(inscriptions)
        for i, inscription in enumerate(inscriptions, 1):
            inscription.initial_order = i

        matches = self._create_first_round_matches(inscriptions)

        # 🔧 FIX contratto: registra incontri con ordine corretto
        # (gara_id, p1, p2, round)
        for match in matches:
            if not getattr(match, "is_bye", False):
                PlayerEncounter.record_encounter(
                    self.gara.id, match.player1_id, match.player2_id, 1
                )

        return matches

    def _create_first_round_matches(
        self, inscriptions: List[Inscription]
    ) -> List[Match]:
        players = [insc.user for insc in inscriptions]
        matches: List[Match] = []

        # Aggiorna o crea nuove classifiche
        for position, ins in enumerate(inscriptions, 1):
            # Cerca classifica esistente
            existing = (
                db.session.query(RoundClassification)
                .filter_by(gara_id=self.gara.id, round_number=1, user_id=ins.user_id)
                .first()
            )

            if existing:
                # Aggiorna posizione
                existing.position = position
            else:
                # Crea nuova classifica
                classification = RoundClassification(
                    gara_id=self.gara.id,
                    round_number=1,
                    user_id=ins.user_id,
                    position=position,
                )
                db.session.add(classification)

        # Dispari → bye oppure trasformazione in trio a seconda della modalità
        if len(players) % 2 == 1:
            bye_player = players[-1]
            bye_score = (
                self.gara.get_winning_score()
                if self.gara.best_of
                else self.gara.distance
            )
            match = Match(
                gara_id=self.gara.id,
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
                gara_id=self.gara.id,
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
            self.gara.id, round_number - 1
        )
        classification = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=self.gara.id, round_number=round_number - 1)
            .order_by(RoundClassification.position)
            .all()
        )

        # escludi i ritirati se EXCLUDE
        if self.gara.withdraw_policy == WithdrawPolicy.EXCLUDE.value:
            excluded_ids = {
                ins.user_id
                for ins in db.session.query(Inscription)
                .filter_by(gara_id=self.gara.id, is_withdrawn=True)
                .all()
            }
            classification = [
                c for c in classification if c.user_id not in excluded_ids
            ]

        salto = self.gara.rounds_count - round_number
        matches = self._apply_amalfi_algorithm(classification, round_number, salto)

        # 🔧 FIX contratto: registra incontri con ordine corretto + copri i trii
        for match in matches:
            if getattr(match, "is_bye", False):
                continue
            if getattr(match, "is_trio", False):
                trio = match.trio_match
                PlayerEncounter.record_encounter(
                    self.gara.id, trio.player1_id, trio.player2_id, round_number
                )
                PlayerEncounter.record_encounter(
                    self.gara.id, trio.player1_id, trio.player3_id, round_number
                )
                PlayerEncounter.record_encounter(
                    self.gara.id, trio.player2_id, trio.player3_id, round_number
                )
            else:
                PlayerEncounter.record_encounter(
                    self.gara.id, match.player1_id, match.player2_id, round_number
                )

        self._finalize_forfeit_matches(matches)
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
                    gara_id=self.gara.id,
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

            # gara posizione successiva
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
        # anti‑reincontro via policy
        if not anti_rematch_allowed(self.gara.id, p1_id, p2_id):
            return False
        return True

    def _handle_unmatched_player(
        self,
        unmatched_class: RoundClassification,
        matches: List[Match],
        round_number: int,
    ) -> None:
        """Gestisce l'ultimo giocatore rimasto (bye oppure trasformazione in trio)."""
        decision = decide_trio_or_bye(
            campionato_without_x=bool(self.campionato.without_x),
            can_trio=bool(matches),
        )
        if decision is OddResolution.TRIO and matches:
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
            target_score=self.gara.get_winning_score()
            if self.gara.best_of
            else self.gara.distance,
        )
        db.session.add(trio)

    def _create_bye_match(self, player_id: int, round_number: int) -> None:
        score = (
            self.gara.get_winning_score()
            if self.gara.best_of
            else self.gara.distance
        )
        bye = Match(
            gara_id=self.gara.id,
            round_number=round_number,
            player1_id=player_id,
            is_bye=True,
            player1_score=score,
            winner_id=player_id,
            status="completed",
            amalfi_round=round_number,
        )
        db.session.add(bye)

    def _inscriptions_for_pairing(self) -> list[Inscription]:
        q = db.session.query(Inscription).filter_by(gara_id=self.gara.id)
        if self.gara.withdraw_policy == WithdrawPolicy.EXCLUDE.value:
            q = q.filter_by(is_withdrawn=False)
        return q.all()

    def _finalize_forfeit_matches(self, matches: list["Match"]) -> None:
        """Chiude a tavolino i match con esattamente un
        cancellato/ritirato, SOLO se policy FORFEIT."""
        if self.gara.withdraw_policy != WithdrawPolicy.FORFEIT.value:
            return

        withdrawn_ids = {
            ins.user_id
            for ins in Inscription.query.filter_by(
                gara_id=self.gara.id, is_withdrawn=True
            ).all()
        }
        deleted_ids = {
            u.id
            for u in db.session.query(User).filter(User.deleted_at.isnot(None)).all()
        }
        cancelled_ids = withdrawn_ids | deleted_ids
        if not cancelled_ids:
            return

        to_win = self.gara.get_winning_score()

        for m in matches:
            # Salta match già completati e BYE (il cleanup li ha già gestiti)
            if m.status == MatchStatus.COMPLETED.value:
                continue
            if m.player1_id is None or m.player2_id is None:
                continue

            p1_cancel = m.player1_id in cancelled_ids
            p2_cancel = m.player2_id in cancelled_ids

            # Esattamente uno cancellato/ritirato → vittoria massima all'altro
            if p1_cancel ^ p2_cancel:
                if p1_cancel:
                    m.player2_score = to_win
                else:
                    m.player1_score = to_win
                m.status = MatchStatus.COMPLETED.value

    def _cleanup_cancelled_matches(self, matches: list["Match"]) -> None:
        """Elimina:
        - match contro X (uno dei due player è None) se l'altro è cancellato/ritirato
            (sempre, anche se 'completed')
        - match tra due cancellati/ritirati se NON completati
        """
        withdrawn_ids = {
            ins.user_id
            for ins in db.session.query(Inscription)
            .filter_by(gara_id=self.gara.id, is_withdrawn=True)
            .all()
        }
        deleted_ids = {
            u.id for u in User.query.filter(User.deleted_at.isnot(None)).all()
        }
        cancelled_ids = withdrawn_ids | deleted_ids

        to_delete = []
        for m in matches:
            p1, p2 = m.player1_id, m.player2_id

            # BYE/X: uno dei due è None → se l'altro è cancellato, elimina SEMPRE
            if p1 is None or p2 is None:
                other = p2 if p1 is None else p1
                if other in cancelled_ids:
                    to_delete.append(m)
                continue

            # Entrambi cancellati/ritirati → elimina se non completato
            if (
                (p1 in cancelled_ids)
                and (p2 in cancelled_ids)
                and m.status != MatchStatus.COMPLETED.value
            ):
                to_delete.append(m)

        for m in to_delete:
            db.session.delete(m)

    # ────────────────────────────────────────────────────────────────────────────
    # Preview (solo helper legacy; migra in Strategy allo Sprint 2)
    # ────────────────────────────────────────────────────────────────────────────
    def preview_next_round_matches(self, next_round: int) -> List[Dict]:
        import warnings

        warnings.warn(
            "AmalfiEngine.preview_next_round_matches è deprecato: "
            "usare AmalfiStrategy.preview",
            DeprecationWarning,
        )
        if next_round == 1:
            return self._preview_first_round()

        # aggiorna classifica round precedente e poi carica le righe
        RoundClassification.calculate_classification_after_round(
            self.gara.id, next_round - 1
        )
        classification = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=self.gara.id, round_number=next_round - 1)
            .order_by(RoundClassification.position)
            .all()
        )

        # escludi i ritirati se EXCLUDE
        if self.gara.withdraw_policy == WithdrawPolicy.EXCLUDE.value:
            excluded_ids = {
                ins.user_id
                for ins in Inscription.query.filter_by(
                    gara_id=self.gara.id, is_withdrawn=True
                ).all()
            }
            classification = [
                c for c in classification if c.user_id not in excluded_ids
            ]

        salto = self.gara.rounds_count - next_round
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
            if self.campionato.without_x and preview_matches:
                last = preview_matches[-1]
                last["type"] = "trio"
                last["player3"] = rest[0].user
            else:
                preview_matches.append(
                    {"player1": rest[0].user, "player2": None, "type": "bye"}
                )

        return preview_matches

    def _preview_first_round(self) -> List[Dict]:
        inscriptions = self._inscriptions_for_pairing()
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
                if self.campionato.without_x and preview_matches:
                    preview_matches[-1]["type"] = "trio"
                    preview_matches[-1]["player3"] = users_copy[i]
                else:
                    preview_matches.append(
                        {"player1": users_copy[i], "player2": None, "type": "bye"}
                    )
        return preview_matches


# Utility functions per compat con codice esistente


def create_amalfi_round_matches(gara: Gara, round_number: int) -> List[Match]:
    engine = AmalfiEngine(gara)
    return engine.create_round_matches(round_number)


def get_amalfi_classification(
    gara_id: int, round_number: int
) -> List[RoundClassification]:
    return (
        db.session.query(RoundClassification)
        .filter_by(gara_id=gara_id, round_number=round_number)
        .order_by(RoundClassification.position)
        .all()
    )


def validate_amalfi_configuration(gara: Gara) -> ValidationResult:
    from models import Inscription  # late import per evitare cicli

    inscriptions = db.session.query(Inscription).filter_by(gara_id=gara.id).count()
    validation: ValidationResult = {"is_valid": True, "warnings": [], "errors": []}

    if inscriptions < gara.min_participants:
        validation["errors"].append(
            f"Servono almeno {gara.min_participants} "
            f"iscritti (attuali: {inscriptions})"
        )
        validation["is_valid"] = False

    if gara.rounds_count < 2:
        validation["warnings"].append(
            "Con meno di 2 turni l'algoritmo Amalfi ha efficacia limitata"
        )

    max_encounters = (inscriptions * (inscriptions - 1)) // 2
    required_encounters = inscriptions * (gara.rounds_count - 1)
    if required_encounters > max_encounters:
        validation["errors"].append(
            f"Troppi turni per {inscriptions} giocatori. Massimo "
            f"consigliato: {max_encounters // inscriptions + 1}"
        )
        validation["is_valid"] = False

    return validation
