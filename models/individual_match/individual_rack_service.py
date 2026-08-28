"""
Module: models/individual_match/individual_rack_service.py
Purpose: Rack management service for individual matches (extracted
    from IndividualMatchService)
Sprint 13: IndividualMatchService decomposition
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from flask_babel import gettext as _
from sqlalchemy import func

from ..base import db, utc_now
from ..exceptions import NotFoundError, ValidationError
from ..transaction.manager import transactional
from .models import IndividualMatch, IndividualRack


class IndividualRackService:
    """Service for rack management in individual matches."""

    @staticmethod
    @transactional(domain="individual_match")
    def add_rack_for_player(
        match_id: int,
        user_id: int,
        winner_id: int,
    ) -> IndividualRack:
        """Add a rack won by specified player (new simplified UX)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_player(user_id):
            raise ValueError("User is not part of this match")

        if not match.is_player(winner_id):
            raise ValueError("Invalid winner ID")

        # A partita finita non si segna più. La regola era già scritta —
        # `can_add_rack()` sul modello, e `match_scoring_state` che le fa
        # sparire i «+1» — ma nessuno la chiedeva qui, e l'interfaccia non è un
        # controllo: il tabellone orizzontale resta aperto sul telefono
        # appoggiato alla sponda, e una pagina che non sa di essere vecchia
        # manda comunque il triangolo.
        #
        # In «esattamente N» non è contabilità: a 2-2 su quattro la partita è
        # **pari**, e un triangolo di troppo la portava a 3-2 assegnando la
        # vittoria a chi aveva premuto — dopo che era finita, e cancellando la
        # firma che il pareggio aveva già raccolto (`reset_confirmations`).
        #
        # Nel formato libero `can_add_rack()` risponde sempre di sì: là un
        # traguardo non c'è, e `is_ready_for_validation()` è vera dal primo
        # triangolo.
        if not match.can_add_rack():
            raise ValidationError(
                _("La partita è arrivata alla distanza: non si segna più.")
            )

        if match.is_multi_set:
            # Al meglio dei set il triangolo appartiene al **set in corso**, e
            # `player*_score` conta i set vinti, non i triangoli. Questa
            # funzione lo ignorava: creava il triangolo attaccato alla partita
            # e alzava di uno il punteggio, quindi il set non si chiudeva mai,
            # quello successivo non poteva cominciare e il punteggio diceva
            # «2 set a 0» dopo due triangoli. Una sfida al meglio dei set,
            # dall'interfaccia, non arrivava in fondo in nessun modo.
            #
            # La logica dei set sta già sul modello (`IndividualSet`): qui si
            # delega, invece di riscriverla una seconda volta.
            break_player_id = match.next_break_player_id
            rack = match.add_rack_result(winner_id)
            rack.added_by_id = user_id
            rack.added_at = utc_now()
            rack.break_player_id = break_player_id
        else:
            # Include ALL racks (even deleted) for max calculation
            # because UNIQUE constraint is on (match_id, rack_number)
            max_rack = (
                db.session.query(func.max(IndividualRack.rack_number))
                .filter_by(match_id=match_id)
                .scalar()
            )
            rack_number = (max_rack or 0) + 1

            # Chi apre questo triangolo, dedotto dalla regola di apertura
            # della sfida e da chi ha vinto i precedenti — e scritto sul
            # triangolo, perché è un fatto (ADR-056). Va letto **prima** di
            # creare il rack: dopo, la deduzione risponderebbe per quello
            # successivo.
            break_player_id = match.next_break_player_id

            rack = IndividualRack(
                match_id=match_id,
                rack_number=rack_number,
                winner_id=winner_id,
                break_player_id=break_player_id,
                added_by_id=user_id,
                added_at=utc_now(),
            )

            db.session.add(rack)

            if winner_id == match.player1_id:
                match.player1_score += 1
            else:
                match.player2_score += 1

        # Reset confirmations when score changes
        match.reset_confirmations()

        # Auto-confirm when distance is reached:
        # - Winner auto-confirms (loser must accept)
        # - Tie: rack adder auto-confirms (opponent must accept)
        #
        # `distance is not None`: nel **formato libero** non c'è nessun
        # traguardo da raggiungere — la partita finisce quando lo decidono i
        # giocatori — e `is_ready_for_validation()` è vera fin dal primo
        # triangolo. Senza questa guardia ogni triangolo firmava d'ufficio per
        # chi era in vantaggio, e la doppia conferma diventava un'illusione: al
        # primo «Termina la sfida» dell'altro la partita si chiudeva con una
        # firma che nessuno aveva dato. Chi era in vantaggio, per giunta, non
        # vedeva mai il proprio pulsante fare niente — era già confermato.
        if match.distance is not None and match.is_ready_for_validation():
            if match.player1_score > match.player2_score:
                match.confirm_result(match.player1_id)
            elif match.player2_score > match.player1_score:
                match.confirm_result(match.player2_id)
            else:
                match.confirm_result(user_id)

        return rack

    @staticmethod
    @transactional(domain="individual_match")
    def remove_rack_for_player(
        match_id: int,
        user_id: int,
        player_id: int,
    ) -> None:
        """Remove last rack won by specified player (new simplified UX)."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_player(user_id):
            raise ValueError("User is not part of this match")

        if match.is_multi_set:
            # Il triangolo appartiene a un set, e `player*_score` conta i set:
            # toglierlo di qui abbasserebbe i **set vinti**. Se ne occupa il
            # set, che sa anche riaprirsi quando il triangolo tolto era quello
            # che l'aveva chiuso.
            insieme = IndividualRackService._set_da_correggere(match)
            if insieme is None:
                raise ValueError("No rack to remove for this player")
            tolto = insieme.remove_last_rack(user_id, player_id=player_id)
            if tolto is None:
                raise ValueError("No rack to remove for this player")
        else:
            last_rack = (
                IndividualRack.query.filter_by(
                    match_id=match_id, winner_id=player_id, is_deleted=False
                )
                .order_by(IndividualRack.rack_number.desc())
                .first()
            )

            if not last_rack:
                raise ValueError("No rack to remove for this player")

            last_rack.is_deleted = True
            last_rack.removed_by_id = user_id
            last_rack.removed_at = utc_now()

            if player_id == match.player1_id:
                match.player1_score = max(0, match.player1_score - 1)
            else:
                match.player2_score = max(0, match.player2_score - 1)

        match.player1_confirmed = False
        match.player2_confirmed = False
        match.player1_confirmed_at = None
        match.player2_confirmed_at = None

    @staticmethod
    @transactional(domain="individual_match")
    def register_lag(
        match_id: int,
        lag_winner_id: int,
        first_break_player_id: int,
    ) -> None:
        """Esito dell'acchito su una sfida individuale (ADR-056)."""
        from models.match import opening_service

        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise NotFoundError(_("Partita non trovata."))
        opening_service.register_lag(match, lag_winner_id, first_break_player_id)

    @staticmethod
    @transactional(domain="individual_match")
    def toggle_run_out(match_id: int, rack_id: int) -> dict:
        """Marca o smarca un triangolo di sfida come chiuso in una visita."""
        from models.match import opening_service

        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise NotFoundError(_("Partita non trovata."))
        return opening_service.toggle_run_out(match, rack_id)

    @staticmethod
    def _set_da_correggere(match: IndividualMatch):
        """Il set su cui agisce l'annulla: quello in corso, o l'ultimo chiuso.

        Fra un set e l'altro non c'è nessun set «in corso», ed è proprio il
        momento in cui un triangolo di troppo fa più danno: ha appena chiuso
        un set. Si torna indietro sull'ultimo che ne ha uno.
        """
        corrente = match.get_current_set()
        if corrente is not None:
            return corrente
        chiusi = [s for s in (match.sets or []) if s.racks]
        if not chiusi:
            return None
        return max(chiusi, key=lambda s: s.set_number)

    @staticmethod
    @transactional(domain="individual_match")
    def submit_rack_result(
        match_id: int,
        user_id: int,
        winner_id: int,
        rack_number: int,
        notes: Optional[str] = None,
    ) -> IndividualRack:
        """Submit result for a rack - legacy method for backward compatibility."""
        return IndividualRackService.add_rack_for_player(
            match_id=match_id,
            user_id=user_id,
            winner_id=winner_id,
        )

    @staticmethod
    @transactional(domain="individual_match")
    def add_rack_result(
        match_id: int,
        rack_number: Optional[int] = None,
        winner_id: Optional[int] = None,
        reported_by_id: Optional[int] = None,
        break_player_id: Optional[int] = None,
        notes: Optional[str] = None,
        **kwargs,
    ) -> IndividualRack:
        """Add a rack result with flexible parameters for test compatibility."""
        if rack_number is not None and reported_by_id is not None:
            return IndividualRackService.submit_rack_result(
                match_id=match_id,
                user_id=reported_by_id,
                winner_id=winner_id,
                rack_number=rack_number,
            )
        elif len(kwargs) == 1 and "user_id" in kwargs:
            user_id = kwargs["user_id"]
            return IndividualRackService._add_rack_result_original(
                match_id=match_id, winner_id=winner_id, user_id=user_id
            )
        else:
            raise ValueError("Invalid parameters for add_rack_result")

    @staticmethod
    @transactional(domain="individual_match")
    def _add_rack_result_original(
        match_id: int, winner_id: int, user_id: int
    ) -> IndividualRack:
        """Original add_rack_result implementation."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        if not match.is_player(user_id):
            raise ValueError("Only match players can add rack results")

        rack = match.add_rack_result(winner_id)
        return rack

    @staticmethod
    @transactional(domain="individual_match")
    def confirm_rack_result(rack_id: int, confirming_player_id: int) -> Dict[str, Any]:
        """Confirm a rack result."""
        rack = db.session.get(IndividualRack, rack_id)
        if not rack:
            raise ValueError(f"Rack {rack_id} not found")

        rack.confirmed_by_player = True

        return {"success": True, "message": "Rack result confirmed"}

    @staticmethod
    @transactional(domain="individual_match")
    def dispute_rack_result(
        rack_id: int, disputing_player_id: int, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dispute a rack result."""
        rack = db.session.get(IndividualRack, rack_id)
        if not rack:
            raise ValueError(f"Rack {rack_id} not found")

        match = rack.match
        if not match.is_player(disputing_player_id):
            raise ValueError("Only match players can dispute rack results")

        return {
            "success": True,
            "message": (
                f"Rack {rack.rack_number} result disputed by player "
                f"{disputing_player_id}"
            ),
            "reason": reason,
        }

    @staticmethod
    @transactional(domain="individual_match")
    def resolve_rack_dispute(
        rack_id: int, admin_user_id: int, resolution: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a rack result dispute."""
        rack = db.session.get(IndividualRack, rack_id)
        if not rack:
            raise ValueError(f"Rack {rack_id} not found")

        return {
            "success": True,
            "message": (
                f"Rack {rack.rack_number} dispute resolved by admin {admin_user_id}"
            ),
            "resolution": resolution,
            "reason": reason,
        }
