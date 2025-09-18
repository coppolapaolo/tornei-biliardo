"""
Module: models/match/services
Purpose: Service layer per il dominio Match (Match, Rack, MatchResult, TrioMatch)
         + state machine centralizzata per gli stati del Match.
Data Structures: MatchService, RackService, MatchResultService
Dependencies: models.base.db, models.match.models, models.status_enum

Nota sprint 4: aggiunte API di transizione di stato; preservati nomi/classi esistenti
per compatibilità con i test di separazione.
"""

from __future__ import annotations

from typing import List, Optional

from models.base import db
from models.status_enum import MatchStatus
from .models import Match, Rack, TrioMatch


from models.exceptions import InvalidTransitionError


class MatchService:
    """Operazioni di business sui Match + state machine facade."""

    # -----------------------------
    # CREAZIONE / QUERY DI SUPPORTO
    # -----------------------------
    @staticmethod
    def create_match(
        gara_id: int,
        round_number: int,
        player1_id: int,
        player2_id: Optional[int] = None,
        is_bye: bool = False,
    ) -> Match:
        """Crea un match. Imposta lo stato iniziale a 'pending'."""
        # Get gara to fetch the distance
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} not found")

        match = Match(
            gara_id=gara_id,
            round_number=round_number,
            player1_id=player1_id,
            player2_id=player2_id,
            is_bye=is_bye,
            status=MatchStatus.PENDING.value,
            match_distance=gara.distance,
        )
        db.session.add(match)
        db.session.commit()
        return match

    @staticmethod
    def get_matches_by_gara(gara_id: int) -> List[Match]:
        return Match.query.filter_by(gara_id=gara_id).all()

    @staticmethod
    def create_trio_match(match_id: int, player3_id: int) -> TrioMatch:
        """Crea l'entità TrioMatch e marca il match come trio (compat)."""
        trio = TrioMatch(match_id=match_id, waiting_player_id=player3_id)
        db.session.add(trio)
        match = db.session.get(Match, match_id)
        if match is not None:
            match.is_trio = True  # compat con modello esistente
            db.session.add(match)
        db.session.commit()
        return trio

    # -----------------------------
    # STATE MACHINE FACADE
    # -----------------------------
    @staticmethod
    def to_playing(match_id: int) -> Match:
        """pending/completed → playing
        (riapertura consentita in flussi admin o dopo rimozione rack)"""
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        if (match.status or MatchStatus.PENDING.value) not in (
            MatchStatus.PENDING.value,
            MatchStatus.COMPLETED.value,
        ):
            raise InvalidTransitionError(
                f"Transizione non ammessa: {match.status!r} → playing"
            )
        match.status = MatchStatus.PLAYING.value
        db.session.add(match)
        db.session.commit()
        return match

    @staticmethod
    def to_completed(match_id: int) -> Match:
        """playing → completed (consente anche pending →
        completed per amministratore)."""
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        if match.status not in (MatchStatus.PLAYING.value, MatchStatus.PENDING.value):
            raise InvalidTransitionError(
                f"Transizione non ammessa: {match.status!r} → completed"
            )
        match.status = MatchStatus.COMPLETED.value
        db.session.add(match)
        db.session.commit()
        return match

    @staticmethod
    def reset_to_pending(match_id: int, clear_validation: bool = True) -> Match:
        """Qualsiasi → pending. Opzione per azzerare flag di validazione admin.
        Non rimuove i rack (responsabilità di RackService).
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        match.status = MatchStatus.PENDING.value
        if clear_validation and hasattr(match, "validated_by_admin"):
            try:
                match.validated_by_admin = False
            except Exception:
                pass
        db.session.add(match)
        db.session.commit()
        return match


class RackService:
    """Service per gestione rack con business logic completa."""

    @staticmethod
    def add_rack_result(
        match_id: int,
        rack_number: int,
        winner_id: int,
        reported_by_id: int,
        *,
        confirmed_by_player: bool = False,
        validated_by_admin: bool = False,
    ) -> Rack:
        rack = Rack(
            match_id=match_id,
            rack_number=rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            confirmed_by_player=confirmed_by_player,
            validated_by_admin=validated_by_admin,
        )
        db.session.add(rack)
        db.session.commit()
        # Transizione soft: se il match è pending, portalo a playing
        match = db.session.get(Match, match_id)
        if (
            match
            and (match.status or MatchStatus.PENDING.value) == MatchStatus.PENDING.value
        ):
            match.status = MatchStatus.PLAYING.value
            db.session.add(match)
            db.session.commit()
        return rack

    @staticmethod
    def add_rack_with_score_update(
        match_id: int,
        winner_id: int,
        reported_by_id: int = 1,
        validated_by_admin: bool = True,
    ) -> dict:
        """Aggiunge rack e aggiorna automaticamente il punteggio del match.

        Returns:
            Dict con stato aggiornato del match
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # Verifica che il match non sia già finito
        if match.gara.is_match_finished(match.player1_score, match.player2_score):
            raise ValueError(
                "Il match è già finito, non è possibile aggiungere altri punti"
            )

        # Verifica che non si superi il limite anche con questo nuovo punto
        temp_p1_score = match.player1_score
        temp_p2_score = match.player2_score

        if winner_id == match.player1_id:
            temp_p1_score += 1
        else:
            temp_p2_score += 1

        # Valida in base al tipo di match
        if match.gara.best_of:  # "al meglio di N"
            # Per "al meglio di N", il limite per singolo giocatore è (N // 2) + 1
            winning_score = match.gara.get_winning_score()
            if temp_p1_score > winning_score or temp_p2_score > winning_score:
                raise ValueError(
                    f"Match già completato - limite raggiunto per 'al meglio di {match.gara.distance}'"
                )
        else:  # "esattamente N"
            # Per "esattamente N", il totale non può superare N
            total_racks = temp_p1_score + temp_p2_score
            if total_racks > match.gara.distance:
                raise ValueError(
                    f"Non è possibile superare il limite di {match.gara.distance} rack totali per questo match"
                )

        # Trova il prossimo numero rack
        last_rack = (
            Rack.query.filter_by(match_id=match_id)
            .order_by(Rack.rack_number.desc())
            .first()
        )
        next_rack_number = (last_rack.rack_number + 1) if last_rack else 1

        # Crea il rack
        RackService.add_rack_result(
            match_id=match.id,
            rack_number=next_rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            validated_by_admin=validated_by_admin,
        )

        # Aggiorna punteggio match
        if winner_id == match.player1_id:
            match.player1_score += 1
        else:
            match.player2_score += 1

        # Se il match è finito, imposta il vincitore
        if match.gara.is_match_finished(match.player1_score, match.player2_score):
            final_winner_id = (
                match.player1_id
                if match.player1_score > match.player2_score
                else match.player2_id
            )
            # Import locale per evitare cicli
            from models.match.services import MatchResultService

            MatchResultService.submit_result(match.id, final_winner_id)

        db.session.commit()

        return {
            "success": True,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }

    @staticmethod
    def set_match_result_direct(
        match_id: int, player1_score: int, player2_score: int
    ) -> None:
        """Imposta risultato completo di una partita sostituendo tutti i rack."""
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if match.is_bye:
            raise ValueError("Non puoi modificare una partita bye!")

        # Validazione punteggi
        if player1_score < 0 or player2_score < 0:
            raise ValueError("I punteggi non possono essere negativi!")

        # Verifica che il risultato sia valido secondo le regole della gara
        total_racks = player1_score + player2_score

        if match.gara.best_of:
            # Al meglio di: uno dei due deve aver raggiunto la soglia
            winning_score = match.gara.get_winning_score()
            if max(player1_score, player2_score) < winning_score:
                raise ValueError(
                    f'Nel "al meglio di {match.gara.distance}", uno dei '
                    f"giocatori deve raggiungere {winning_score} punti!"
                )
        else:
            # Esatto numero: la somma deve essere esattamente la distanza
            if total_racks != match.gara.distance:
                raise ValueError(
                    f'Nel "{match.gara.distance} rack esatti", '
                    f"la somma deve essere esattamente {match.gara.distance}!"
                )

        # Determina il vincitore
        if player1_score > player2_score:
            winner_id = match.player1_id
        elif player2_score > player1_score:
            winner_id = match.player2_id
        else:
            raise ValueError("Non può esserci un pareggio!")

        # Elimina tutti i rack esistenti per questa partita
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Crea i nuovi rack basati sul risultato
        rack_number = 1

        # Crea rack per player1
        for i in range(player1_score):
            RackService.add_rack_result(
                match_id, rack_number, match.player1_id, 1, validated_by_admin=True
            )
            rack_number += 1

        # Crea rack per player2
        for i in range(player2_score):
            RackService.add_rack_result(
                match_id, rack_number, match.player2_id, 1, validated_by_admin=True
            )
            rack_number += 1

        # Aggiorna il match
        match.player1_score = player1_score
        match.player2_score = player2_score
        match.winner_id = winner_id

        # Import locale per evitare cicli
        from models.match.services import MatchService

        MatchService.to_completed(match.id)

    @staticmethod
    def reset_match_complete(match_id: int) -> None:
        """Reset completo di una partita eliminando tutti i rack."""
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if match.is_bye:
            raise ValueError("Non puoi resettare una partita bye!")

        # Elimina tutti i rack
        existing_racks = Rack.query.filter_by(match_id=match_id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Reset match
        match.player1_score = 0
        match.player2_score = 0
        match.winner_id = None

        # Import locale per evitare cicli
        from models.match.services import MatchService

        MatchService.reset_to_pending(match.id, clear_validation=True)

        db.session.commit()

    @staticmethod
    def remove_rack_admin(rack_id: int) -> dict:
        """Rimuove un rack e aggiorna il punteggio del match (admin).

        Returns:
            Dict con stato aggiornato del match
        """
        rack = db.session.get(Rack, rack_id)
        if rack is None:
            from flask import abort

            abort(404)
        match = rack.match

        # Salva il vincitore per aggiornare il punteggio
        winner_id = rack.winner_id

        # Rimuovi il rack
        db.session.delete(rack)

        # Aggiorna il punteggio del match
        if winner_id == match.player1_id:
            match.player1_score = max(0, match.player1_score - 1)
        else:
            match.player2_score = max(0, match.player2_score - 1)

        # Se il match era completato e ora non ha più i punti per essere vinto,
        # rimettilo in playing
        if match.status == MatchStatus.COMPLETED.value:
            if match.gara.best_of:
                winning_score = match.gara.get_winning_score()
                if max(match.player1_score, match.player2_score) < winning_score:
                    # Import locale per evitare cicli
                    from models.match.services import MatchService

                    MatchService.to_playing(match.id)
                    match.winner_id = None
            else:  # esatto numero
                if (match.player1_score + match.player2_score) < match.gara.distance:
                    # Import locale per evitare cicli
                    from models.match.services import MatchService

                    MatchService.to_playing(match.id)
                    match.winner_id = None

        db.session.commit()

        return {
            "success": True,
            "message": "Rack rimosso (Admin)",
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }

    @staticmethod
    def validate_rack_admin(rack_id: int) -> None:
        """Valida un rack (admin)."""
        rack = db.session.get(Rack, rack_id)
        if rack is None:
            from flask import abort

            abort(404)

        # Valida il rack
        rack.validated_by_admin = True
        rack.confirmed_by_player = (
            True  # Automaticamente confermato se validato dall'admin
        )

        db.session.commit()

    @staticmethod
    def remove_last_rack(match_id: int) -> Optional[Rack]:
        last = (
            Rack.query.filter_by(match_id=match_id)
            .order_by(Rack.rack_number.desc())
            .first()
        )
        if last:
            db.session.delete(last)
            db.session.commit()
        return last


class MatchResultService:
    """Placeholder per gestione risultati/validazioni match."""

    @staticmethod
    def validate_by_admin(match_id: int) -> Match:
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")
        if hasattr(match, "validated_by_admin"):
            match.validated_by_admin = True
            db.session.add(match)
            db.session.commit()
        return match

    @staticmethod
    def submit_result(match_id: int, winner_id: int) -> Match:
        """
        Imposta il vincitore del match e porta lo stato a 'completed'
        tramite la state machine.
        Non tocca Trio né logiche rack: è il percorso 'set result' da form.
        """
        match: Optional[Match] = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # winner deve appartenere al match (2-players match)
        if winner_id not in (match.player1_id, match.player2_id):
            raise ValueError("winner_id non appartiene ai giocatori del match")

        # set vincitore e commit prima della transizione
        match.winner_id = winner_id
        db.session.add(match)
        db.session.commit()

        # transizione centralizzata
        # import locale per evitare cicli
        from models.match.services import MatchService

        MatchService.to_completed(match.id)

        # ricarica o restituisci l'oggetto aggiornato
        return match


__all__ = [
    "MatchService",
    "RackService",
    "MatchResultService",
    "InvalidTransitionError",
]
