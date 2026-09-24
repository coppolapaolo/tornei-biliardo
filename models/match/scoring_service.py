"""
ScoringService - Scoring logic for Match domain.

Extracted from MatchService and RackService to follow Single Responsibility Principle.
Handles score calculation, validation, and match completion logic.

High-complexity methods have been refactored with helper functions to reduce CC.
"""

from __future__ import annotations

from typing import Optional, Tuple

from flask_babel import gettext as _

from models.base import db, utc_now
from models.exceptions import NotFoundError
from models.status_enum import MatchStatus
from models.transaction.manager import transactional
from .models import Match, Rack


class ScoringService:
    """Service for scoring operations with reduced cyclomatic complexity.

    Handles:
    - Rack-level scoring with auto-completion detection
    - Direct score setting for admin operations
    - Player rack addition/removal (simplified UX)
    - Forfeit handling
    """

    # -----------------------------
    # PLAYER UX - Simplified Scoring
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def add_rack_for_player(
        match_id: int,
        user_id: int,
        winner_id: int,
        authoritative: bool = False,
    ) -> Rack:
        """Add a rack won by specified player (simplified UX for tournament matches).

        Args:
            match_id: ID of the match
            user_id: ID of user adding the rack
            winner_id: ID of the player who won the rack
            authoritative: chi segna dirige anche la gara. Tiene il segnapunti
                da tavolo, comodo mentre si gioca, ma il suo punteggio non ha
                bisogno di essere confermato da nessuno: è già la parola del
                direttore. Chiedergli di accettare il risultato che ha appena
                scritto significherebbe fargli validare sé stesso.

        Returns:
            The created Rack object

        Raises:
            ValueError: If winner invalid or match not found
        """
        from sqlalchemy import func

        match = db.session.get(Match, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        # Validate winner
        if winner_id not in (match.player1_id, match.player2_id):
            raise ValueError("Invalid winner ID")

        # Validate against match.distance_config (ADR-027, override per turno).
        # Mirror del path admin (riga 229): senza questo, in modalità
        # "rack esatti" lo score può superare il limite via UI giocatore.
        ScoringService._validate_rack_addition(match, winner_id)

        # Get next rack number
        max_rack = (
            db.session.query(func.max(Rack.rack_number))
            .filter_by(match_id=match_id)
            .scalar()
        )
        rack_number = (max_rack or 0) + 1

        # Chi apre questo triangolo, **prima** di crearlo: dopo, il conteggio
        # dei triangoli attivi sarebbe già avanzato di uno e la deduzione
        # risponderebbe per quello successivo. Si scrive sul rack invece di
        # ricalcolarlo a ogni lettura perché è un fatto: se domani il direttore
        # cambia la regola di apertura della gara, i triangoli già giocati non
        # devono cambiare chi li ha aperti — e con loro le B/R del profilo
        # (ADR-056).
        break_player_id = match.next_break_player_id

        # Create rack with audit trail
        rack = Rack(
            match_id=match_id,
            rack_number=rack_number,
            winner_id=winner_id,
            break_player_id=break_player_id,
            added_by_id=user_id,
            added_at=utc_now(),
        )
        db.session.add(rack)

        # Update scores
        ScoringService._update_score_on_add(match, winner_id)

        # Reset confirmations when score changes
        match.reset_confirmations()

        # Auto-confirm winner when distance is reached
        # (winner has no reason to contest, only loser needs to confirm)
        if match.is_at_distance:
            winner_number = match.rack_score.get_winner()
            if winner_number is not None:
                # There's a clear winner - auto-confirm them
                match_winner_id = (
                    match.player1_id if winner_number == 1 else match.player2_id
                )
                match.confirm_result(match_winner_id)

                # Restano due modi perché anche la seconda firma sia già data.
                #
                # Il primo: a segnare il rack decisivo è stato **chi perde**.
                # Ha appena dichiarato il punto che chiude la partita a favore
                # dell'altro — chiedergli poi di accettare il risultato è
                # chiedergli due volte la stessa cosa, con in mezzo una
                # schermata che sembra un ostacolo.
                #
                # Il secondo: chi segna **dirige la gara**. Il suo punteggio è
                # già quello ufficiale, da qualunque schermata lo scriva.
                #
                # In entrambi i casi resta possibile annullare l'ultimo rack:
                # il gesto è implicito, non irrevocabile.
                loser_id = (
                    match.player2_id
                    if match_winner_id == match.player1_id
                    else match.player1_id
                )
                if authoritative or user_id == loser_id:
                    match.confirm_result(loser_id)
            elif authoritative:
                # Pareggio (in «esattamente N» con N pari). Qui nessuno ha
                # perso, quindi nessuna firma si può dare per implicita — tranne
                # quella di chi dirige la gara, il cui punteggio è già quello
                # ufficiale: vale col vincitore e vale senza. Fino al
                # 2026-09-24 il ramo mancava e il direttore restava davanti a
                # «Conferma».
                match.confirm_result(match.player1_id)
                match.confirm_result(match.player2_id)

        # Soft transition: pending → playing
        if match.status == MatchStatus.PENDING.value:
            match.status = MatchStatus.PLAYING.value

        return rack

    @staticmethod
    @transactional(domain="match")
    def register_lag(
        match_id: int,
        lag_winner_id: int,
        first_break_player_id: int,
    ) -> None:
        """Esito dell'acchito su un match di gara (ADR-056)."""
        from models.match import opening_service

        match = db.session.get(Match, match_id)
        if match is None:
            raise NotFoundError(_("Partita non trovata."))
        opening_service.register_lag(match, lag_winner_id, first_break_player_id)

    @staticmethod
    @transactional(domain="match")
    def toggle_run_out(match_id: int, rack_id: int) -> dict:
        """Marca o smarca un triangolo di gara come chiuso in una visita."""
        from models.match import opening_service

        match = db.session.get(Match, match_id)
        if match is None:
            raise NotFoundError(_("Partita non trovata."))
        return opening_service.toggle_run_out(match, rack_id)

    @staticmethod
    @transactional(domain="match")
    def remove_rack_for_player(match_id: int, user_id: int, player_id: int) -> None:
        """Remove last rack won by specified player (simplified UX).

        Args:
            match_id: ID of the match
            user_id: ID of user removing the rack
            player_id: ID of player whose rack to remove

        Raises:
            ValueError: If no rack to remove
        """
        match = db.session.get(Match, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        # Un rack segnato per sbaglio non smette di essere un errore quando è
        # l'ultimo: proprio quello chiude la partita, ed è il momento in cui
        # accorgersene costa di più. Finché il direttore non ha validato, i
        # giocatori possono tornare indietro; dopo, il risultato è agli atti e
        # si passa dal reset del direttore.
        #
        # Le due righe qui sotto sono la ragione per cui i due stati finali
        # hanno cambiato nome: si chiamavano COMPLETED e VALIDATED, e quello
        # dai poteri più forti portava il nome che suonava più debole. Ora si
        # legge quello che fanno — quel che i giocatori hanno concordato
        # possono disfarlo, quel che è stato messo agli atti no.
        if match.status == MatchStatus.CLOSED_UNILATERALLY.value:
            raise ValueError(
                _(
                    "Il risultato è già stato validato: per correggerlo serve "
                    "il direttore di gara"
                )
            )
        riapri = match.status == MatchStatus.CONFIRMED_BY_BOTH.value

        # Find last non-deleted rack for this player
        last_rack = (
            Rack.query.filter_by(
                match_id=match_id, winner_id=player_id, is_deleted=False
            )
            .order_by(Rack.rack_number.desc())
            .first()
        )

        if not last_rack:
            raise ValueError("No rack to remove for this player")

        # Soft delete with audit trail
        last_rack.is_deleted = True
        last_rack.removed_by_id = user_id
        last_rack.removed_at = utc_now()

        # Update scores
        ScoringService._update_score_on_remove(match, player_id)

        # Clear winner if score no longer justifies it
        if ScoringService._should_clear_winner(match):
            match.winner_id = None

        # Reset confirmations
        match.reset_confirmations()

        if riapri:
            # La partita era chiusa: riaprirla significa anche disfare ciò che
            # la chiusura aveva prodotto (i delta di rating), altrimenti il
            # punteggio torna indietro e le classifiche no.
            from .state_service import MatchStateService

            MatchStateService.emit_reopened_event(match)
            match.status = MatchStatus.PLAYING.value

    # -----------------------------
    # FORFEIT HANDLING
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def forfeit_match(match_id: int, user_id: int) -> Match:
        """Forfeit match - user loses, opponent gets maximum score.

        Also handles gara-level forfait policy (FORFEIT vs EXCLUDE).

        Args:
            match_id: ID of the match
            user_id: ID of player forfeiting

        Returns:
            The updated Match object

        Raises:
            ValueError: If invalid forfeit conditions
        """
        match = db.session.get(Match, match_id)
        if match is None:
            raise ValueError("Match non trovato")

        # Validate forfeit conditions
        ScoringService._validate_forfeit(match, user_id)

        # Determine winner and calculate scores
        winner_id, forfeit_player = ScoringService._determine_forfeit_outcome(
            match, user_id
        )
        winning_score = ScoringService._calculate_forfeit_score(match)

        # Apply forfeit scores
        ScoringService._apply_forfeit_scores(match, forfeit_player, winning_score)
        match.winner_id = winner_id

        # Complete the match
        from .state_service import MatchStateService

        match = MatchStateService.to_completed(match_id)

        # Handle gara-level forfait policy
        from models.competition.withdraw_policy_service import WithdrawPolicyService

        WithdrawPolicyService.handle_forfeit(gara_id=match.gara_id, user_id=user_id)

        return match

    # -----------------------------
    # ADMIN SCORING
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def add_rack_with_score_update(
        match_id: int,
        winner_id: int,
        reported_by_id: int = 1,
        validated_by_admin: bool = True,
    ) -> dict:
        """Add rack and auto-update match score with completion detection.

        Args:
            match_id: ID of the match
            winner_id: ID of rack winner
            reported_by_id: ID of reporter
            validated_by_admin: If True, auto-complete on winning score

        Returns:
            Dict with updated match state
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        # Un trio ha tre punteggi e una rotazione (chi aspetta, chi rientra):
        # sta tutto nel `TrioMatch`, e si segna dalle sue route
        # (`/admin/gara/trio/<id>/add_rack`). Qui si scriverebbero invece
        # `player1_score`/`player2_score` sul `Match`, cioè un secondo
        # punteggio accanto a quello vero, libero di divergere al primo tocco.
        # Nessuna schermata lo fa, ma l'endpoint lo accettava.
        if match.is_trio:
            raise ValueError(
                _(
                    "La partita a tre si segna dal suo tabellino, "
                    "non dai triangoli a due"
                )
            )

        # Validate match not already complete
        if match.rack_score.is_complete():
            raise ValueError(
                _("La partita è già finita, non è possibile aggiungere altri punti")
            )

        # Validate score limits before adding
        ScoringService._validate_rack_addition(match, winner_id)

        # Find next rack number and add rack
        from .services import RackService

        last_rack = (
            Rack.query.filter_by(match_id=match_id)
            .order_by(Rack.rack_number.desc())
            .first()
        )
        next_rack_number = (last_rack.rack_number + 1) if last_rack else 1

        RackService.add_rack_result(
            match_id=match.id,
            rack_number=next_rack_number,
            winner_id=winner_id,
            reported_by_id=reported_by_id,
            validated_by_admin=validated_by_admin,
        )

        # Reload match for updated scores
        db.session.refresh(match)

        # Handle completion if match is finished
        if match.rack_score.is_complete():
            ScoringService._handle_rack_completion(match, validated_by_admin)

        return {
            "success": True,
            "player1_score": match.player1_score,
            "player2_score": match.player2_score,
            "status": match.status,
        }

    @staticmethod
    @transactional(domain="match")
    def set_match_result_direct(
        match_id: int,
        player1_score: int,
        player2_score: int,
        parziale: bool = False,
    ) -> None:
        """Set complete match result directly (admin operation).

        Replaces all existing racks with new result.

        Args:
            match_id: ID of the match
            player1_score: Final score for player 1
            player2_score: Final score for player 2
            parziale: il punteggio arriva dagli stepper della card, un tocco
                alla volta, e puo' essere a meta' partita. Vedi
                `_validate_score_limits`.

        Raises:
            ValueError: If invalid scores
        """
        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} non trovato")

        if match.is_bye:
            raise ValueError("Non puoi modificare una partita bye!")

        # Validate scores
        ScoringService._validate_score_limits(
            match, player1_score, player2_score, parziale=parziale
        )

        # Determine winner and completion status
        is_complete, winner_id = ScoringService._calculate_result(
            match, player1_score, player2_score
        )

        # Replace all racks
        ScoringService._replace_all_racks(match, player1_score, player2_score)

        # Update match state
        ScoringService._update_match_with_result(
            match, player1_score, player2_score, winner_id, is_complete
        )

    # -----------------------------
    # HELPER METHODS (Private)
    # -----------------------------

    @staticmethod
    def _update_score_on_add(match: Match, winner_id: int) -> None:
        """Update match score when rack is added."""
        if winner_id == match.player1_id:
            match.player1_score += 1
        else:
            match.player2_score += 1

    @staticmethod
    def _update_score_on_remove(match: Match, player_id: int) -> None:
        """Update match score when rack is removed."""
        if player_id == match.player1_id:
            match.player1_score = max(0, match.player1_score - 1)
        else:
            match.player2_score = max(0, match.player2_score - 1)

    @staticmethod
    def _should_clear_winner(match: Match) -> bool:
        """Check if winner should be cleared based on current scores."""
        if not match.gara:
            return True
        # ADR-027: usa la distance del match per rispettare gli override per turno.
        distance = match.distance_config
        if distance.is_race_to_racks:
            winning_score = distance.get_winning_racks()
            return max(match.player1_score, match.player2_score) < winning_score
        return (match.player1_score + match.player2_score) < distance.racks

    @staticmethod
    def _validate_forfeit(match: Match, user_id: int) -> None:
        """Validate that forfeit is allowed."""
        if user_id not in [match.player1_id, match.player2_id]:
            raise ValueError("User is not a player in this match")
        if match.is_bye:
            raise ValueError("Cannot forfeit a bye match - it's an automatic win")
        # Chiusa vuol dire tutte e due le chiusure: fino al 2026-09-13 qui si
        # guardava solo `CLOSED_UNILATERALLY`, e una partita confermata dai due
        # giocatori lasciava passare il forfait, che ne riscriveva punteggio e
        # vincitore.
        if MatchStatus.is_finished(match.status):
            raise ValueError("Cannot forfeit a completed match")
        # Un turno superato non si tocca da nessuna strada: fino al 2026-09-13
        # lo rifiutava solo il ritiro deciso dal direttore, mentre il forfait
        # dichiarato dal giocatore passava.
        from models.competition.round_manager import AdvancedRoundManager
        from models.exceptions import ConflictError

        motivo = AdvancedRoundManager.motivo_turno_superato(match)
        if motivo:
            raise ConflictError(motivo)

    @staticmethod
    def _determine_forfeit_outcome(
        match: Match, user_id: int
    ) -> Tuple[Optional[int], int]:
        """Determine winner and forfeiting player number."""
        if user_id == match.player1_id:
            return match.player2_id, 1
        else:
            return match.player1_id, 2

    @staticmethod
    def _calculate_forfeit_score(match: Match) -> int:
        """Calculate winning score for forfeit."""
        return match.distance_config.walkover_score()

    @staticmethod
    def _apply_forfeit_scores(
        match: Match, forfeit_player: int, winning_score: int
    ) -> None:
        """Apply forfeit scores to match.

        The forfeiting player keeps their current score (racks already won).
        The winner receives at least the winning score (distance).

        In modalità "esatto numero di rack" (single-set, is_race_to_racks=False)
        il punteggio del vincitore è `racks - punteggio_perdente`: i rack non
        giocati vanno al vincitore, così l'invariante p1+p2 == racks resta valida
        (altrimenti winner=racks totali + rack del perdente → somma incoerente).

        Lo score del perdente viene SEMPRE normalizzato a int (mai None): un
        record legacy con score NULL romperebbe le stringhe punteggio ("None-6")
        e la classificazione, che somma player*_score direttamente senza `or 0`
        (models/classification/models.py).
        """
        distance = match.distance_config
        exact_racks = not match.is_multi_set and not distance.is_race_to_racks

        if forfeit_player == 1:
            # Player 1 forfeits (loser).
            if exact_racks:
                # Clampa il perdente a [0, racks] e deriva il vincitore come
                # differenza: mantiene p1+p2 == racks anche con record legacy
                # incoerenti (None, negativi, o score > racks).
                match.player1_score = min(
                    max(match.player1_score or 0, 0), distance.racks
                )
                match.player2_score = distance.racks - match.player1_score
            else:
                # Race-to: il perdente tiene i rack già vinti (normalizzati a int).
                match.player1_score = match.player1_score or 0
                if (match.player2_score or 0) < winning_score:
                    match.player2_score = winning_score
        else:
            # Player 2 forfeits (loser).
            if exact_racks:
                match.player2_score = min(
                    max(match.player2_score or 0, 0), distance.racks
                )
                match.player1_score = distance.racks - match.player2_score
            else:
                match.player2_score = match.player2_score or 0
                if (match.player1_score or 0) < winning_score:
                    match.player1_score = winning_score

    @staticmethod
    def _validate_rack_addition(match: Match, winner_id: int) -> None:
        """Validate that a rack can be added."""
        temp_p1_score = match.player1_score
        temp_p2_score = match.player2_score

        if winner_id == match.player1_id:
            temp_p1_score += 1
        else:
            temp_p2_score += 1

        # ADR-027: usa match.distance_config per rispettare override per turno.
        distance = match.distance_config
        if distance.is_race_to_racks:
            winning_racks = distance.get_winning_racks()
            if temp_p1_score > winning_racks or temp_p2_score > winning_racks:
                raise ValueError(
                    _(
                        "Partita già completata - limite raggiunto per '%(distanza)s'",
                        distanza=distance.to_display_string(),
                    )
                )
        else:
            total_racks = temp_p1_score + temp_p2_score
            if total_racks > distance.racks:
                raise ValueError(
                    _(
                        "Non è possibile superare il limite di %(n)s triangoli "
                        "totali per questa partita",
                        n=distance.racks,
                    )
                )

    @staticmethod
    def _handle_rack_completion(match: Match, validated_by_admin: bool) -> None:
        """Handle match completion after rack addition."""
        final_winner_id = match.rack_score.get_winner()

        if final_winner_id is None:
            # True tie (exact mode) - no winner
            match.winner_id = None
            if validated_by_admin:
                from .state_service import MatchStateService

                MatchStateService.to_completed(match.id)
            else:
                match.status = MatchStatus.CLOSED_UNILATERALLY.value
                db.session.add(match)
                match.reset_confirmations()
        else:
            # Convert player number to ID
            final_winner_id = (
                match.player1_id if final_winner_id == 1 else match.player2_id
            )

            if validated_by_admin:
                from .services import MatchResultService

                MatchResultService.submit_result(match.id, final_winner_id)
            else:
                match.winner_id = final_winner_id
                db.session.add(match)
                match.reset_confirmations()

    @staticmethod
    def _validate_score_limits(
        match: Match, player1_score: int, player2_score: int, parziale: bool = False
    ) -> None:
        """Validate score limits for direct result setting.

        For "race to n" matches, validates that both players cannot have
        the winning score simultaneously (logically impossible - match
        ends when first player reaches winning score).

        Con «esattamente N» il risultato secco deve dare N triangoli in totale:
        un totale diverso e' un errore di battitura, che altrimenti lascerebbe
        la partita aperta in silenzio. Con `parziale` il punteggio arriva dagli
        stepper della card a meta' partita, e basta che non superi N.
        """
        if player1_score < 0 or player2_score < 0:
            raise ValueError("I punteggi non possono essere negativi!")

        # ADR-027: usa match.distance_config per rispettare override per turno.
        distance = match.distance_config
        max_score = distance.racks
        if player1_score > max_score or player2_score > max_score:
            raise ValueError(f"I punteggi non possono superare {max_score}!")

        if distance.is_race_to_racks:
            winning_score = distance.get_winning_racks()
            if player1_score >= winning_score and player2_score >= winning_score:
                raise ValueError(
                    _(
                        "In una partita 'al %(n)s', entrambi i giocatori "
                        "non possono avere %(n)s o più punti!",
                        n=winning_score,
                    )
                )
        else:
            total_racks = player1_score + player2_score
            if parziale:
                if total_racks > distance.racks:
                    raise ValueError(
                        _(
                            "Non è possibile superare il limite di %(n)s triangoli "
                            "totali per questa partita",
                            n=distance.racks,
                        )
                    )
            elif total_racks != distance.racks:
                raise ValueError(
                    _(
                        "In modalità 'esatto numero', il totale dei triangoli "
                        "(%(totale)s) deve essere esattamente %(n)s!",
                        totale=total_racks,
                        n=distance.racks,
                    )
                )

    @staticmethod
    def _calculate_result(
        match: Match, player1_score: int, player2_score: int
    ) -> Tuple[bool, Optional[int]]:
        """Calculate if result is complete and who won."""
        # ADR-027: usa match.distance_config per rispettare override per turno.
        distance = match.distance_config
        winning_score = distance.get_winning_racks()

        if distance.is_race_to_racks:
            if player1_score >= winning_score:
                return True, match.player1_id
            elif player2_score >= winning_score:
                return True, match.player2_id
            return False, None
        else:
            total_racks = player1_score + player2_score
            if total_racks == distance.racks:
                if player1_score > player2_score:
                    return True, match.player1_id
                elif player2_score > player1_score:
                    return True, match.player2_id
                return True, None  # Tie
            return False, None

    @staticmethod
    def _replace_all_racks(
        match: Match, player1_score: int, player2_score: int
    ) -> None:
        """Replace all existing racks with new result."""
        from .services import RackService
        from .state_service import MatchStateService

        # Delete existing racks
        existing_racks = Rack.query.filter_by(match_id=match.id).all()
        for rack in existing_racks:
            db.session.delete(rack)

        # Ensure match is in playing state
        if match.status != MatchStatus.PLAYING.value:
            MatchStateService.to_playing(match.id)

        # Create new racks. Il contatore si chiama `_indice` e non `_`: in
        # questo modulo `_` è gettext, e assegnarlo in un `for` lo renderebbe
        # una variabile locale per tutta la funzione — con un `_()` più su,
        # sarebbe UnboundLocalError.
        rack_number = 1
        for _indice in range(player1_score):
            RackService.add_rack_result(
                match.id,
                rack_number,
                match.player1_id,
                1,
                validated_by_admin=True,
                bypass_validation=True,
            )
            rack_number += 1

        for _indice in range(player2_score):
            RackService.add_rack_result(
                match.id,
                rack_number,
                match.player2_id,
                1,
                validated_by_admin=True,
                bypass_validation=True,
            )
            rack_number += 1

    @staticmethod
    def _update_match_with_result(
        match: Match,
        player1_score: int,
        player2_score: int,
        winner_id: Optional[int],
        is_complete: bool,
    ) -> None:
        """Update match with final result.

        Qui c'erano due `match.validated_by_admin = ...`, una per ramo. Su
        `Match` quella colonna non esiste — vive su `Rack` — quindi SQLAlchemy
        accettava l'attributo di istanza, lo teneva per la durata della
        richiesta e non lo scriveva mai. Nessuno lo rileggeva: l'unico effetto
        era far credere a chi leggeva il codice che ci fosse un flag di
        validazione da tenere allineato allo stato.

        Il flag è lo stato, e lo si vede proprio dalle due righe rimaste: il
        ramo completo transita a COMPLETED, quello incompleto torna a PLAYING.
        """
        from .state_service import MatchStateService

        match.player1_score = player1_score
        match.player2_score = player2_score
        match.winner_id = winner_id

        if is_complete:
            if match.status != MatchStatus.CLOSED_UNILATERALLY.value:
                # È il percorso «risultato secco» del direttore: la partita può
                # non essere mai partita (nessun tavolo, quindi ancora
                # PENDING), e chiuderla comunque è appunto una sua facoltà.
                MatchStateService.to_completed(match.id, closed_by_director=True)

            # Release table
            if match.table_assignment:
                from .table_assignment_service import TableAssignmentService

                TableAssignmentService.release_and_reassign_table(match.id)
                match.table_assignment = None
        else:
            if match.status == MatchStatus.CLOSED_UNILATERALLY.value:
                match.status = MatchStatus.PLAYING.value


__all__ = ["ScoringService"]
