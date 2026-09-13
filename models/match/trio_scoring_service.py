"""
TrioScoringService - Scoring logic for TrioMatch domain.

Extracted from TrioMatch model to follow Single Responsibility Principle
and maintain consistency with ScoringService for regular matches.

Handles:
- Rack-level scoring with round-robin rotation
- Direct score setting for admin operations (quick result)
- Rack removal (undo)
- Full reset
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from flask_babel import gettext as _

from models.base import db
from models.status_enum import MatchStatus
from models.transaction.manager import transactional
from models.match.trio_schulze import determine_trio_winner

if TYPE_CHECKING:
    from .models import TrioMatch, TrioRack


class TrioScoringService:
    """Service for Trio scoring operations.

    Mirrors ScoringService pattern for regular matches.
    All methods take trio_id and load the TrioMatch internally.
    """

    # -----------------------------
    # RACK SCORING
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def add_rack_win(
        trio_id: int,
        winner_id: int,
        added_by_id: Optional[int] = None,
        authoritative: bool = False,
    ) -> Optional["TrioRack"]:
        """Add a rack win for a player in the round-robin.

        Creates a TrioRack record and updates the matchup for the next rack.

        Args:
            trio_id: ID of the TrioMatch
            winner_id: ID of the player who won the rack
            added_by_id: ID of user adding the rack (for audit)
            authoritative: chi segna dirige anche la gara: il punteggio e' gia'
                quello ufficiale e non ha bisogno della firma di nessuno

        Returns:
            The created TrioRack, or None if invalid (completed, wrong player, etc.)
        """
        from .models import TrioMatch, TrioRack

        trio = db.session.get(TrioMatch, trio_id)
        if trio is None:
            return None

        if trio.is_completed:
            return None

        config = trio.trio_config

        # Check if all racks are already played
        if trio.total_racks_played >= config.total_played_racks:
            return None

        # Get current matchup from config
        next_rack_number = trio.total_racks_played + 1
        matchup = config.get_matchup_for_rack(next_rack_number)
        if not matchup:
            return None

        p1_idx, p2_idx, waiting_idx = matchup
        current_p1_id = trio.player_ids[p1_idx]
        current_p2_id = trio.player_ids[p2_idx]
        waiting_id = trio.player_ids[waiting_idx]

        # Verify winner is one of the current players
        if winner_id not in [current_p1_id, current_p2_id]:
            return None

        # Create TrioRack record
        trio_rack = TrioRack(
            trio_match_id=trio.id,
            rack_number=next_rack_number,
            winner_id=winner_id,
            player1_id=current_p1_id,
            player2_id=current_p2_id,
            waiting_player_id=waiting_id,
            added_by_id=added_by_id,
        )
        db.session.add(trio_rack)

        # Flush to ensure the new rack is visible in the relationship
        db.session.flush()

        # Update current players for next rack
        TrioScoringService._update_current_players(trio)

        # Check if trio is completed
        if trio.total_racks_played >= config.total_played_racks:
            TrioScoringService._apply_bonus_and_complete(
                trio, added_by_id=added_by_id, authoritative=authoritative
            )

        return trio_rack

    @staticmethod
    @transactional(domain="match")
    def remove_last_rack(trio_id: int, removed_by_id: int) -> Optional["TrioRack"]:
        """Remove the last rack (undo).

        Soft-deletes the most recent active rack.

        Args:
            trio_id: ID of the TrioMatch
            removed_by_id: ID of user removing the rack (for audit)

        Returns:
            The removed TrioRack, or None if no racks to remove.
        """
        from .models import TrioMatch, Match

        trio = db.session.get(TrioMatch, trio_id)
        if trio is None:
            return None

        # Il sigillo del direttore vale anche qui. Fino al 2026-08-21 questa
        # difesa esisteva solo nel template (il pulsante spariva), quindi una
        # POST diretta all'endpoint riapriva una partita gia' messa agli atti.
        # Nella partita a due il rifiuto e' sempre stato sul server
        # (`ScoringService.remove_rack`); questo e' lo stesso rifiuto, con le
        # stesse parole.
        match_obj = db.session.get(Match, trio.match_id)
        if match_obj and match_obj.status == MatchStatus.CLOSED_UNILATERALLY.value:
            raise ValueError(
                _(
                    "Il risultato è già stato validato: per correggerlo serve "
                    "il direttore di gara"
                )
            )

        last = trio.last_rack
        if not last:
            return None

        # Soft delete
        last.soft_delete(removed_by_id)

        # If trio was awaiting confirmation, reset it and all player confirmations
        if trio.awaiting_confirmation:
            trio.awaiting_confirmation = False
            trio.bonus_applied = False  # Revert bonus that was pre-applied
            # Reset all player confirmations on undo
            trio.player1_confirmed = False
            trio.player2_confirmed = False
            trio.player3_confirmed = False

        # If trio was completed, reopen it
        if trio.is_completed:
            trio.is_completed = False
            trio.winner_id = None
            trio.bonus_applied = False

            # Revert associated match status
            match_obj = db.session.get(Match, trio.match_id)
            if match_obj:
                match_obj.status = MatchStatus.PLAYING.value
                match_obj.winner_id = None

        # Update current players to show the matchup for the removed rack
        TrioScoringService._update_current_players(trio)

        return last

    # -----------------------------
    # DIRECT RESULT (QUICK RESULT)
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def set_result_direct(
        trio_id: int, player1_racks: int, player2_racks: int, player3_racks: int
    ) -> bool:
        """Set trio result directly (for quick result entry).

        Creates synthetic TrioRack records to match the given scores.
        Validates that total racks match expected for the distance.

        Args:
            trio_id: ID of the TrioMatch
            player1_racks: Racks won by player 1
            player2_racks: Racks won by player 2
            player3_racks: Racks won by player 3

        Returns:
            True if result was set successfully.

        Raises:
            ValueError: If total racks don't match expected count for the distance.
        """
        from .models import TrioMatch, TrioRack, Match
        from .state_service import MatchStateService

        trio = db.session.get(TrioMatch, trio_id)
        if trio is None:
            raise ValueError(f"TrioMatch {trio_id} non trovato")

        config = trio.trio_config

        # Validate total racks
        total = player1_racks + player2_racks + player3_racks
        if total != config.total_played_racks:
            raise ValueError(
                _(
                    "Il totale dei triangoli (%(totale)s) deve essere %(attesi)s "
                    "per un trio con distanza %(distanza)s",
                    totale=total,
                    attesi=config.total_played_racks,
                    distanza=config.distance,
                )
            )

        # Validate per-player maximum (each player plays 2 racks per round)
        max_per_player = 2 * config.num_rounds
        for label, racks in [
            ("P1", player1_racks),
            ("P2", player2_racks),
            ("P3", player3_racks),
        ]:
            if racks > max_per_player:
                raise ValueError(
                    f"{label} non può vincere più di {max_per_player} rack "
                    f"(partecipa a {max_per_player} matchup su "
                    f"{config.total_played_racks})"
                )

        # Delete any existing racks
        for rack in trio.racks.all():
            db.session.delete(rack)
        db.session.flush()

        # Create synthetic racks matching the scores
        # Track remaining wins needed for each player
        remaining_wins = {
            trio.player1_id: player1_racks,
            trio.player2_id: player2_racks,
            trio.player3_id: player3_racks,
        }

        # Go through round-robin sequence and assign winners
        for rack_num in range(1, config.total_played_racks + 1):
            matchup = config.get_matchup_for_rack(rack_num)
            if not matchup:
                continue

            p1_idx, p2_idx, waiting_idx = matchup
            current_p1_id = trio.player_ids[p1_idx]
            current_p2_id = trio.player_ids[p2_idx]
            waiting_id = trio.player_ids[waiting_idx]

            # Assign winner: prefer player who still needs more wins
            p1_needs = remaining_wins.get(current_p1_id, 0)
            p2_needs = remaining_wins.get(current_p2_id, 0)
            if p1_needs >= p2_needs:
                winner_id = current_p1_id
            else:
                winner_id = current_p2_id

            remaining_wins[winner_id] = remaining_wins.get(winner_id, 0) - 1

            trio_rack = TrioRack(
                trio_match_id=trio.id,
                rack_number=rack_num,
                winner_id=winner_id,
                player1_id=current_p1_id,
                player2_id=current_p2_id,
                waiting_player_id=waiting_id,
            )
            db.session.add(trio_rack)

        # Set bonus flag and complete
        trio.bonus_applied = config.bonus_racks > 0
        trio.is_completed = True

        # Update current players (will point past end since completed)
        TrioScoringService._update_current_players(trio)

        # Flush to ensure computed properties work
        db.session.flush()

        # Determine winner: with explicit totals from direct-entry, the natural
        # interpretation is "highest total wins". Schulze on synthetic racks can
        # report a tie even when totals are clearly dominant, because the greedy
        # synthetic distribution often equalizes pairwise matchups.
        # Only fall back to Schulze when totals themselves are tied.
        totals = {
            trio.player1_id: player1_racks,
            trio.player2_id: player2_racks,
            trio.player3_id: player3_racks,
        }
        max_racks = max(totals.values())
        top_players = [pid for pid, r in totals.items() if r == max_racks]
        if len(top_players) == 1:
            trio.winner_id = top_players[0]
        else:
            trio.winner_id = determine_trio_winner(trio.active_racks, trio.player_ids)

        # Update associated match and complete via service (emits SSE)
        match_obj = db.session.get(Match, trio.match_id)
        if match_obj:
            match_obj.winner_id = trio.winner_id
            match_obj.player1_score = player1_racks
            match_obj.player2_score = player2_racks
            # Niente `match_obj.validated_by_admin = True`: su `Match` quella
            # colonna non esiste (vive su `Rack`), e per i trio non serviva
            # comunque — il guard di `to_completed` li lascia passare da
            # PENDING perché `is_trio` è vera.
            #
            # Use service to complete - emits SSE and records PlayerEncounter
            MatchStateService.to_completed(match_obj.id)

        return True

    # -----------------------------
    # TOTALI DALLA CARD DEL DIRETTORE
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def set_racks_won(trio_id: int, punti: tuple, set_by_id: int) -> "TrioMatch":
        """Porta il trio ai triangoli vinti `punti` (uno per giocatore).

        E' il gesto degli stepper della card: un tocco cambia un totale di uno.
        I triangoli gia' registrati restano dove possono (`assegna_vincitori`
        cambia il minimo), quelli in piu' si annullano come l'annulla del
        segnapunti, quelli che mancano si aggiungono. Chi segna dirige: al
        totale dei triangoli la partita si chiude senza chiedere firme, come
        `add_trio_rack` con `authoritative`.

        Raises:
            ConflictError: il trio e' gia' chiuso.
            ValidationError: nessuna sequenza del girone da' quei totali.
        """
        from models.exceptions import ConflictError, ValidationError

        from .models import TrioMatch, TrioRack
        from .trio_punteggio import assegna_vincitori, massimo_per_giocatore

        trio = db.session.get(TrioMatch, trio_id)
        if trio is None:
            raise ValidationError(_("Partita non trovata"))
        if trio.is_completed:
            raise ConflictError(
                _("La partita è chiusa: si cambia azzerandola dal segnapunti.")
            )

        config = trio.trio_config
        attivi = sorted(trio.active_racks, key=lambda r: r.rack_number)
        esistenti = [trio.get_player_index(r.winner_id) for r in attivi]
        vincitori = assegna_vincitori(config, punti, esistenti)
        if vincitori is None:
            if any(p > massimo_per_giocatore(config) for p in punti):
                raise ValidationError(
                    _(
                        "Nel trio ognuno gioca %(n)s triangoli: non se ne "
                        "vincono di più.",
                        n=massimo_per_giocatore(config),
                    )
                )
            raise ValidationError(
                _(
                    "Questo punteggio non torna con l'ordine del girone: "
                    "il primo triangolo è fra il primo e il secondo giocatore, "
                    "il secondo fra il primo e il terzo."
                )
            )

        # Quelli che restano: il vincitore si corregge sul posto.
        for rack, vincitore in zip(attivi, vincitori):
            nuovo_id = trio.player_ids[vincitore]
            if rack.winner_id != nuovo_id:
                rack.winner_id = nuovo_id
        # Quelli in piu': annullati come dal segnapunti, restano nello storico.
        for rack in attivi[len(vincitori) :]:
            rack.soft_delete(set_by_id)
        # Quelli che mancano. Il numero segue il massimo di sempre, annullati
        # compresi, come per i triangoli della partita a due.
        prossimo = max((r.rack_number for r in trio.racks.all()), default=0) + 1
        for posizione in range(len(attivi), len(vincitori)):
            incontro = config.get_matchup_for_rack(posizione + 1)
            assert incontro is not None
            primo, secondo, attende = incontro
            db.session.add(
                TrioRack(
                    trio_match_id=trio.id,
                    rack_number=prossimo,
                    winner_id=trio.player_ids[vincitori[posizione]],
                    player1_id=trio.player_ids[primo],
                    player2_id=trio.player_ids[secondo],
                    waiting_player_id=trio.player_ids[attende],
                    added_by_id=set_by_id,
                )
            )
            prossimo += 1
        db.session.flush()

        # Sotto il totale non c'e' niente da confermare: le firme raccolte sul
        # punteggio di prima non valgono per questo.
        if trio.awaiting_confirmation:
            trio.awaiting_confirmation = False
            trio.bonus_applied = False
            trio.winner_id = None
            trio.player1_confirmed = False
            trio.player2_confirmed = False
            trio.player3_confirmed = False

        TrioScoringService._update_current_players(trio)

        if len(vincitori) >= config.total_played_racks:
            TrioScoringService._apply_bonus_and_complete(
                trio, added_by_id=set_by_id, authoritative=True
            )
        return trio

    # -----------------------------
    # RESET
    # -----------------------------

    @staticmethod
    @transactional(domain="match")
    def reset(trio_id: int) -> None:
        """Reset trio to initial state by deleting all TrioRack records.

        Preserves table assignment - status is set based on whether table is assigned:
        - PLAYING if table is assigned (ready to play)
        - PENDING if no table (waiting for assignment)

        Args:
            trio_id: ID of the TrioMatch
        """
        from .models import TrioMatch, Match

        trio = db.session.get(TrioMatch, trio_id)
        if trio is None:
            return

        # Hard delete all rack records (not soft delete - this is a full reset)
        for rack in trio.racks.all():
            db.session.delete(rack)

        # Reset state flags
        trio.bonus_applied = False
        trio.is_completed = False
        trio.winner_id = None
        trio.awaiting_confirmation = False
        trio.player1_confirmed = False
        trio.player2_confirmed = False
        trio.player3_confirmed = False

        # Set initial players for first rack (P1 vs P2, P3 waits)
        TrioScoringService._update_current_players(trio)

        # Reset associated match - preserve table assignment
        match_obj = db.session.get(Match, trio.match_id)
        if match_obj:
            match_obj.winner_id = None
            match_obj.player1_score = 0
            match_obj.player2_score = 0
            # Status based on table assignment (like regular match reset)
            if match_obj.table_assignment:
                match_obj.status = MatchStatus.PLAYING.value
            else:
                match_obj.status = MatchStatus.PENDING.value

            # B32: if match has no table, try to auto-assign a free one.
            if match_obj.status == MatchStatus.PENDING.value:
                from .table_assignment_service import TableAssignmentService

                db.session.flush()
                TableAssignmentService.assign_available_tables(match_obj.gara_id)

    # -----------------------------
    # HELPER METHODS (Private)
    # -----------------------------

    @staticmethod
    def _update_current_players(trio: "TrioMatch") -> None:
        """
        Update current_player1, current_player2, waiting_player based on next rack.
        """
        config = trio.trio_config
        next_rack = trio.total_racks_played + 1

        if next_rack > config.total_played_racks:
            # All racks done
            return

        matchup = config.get_matchup_for_rack(next_rack)
        if matchup:
            p1_idx, p2_idx, waiting_idx = matchup
            trio.current_player1_id = trio.player_ids[p1_idx]
            trio.current_player2_id = trio.player_ids[p2_idx]
            trio.waiting_player_id = trio.player_ids[waiting_idx]

    @staticmethod
    def _apply_bonus_and_complete(
        trio: "TrioMatch",
        added_by_id: Optional[int] = None,
        authoritative: bool = False,
    ) -> None:
        """Apply bonus flag and set trio to awaiting confirmation.

        Note: bonus_racks don't create actual rack records - the bonus is virtual
        and applied equally to all players for display/classification purposes.
        Since it's equal for all, it doesn't affect winner determination.

        Il trio entra in `awaiting_confirmation`, ma non a mani vuote: le firme
        che sono gia' implicite nel gesto appena compiuto vengono date qui,
        con le stesse tre regole della partita a due (`ScoringService.add_rack`):

        - **chi ha vinto** non ha ragione di contestare il proprio risultato;
        - **chi ha inserito** il triangolo decisivo ha gia' dichiarato come e'
          finita: richiederglielo e' chiedere due volte la stessa cosa, con in
          mezzo una schermata che sembra un ostacolo;
        - **chi dirige la gara** scrive gia' il punteggio ufficiale, da
          qualunque schermata lo faccia.

        Se le firme implicite sono tutte e tre, la partita si chiude da sola —
        e resta comunque annullabile finche' il direttore non valida: il gesto
        e' implicito, non irrevocabile.
        """
        config = trio.trio_config

        # Set bonus flag (for UI display - bonus is virtual, not actual racks)
        if config.bonus_racks > 0:
            trio.bonus_applied = True

        # Flush to ensure computed properties see all racks
        db.session.flush()

        # Determine winner using Condorcet/Schulze pairwise comparison
        trio.winner_id = determine_trio_winner(trio.active_racks, trio.player_ids)

        # Enter awaiting confirmation state (don't complete yet)
        trio.awaiting_confirmation = True

        # Firme implicite (vedi docstring). `winner_id` puo' essere None: il
        # trio ammette il pareggio, e li' nessuno ha "vinto" alcunche'.
        gia_daccordo = set()
        if trio.winner_id is not None:
            gia_daccordo.add(trio.winner_id)
        if added_by_id is not None and added_by_id in trio.player_ids:
            gia_daccordo.add(added_by_id)
        if authoritative:
            gia_daccordo.update(trio.player_ids)

        for player_id in gia_daccordo:
            if player_id == trio.player1_id:
                trio.player1_confirmed = True
            elif player_id == trio.player2_id:
                trio.player2_confirmed = True
            elif player_id == trio.player3_id:
                trio.player3_confirmed = True

        # Tutte e tre implicite: non resta niente da chiedere a nessuno.
        if trio.player1_confirmed and trio.player2_confirmed and trio.player3_confirmed:
            trio._finalize_trio(closed_by_director=False)


__all__ = ["TrioScoringService"]
