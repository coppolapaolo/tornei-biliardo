"""
Module: models/challenge/services.py
Purpose: Challenge domain services for business logic
Requirements: SPECIFICHE.md - Challenge management and statistics
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from sqlalchemy import desc

from ..base import db
from ..transaction.manager import transactional
from .models import Challenge, ChallengeAttempt, ChallengeFavorite


class ChallengeService:
    """Service per la gestione delle sfide (challenges) e business logic.

    Gestisce il sistema di sfide individuali per l'allenamento e valutazione
    delle competenze dei giocatori, incluso:
    - CRUD operations per sfide
    - Sistema dei preferiti per i giocatori
    - Integrazione X-replacement per sostituzioni in campionato
    - Statistiche e cronologia tentativi
    """

    @staticmethod
    @transactional(domain="challenge")
    def create_challenge(
        description: str,
        image_path: str,
        pass_fail_only: bool = False,
        created_by_id: Optional[int] = None,
    ) -> Challenge:
        """Crea una nuova sfida nel sistema.

        Args:
            description: Descrizione della sfida e istruzioni per il giocatore
            image_path: Percorso all'immagine che illustra la sfida
            pass_fail_only: True se pass/fail, False se punteggio numerico
            created_by_id: ID del direttore/admin che ha creato la sfida (opzionale)

        Returns:
            Challenge: L'oggetto sfida creato e persistito nel database
        """
        challenge = Challenge(
            description=description,
            pass_fail_only=pass_fail_only,
            image_path=image_path,
            created_by_id=created_by_id,
        )

        db.session.add(challenge)
        return challenge

    @staticmethod
    @transactional(domain="challenge")
    def update_challenge(
        challenge_id: int,
        description: Optional[str] = None,
        image_path: Optional[str] = None,
        pass_fail_only: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> Challenge:
        """Aggiorna una sfida esistente con validazione.

        Args:
            challenge_id: ID della sfida da modificare
            description: Nuova descrizione (mantiene esistente se None)
            image_path: Nuovo percorso immagine (mantiene esistente se None)
            pass_fail_only: Nuovo tipo di scoring (mantiene esistente se None)
            is_active: Nuovo stato attivo/inattivo (mantiene esistente se None)

        Returns:
            Challenge: L'oggetto sfida aggiornato

        Raises:
            404: Se la sfida non esiste
        """
        challenge = db.session.get(Challenge, challenge_id)
        if not challenge:
            from flask import abort
            abort(404)

        # Aggiorna solo i campi specificati (pattern partial update)
        if description is not None:
            challenge.description = description
        if image_path is not None:
            challenge.image_path = image_path
        if pass_fail_only is not None:
            challenge.pass_fail_only = pass_fail_only
        if is_active is not None:
            challenge.is_active = is_active

        return challenge

    @staticmethod
    def get_all_challenges() -> List[Challenge]:
        """Recupera tutte le sfide (incluse quelle inattive) - solo per admin."""
        return db.session.query(Challenge).all()

    @staticmethod
    def get_active_challenges() -> List[Challenge]:
        """Recupera solo le sfide attive visibili ai giocatori."""
        return db.session.query(Challenge).filter_by(is_active=True).all()

    @staticmethod
    def get_user_challenges(user_id: int) -> Dict[str, List[Challenge]]:
        """Organizza sfide attive per relazione con l'utente specificato.

        Args:
            user_id: ID del giocatore per cui organizzare le sfide

        Returns:
            Dict con chiavi:
            - 'favorites': Sfide contrassegnate come preferite dall'utente
            - 'attempted': Sfide già tentate dall'utente (con cronologia)
            - 'general': Sfide mai tentate dall'utente (catalogo generale)
        """
        # Recupera solo sfide attive per evitare confusione
        all_challenges = ChallengeService.get_active_challenges()

        # Identifica preferiti dell'utente tramite relazione ChallengeFavorite
        favorite_ids = {
            fav.challenge_id
            for fav in db.session.query(ChallengeFavorite)
            .filter_by(user_id=user_id)
            .all()
        }
        favorites = [c for c in all_challenges if c.id in favorite_ids]

        # Identifica sfide già tentate dall'utente (cronologia)
        attempted_ids = {
            att.challenge_id
            for att in db.session.query(ChallengeAttempt)
            .filter_by(user_id=user_id)
            .all()
        }
        attempted = [c for c in all_challenges if c.id in attempted_ids]

        # Catalogo generale: sfide non ancora tentate dall'utente
        general = [c for c in all_challenges if c.id not in attempted_ids]

        return {"favorites": favorites, "attempted": attempted, "general": general}

    @staticmethod
    def get_catalog_data(user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get complete data structure for challenge catalog (active only)."""
        # Everyone sees only active challenges
        all_challenges = ChallengeService.get_active_challenges()

        result = {
            "all_challenges": all_challenges,
            "my_challenges": [],
            "favorite_challenges": [],
            "user_favorites": set(),
        }

        if user_id:
            # Get user's created active challenges
            my_challenges = (
                db.session.query(Challenge)
                .filter_by(created_by_id=user_id, is_active=True)
                .all()
            )
            result["my_challenges"] = my_challenges

            # Get user's favorites (only from active challenges)
            favorite_ids = {
                fav.challenge_id
                for fav in db.session.query(ChallengeFavorite)
                .filter_by(user_id=user_id)
                .all()
            }
            result["user_favorites"] = favorite_ids
            result["favorite_challenges"] = [
                c for c in all_challenges if c.id in favorite_ids
            ]

        return result

    @staticmethod
    @transactional(domain="challenge")
    def start_challenge_attempt(
        user_id: int,
        challenge_id: int,
        gara_id: Optional[int] = None,
        round_number: Optional[int] = None,
    ) -> ChallengeAttempt:
        """Start a new challenge attempt.

        If gara_id is provided, also creates a GaraByeChallenge entry to track
        the relationship (Competition → Challenge direction).
        """
        attempt = ChallengeAttempt(
            user_id=user_id,
            challenge_id=challenge_id,
            gara_id=gara_id,  # DEPRECATED: kept for backward compatibility
            round_number=round_number,  # DEPRECATED: kept for backward compatibility
        )

        db.session.add(attempt)
        db.session.flush()  # Get attempt.id before creating GaraByeChallenge

        # Create GaraByeChallenge entry for bye replacement (new pattern)
        if gara_id is not None and round_number is not None:
            from models.competition.gara_bye_challenge import GaraByeChallenge

            bye_challenge = GaraByeChallenge.create_for_bye(
                gara_id=gara_id,
                user_id=user_id,
                round_number=round_number,
            )
            bye_challenge.challenge_attempt_id = attempt.id
            db.session.add(bye_challenge)

        return attempt

    @staticmethod
    @transactional(domain="challenge")
    def complete_challenge_attempt(
        attempt_id: int,
        score: Optional[int] = None,
        passed: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> ChallengeAttempt:
        """Complete a challenge attempt with results."""
        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if not attempt:
            from flask import abort

            abort(404)

        attempt.complete_attempt(score=score, passed=passed)
        if notes:
            attempt.notes = notes

        return attempt

    @staticmethod
    @transactional(domain="challenge")
    def toggle_favorite(user_id: int, challenge_id: int) -> bool:
        """Toggle challenge as favorite. Returns True if added, False if removed."""
        favorite = (
            db.session.query(ChallengeFavorite)
            .filter_by(user_id=user_id, challenge_id=challenge_id)
            .first()
        )

        if favorite:
            db.session.delete(favorite)
            return False
        else:
            favorite = ChallengeFavorite(user_id=user_id, challenge_id=challenge_id)
            db.session.add(favorite)
            return True

    @staticmethod
    def get_challenge_for_x_replacement(gara_id: int) -> Optional[Challenge]:
        """Seleziona una sfida appropriata per sostituzione X in campionato.

        L'algoritmo di selezione implementa una strategia di equità:
        1. Filtra sfide attive con punteggio numerico (no pass/fail only)
        2. Conta utilizzi precedenti nella stessa gara
        3. Preferisce sfide meno utilizzate per bilanciamento

        Args:
            gara_id: ID della gara per cui trovare la sfida sostitutiva

        Returns:
            Challenge: Sfida selezionata, None se nessuna disponibile

        Note:
            X-replacement: quando un giocatore ha 'bye' può fare una sfida
            invece di riposare, per mantenere attivo l'allenamento.
        """
        # Criteri per X-replacement: attive e con scoring numerico (no pass/fail)
        suitable_challenges = (
            db.session.query(Challenge)
            .filter_by(is_active=True, pass_fail_only=False)
            .all()
        )

        if not suitable_challenges:
            return None

        # Algoritmo equità: conta utilizzi per gara per bilanciare le sfide
        challenge_usage = {}
        for challenge in suitable_challenges:
            usage_count = (
                db.session.query(ChallengeAttempt)
                .filter_by(challenge_id=challenge.id, gara_id=gara_id)
                .count()
            )
            challenge_usage[challenge.id] = usage_count

        # Selezione: sfida con minor numero di utilizzi nella gara corrente
        min_usage = min(challenge_usage.values())
        for challenge in suitable_challenges:
            if challenge_usage[challenge.id] == min_usage:
                return challenge

        return suitable_challenges[0]  # Fallback se tutte hanno stesso utilizzo

    @staticmethod
    def create_x_replacement_attempt(
        user_id: int,
        gara_id: int,
        round_number: int,
        challenge_id: Optional[int] = None,
    ) -> ChallengeAttempt:
        """Create a challenge attempt to replace X in campionato."""

        final_challenge_id: int
        if challenge_id is None:
            challenge = ChallengeService.get_challenge_for_x_replacement(gara_id)
            if not challenge:
                raise ValueError("No suitable challenge available for X replacement")
            final_challenge_id = challenge.id
        else:
            final_challenge_id = challenge_id

        attempt = ChallengeService.start_challenge_attempt(
            user_id=user_id,
            challenge_id=final_challenge_id,
            gara_id=gara_id,
            round_number=round_number,
        )

        return attempt

    @staticmethod
    def complete_x_replacement_attempt(
        attempt_id: int, score: int, notes: Optional[str] = None
    ) -> ChallengeAttempt:
        """Complete X replacement challenge and return match-equivalent result."""
        from models.competition.gara_bye_challenge import GaraByeChallenge

        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if not attempt:
            from flask import abort

            abort(404)

        # Complete the attempt
        attempt.complete_attempt(score=score, passed=None)

        # Set notes separately if provided
        if notes:
            attempt.notes = notes

        # Mark GaraByeChallenge as completed (new pattern)
        bye_challenge = GaraByeChallenge.query.filter_by(
            challenge_attempt_id=attempt_id
        ).first()
        if bye_challenge:
            bye_challenge.complete_with_attempt(attempt_id)

        # Create equivalent match result for campionato classification
        ChallengeService._create_x_replacement_match_result(attempt)

        return attempt

    @staticmethod
    @transactional(domain="challenge")
    def _create_x_replacement_match_result(attempt: ChallengeAttempt) -> None:
        """Create a match result equivalent for X replacement challenge.

        Uses GaraByeChallenge to get gara context (Competition → Challenge direction).
        Falls back to attempt.gara_id for backward compatibility with existing data.
        """
        from ..match.models import Match
        from models.competition.gara_bye_challenge import GaraByeChallenge

        # Try to get gara context from GaraByeChallenge (new pattern)
        bye_challenge = GaraByeChallenge.query.filter_by(
            challenge_attempt_id=attempt.id
        ).first()

        if bye_challenge:
            gara_id = bye_challenge.gara_id
            round_number = bye_challenge.round_number
        else:
            # Backward compatibility: use deprecated attempt fields
            gara_id = attempt.gara_id
            round_number = attempt.round_number

        if not gara_id or not round_number:
            # Not an X replacement challenge, skip match creation
            return

        # Find or create a match for this X replacement
        match = (
            db.session.query(Match)
            .filter_by(
                gara_id=gara_id,
                round_number=round_number,
                player1_id=attempt.user_id,
                is_bye=True,
            )
            .first()
        )

        if not match:
            match = Match(
                gara_id=gara_id,
                round_number=round_number,
                player1_id=attempt.user_id,
                player2_id=None,
                is_bye=True,
                status="completed",
                winner_id=attempt.user_id,
            )
            db.session.add(match)

        # Set match scores based on challenge performance
        # Use raw score as rack equivalent (simplified, no invented scaling)
        match.player1_score = max(1, attempt.score or 0)  # At least 1 for the win
        match.player2_score = 0  # X gets 0

    @staticmethod
    def get_admin_statistics() -> List[Dict[str, Any]]:
        """Get statistics for all challenges (admin view)."""
        challenges = Challenge.query.all()
        return [
            {"challenge": challenge, "stats": challenge.get_statistics()}
            for challenge in challenges
        ]

    @staticmethod
    def get_user_challenge_history(user_id: int) -> List[ChallengeAttempt]:
        """Get user's complete challenge attempt history."""
        return (
            ChallengeAttempt.query.filter_by(user_id=user_id, completed=True)
            .order_by(desc("attempted_at"))
            .all()
        )

    @staticmethod
    @transactional(domain="challenge")
    def delete_challenge(challenge_id: int) -> None:
        """Elimina una sfida con logica intelligente per preservare integrità dati.

        Strategia di eliminazione:
        - Hard delete: se mai utilizzata (no tentativi, no selezioni gara)
        - Soft delete: se utilizzata, marca is_active=False per nascondere

        Args:
            challenge_id: ID della sfida da eliminare

        Raises:
            404: Se la sfida non esiste

        Note:
            La soft delete preserva l'integrità referenziale per cronologie
            e statistiche esistenti, mentre nasconde la sfida dai cataloghi.
        """
        challenge = db.session.get(Challenge, challenge_id)
        if not challenge:
            from flask import abort

            abort(404)

        # Verifica se la sfida ha tentativi registrati (cronologia)
        has_attempts = (
            db.session.query(ChallengeAttempt)
            .filter_by(challenge_id=challenge_id)
            .first()
            is not None
        )

        # Verifica se la sfida è stata selezionata in qualche gara
        # Controlla relazioni gara-challenge se il modello esiste
        has_gara_usage = False
        try:
            from models.competition.gara_challenge import GaraChallenge

            has_gara_usage = (
                db.session.query(GaraChallenge)
                .filter_by(challenge_id=challenge_id)
                .first()
                is not None
            )
        except ImportError:
            # Se non esiste relazione gara-challenge, salta questo controllo
            pass

        if not has_attempts and not has_gara_usage:
            # Hard delete: rimozione completa dal database (mai utilizzata)
            db.session.delete(challenge)
        else:
            # Soft delete: marca inattiva ma preserva per dati storici
            challenge.is_active = False

    @staticmethod
    def record_attempt(
        user_id: int,
        challenge_id: int,
        score: int,
        max_score: int = 100,
        gara_id: Optional[int] = None,
        round_number: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> ChallengeAttempt:
        """Registra un tentativo di sfida completo in una singola chiamata.

        Metodo di convenienza che combina start_challenge_attempt e
        complete_challenge_attempt. Registra solo il punteggio senza
        determinare automaticamente pass/fail.

        Args:
            user_id: ID del giocatore che tenta la sfida
            challenge_id: ID della sfida da tentare
            score: Punteggio ottenuto dal giocatore
            max_score: Punteggio massimo teorico (per riferimento, non usato per logica)
            gara_id: ID gara se il tentativo è durante una competizione
            round_number: Numero round se durante una competizione
            notes: Note aggiuntive sul tentativo

        Returns:
            ChallengeAttempt: Il tentativo completato e persistito
        """
        # Start the attempt
        attempt = ChallengeService.start_challenge_attempt(
            user_id=user_id,
            challenge_id=challenge_id,
            gara_id=gara_id,
            round_number=round_number,
        )

        # Complete the attempt with score (no pass/fail logic)
        completed_attempt = ChallengeService.complete_challenge_attempt(
            attempt_id=attempt.id,
            score=score,
            passed=None,  # No automatic pass/fail determination
            notes=notes,
        )

        return completed_attempt
