"""
Module: models/classification/campionato_classification.py
Purpose: le righe `Classification`, copia persistita della classifica generale

La classifica generale si calcola in un posto solo,
`TournamentStatisticsService.classifica_generale` (ADR-073). Qui la si scrive
nelle righe che leggono il profilo, l'export e gli inviti ai playoff: la
copia congela la classifica al momento dell'ultimo ricalcolo, ma non può più
dire una cosa diversa dalla pagina.
"""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import joinedload

from models.base import db

from ..caching import cache_invalidate, cache_manager, cached
from ..transaction import transactional
from .models import Classification, GaraClassification


class ClassificationService:
    """Le righe `Classification` di un campionato, e le letture su di esse."""

    @staticmethod
    def uses_position_points(campionato) -> bool:
        """Se la classifica generale di questo campionato somma punti-posizione.

        È la domanda «il campionato è a piazzamenti?», e ha una risposta sola:
        `piazzamenti.e_a_piazzamenti` (ADR-080). Qui ce n'era una copia, con i
        tipi a tabellone scritti come stringhe.
        """
        from models.campionato.piazzamenti import e_a_piazzamenti

        return e_a_piazzamenti(campionato)

    @staticmethod
    def playoff_finali(campionato) -> List[Tuple[Any, List[GaraClassification]]]:
        """Le finali playoff che decidono la classifica, con le loro righe.

        Una coppia `(gara, righe)` per ogni configurazione playoff che *decide*
        la classifica finale e la cui gara ha già una classifica finale.
        L'ordine segue `positions_from`, così Elite (dal 1°) precede Academy
        (dal 7°).

        Le righe sono in ordine di posizione **mostrata**, e fra chi la
        condivide in ordine alfabetico (decisione dell'utente, 2026-10-15):
        chi in finale è arrivato pari merito lo resta anche nel campionato, e
        separarli per id del giocatore era inventare un risultato. Campionato
        5: MARCO e FLAVIO, sesti pari in finale, erano 7° e 6°.

        Finché la gara di playoff non è chiusa la lista è vuota, e la
        classifica generale resta quella del campionato: è il comportamento
        giusto, non un caso da gestire a parte.
        """
        configurations = getattr(campionato, "playoff_configurations", None) or []
        candidate = [
            cfg
            for cfg in configurations
            if cfg.is_active and cfg.decides_final_ranking and cfg.gara is not None
        ]
        if not candidate:
            return []

        candidate.sort(key=lambda cfg: (cfg.positions_from or 0, cfg.id))

        finali: List[Tuple[Any, List[GaraClassification]]] = []
        for cfg in candidate:
            rows = (
                db.session.query(GaraClassification)
                .filter_by(gara_id=cfg.gara.id)
                .options(joinedload(GaraClassification.user))
                .all()
            )
            if rows:
                rows.sort(
                    key=lambda r: (
                        r.posizione_mostrata,
                        (r.user.username if r.user else "").casefold(),
                    )
                )
                finali.append((cfg.gara, rows))
        return finali

    @staticmethod
    def playoff_final_blocks(campionato) -> List[List[int]]:
        """I blocchi di giocatori il cui ordine lo detta una gara di playoff.

        Gli id delle righe di `playoff_finali`, nello stesso ordine. La legge
        `TournamentStatisticsService._ordine_deciso_dal_playoff`.
        """
        return [
            [row.user_id for row in rows]
            for _gara, rows in ClassificationService.playoff_finali(campionato)
        ]

    @staticmethod
    @transactional(domain="classification")
    def update_campionato_classification(campionato_id: int) -> List[Classification]:
        """Riscrive le righe `Classification` dalla classifica generale.

        Le righe sono la **copia** di `classifica_generale`, la stessa che
        mostra la pagina (ADR-073): posizione, vittorie, triangoli, differenza,
        gare giocate e punti per piazzamento, riga per riga.

        Non è in cache, e non deve esserci: fino al 2026-09-24 una seconda
        chiamata entro cinque minuti tornava il risultato di prima senza
        scrivere niente. Dopo aver scritto svuota le cache di chi legge le
        righe (`get_campionato_standings` e simili).
        """
        from models.campionato.models import Campionato
        from models.campionato.statistics_service import TournamentStatisticsService

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise ValueError(f"Campionato {campionato_id} not found")

        classifica = TournamentStatisticsService().classifica_generale(campionato_id)
        if not classifica:
            # «Non so niente» non è «non c'è più nessuno»: senza gare concluse
            # le righe restano dove sono, invece di sparire.
            return []

        existing_classifications = {
            c.user_id: c
            for c in db.session.query(Classification)
            .filter_by(campionato_id=campionato_id)
            .all()
        }

        classifications = []
        for position, dati in classifica:
            user_id = dati["user_id"]
            classification = existing_classifications.get(user_id)
            if not classification:
                classification = Classification(
                    campionato_id=campionato_id, user_id=user_id
                )

            classification.position = position
            classification.shown_position = dati.get("shown_position", position)
            classification.total_matches_won = dati["total_matches_won"]
            classification.total_racks_won = dati["total_racks_won"]
            classification.total_point_difference = dati["total_rack_difference"]
            classification.gare_played = dati["participations"]
            classification.total_position_points = dati.get("total_points", 0)

            db.session.add(classification)
            classifications.append(classification)

        # Chi non è più in classifica non deve restarci. L'upsert da solo non
        # basta: aggiorna e crea, ma non toglie, e una riga rimasta indietro non
        # è inerte — `start_playoff` qualifica leggendo proprio queste righe, e
        # il profilo giocatore le mostra. Un giocatore esce dalla classifica
        # quando una gara viene cancellata, quando un'iscrizione viene ritirata,
        # o quando una partecipazione viene spostata su un altro account
        # (ADR-048).
        rimasti = {dati["user_id"] for _position, dati in classifica}
        for user_id, orfana in existing_classifications.items():
            if user_id not in rimasti:
                db.session.delete(orfana)

        ClassificationService.invalidate_campionato_cache(campionato_id)
        return classifications

    @staticmethod
    @cached(
        ttl_seconds=600,
        tags=["classification", "campionato"],
        key_generator="campionato",
    )
    def get_campionato_standings(campionato_id: int) -> List[Classification]:
        """
        Get current campionato standings with caching.
        Cached for 10 minutes as standings don't change frequently.

        Args:
            campionato_id: ID of the campionato

        Returns:
            List of Classification objects ordered by position
        """
        return (
            db.session.query(Classification)
            .filter_by(campionato_id=campionato_id)
            .options(
                joinedload(getattr(Classification, "user"))
            )  # Eager load user data
            .order_by(Classification.position)
            .all()
        )

    @staticmethod
    @cached(ttl_seconds=300, tags=["classification", "user"])
    def get_player_ranking(
        campionato_id: int, user_id: int
    ) -> Optional[Classification]:
        """
        Get a specific player's ranking in a campionato with caching.

        Args:
            campionato_id: ID of the campionato
            user_id: ID of the player

        Returns:
            Classification object or None if not found
        """
        return (
            db.session.query(Classification)
            .options(joinedload(getattr(Classification, "user")))
            .filter_by(campionato_id=campionato_id, user_id=user_id)
            .first()
        )

    @staticmethod
    @cache_invalidate(tags=["classification", "campionato"])
    def invalidate_campionato_cache(campionato_id: int) -> None:
        """Invalidate all classification caches for a campionato."""
        # Additional specific cache invalidation
        cache_manager.invalidate_by_tags([f"campionato:{campionato_id}"])

    @staticmethod
    @cached(ttl_seconds=1800, tags=["classification", "campionato"])
    def get_player_statistics_summary(campionato_id: int) -> Dict[str, Any]:
        """Get comprehensive statistics summary for the campionato."""
        standings = ClassificationService.get_campionato_standings(campionato_id)

        if not standings:
            return {"total_players": 0, "completed": False}

        total_matches = sum(c.total_matches_won for c in standings)
        avg_matches_per_player = total_matches / len(standings) if standings else 0

        return {
            "total_players": len(standings),
            "total_matches_played": total_matches,
            "average_matches_per_player": round(avg_matches_per_player, 1),
            "leader": (
                {
                    "user_id": standings[0].user_id,
                    "username": (
                        standings[0].user.username if standings[0].user else "Unknown"
                    ),
                    "matches_won": standings[0].total_matches_won,
                    "point_difference": standings[0].total_point_difference,
                }
                if standings
                else None
            ),
            "completed": all(c.total_matches_won > 0 for c in standings),
        }
