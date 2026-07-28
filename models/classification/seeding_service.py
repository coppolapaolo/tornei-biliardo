"""
Module: models/classification/seeding_service.py
Purpose: Classifica di partenza della gara (turno 0), usata come tie-break
    iniziale della catena `previous_position`
Data Structures: SeedingService
Dependencies: models.base.db, models.classification.models
"""

from __future__ import annotations

from typing import Dict, List, Sequence

from models.base import db

from .models import RoundClassification

# Turno "virtuale" che ospita la classifica di partenza. Non ha match
# associati: esiste solo per dare un `previous_position` al turno 1.
SEEDING_ROUND = 0

# Sentinella per chi non compare nel seeding (es. iscritto dopo l'avvio):
# ordina dopo chiunque abbia una posizione reale.
NO_SEEDING_POSITION = 10**6


class SeedingService:
    """Persiste l'ordine iniziale dei giocatori come classifica di turno 0.

    Il metodo di accoppiamento del primo turno definisce implicitamente una
    classifica di partenza: sorteggio casuale, rating, classifica del
    campionato o ordine di iscrizione a seconda della configurazione. Quello
    è un fatto del torneo, non un dettaglio dell'algoritmo di pairing, e va
    conservato: i turni successivi risolvono i pari merito con
    `previous_position`, e senza un turno 0 la catena si spezza proprio al
    turno 1 (cadendo sul `user_id`, cioè sull'ordine di registrazione).

    Vincolo di ciclo di vita: il turno 0 esiste **solo mentre la gara è
    avviata**. Chi riporta la gara in `inscription` (annullamento avvio) deve
    chiamare `clear_seeding`, altrimenti un seeding stantio sopravvive a un
    cambio di iscritti.
    """

    @staticmethod
    def get_seeding(gara_id: int) -> List[RoundClassification]:
        """Classifica di partenza ordinata per posizione (vuota se assente)."""
        return (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=SEEDING_ROUND)
            .order_by(RoundClassification.position)
            .all()
        )

    @staticmethod
    def get_seeding_positions(gara_id: int) -> Dict[int, int]:
        """Mappa user_id -> posizione di partenza."""
        return {rc.user_id: rc.position for rc in SeedingService.get_seeding(gara_id)}

    @staticmethod
    def ensure_seeding(
        gara_id: int, ordered_player_ids: Sequence[int]
    ) -> List[RoundClassification]:
        """Crea la classifica di partenza se manca, altrimenti la restituisce.

        Idempotente per necessità, non per eleganza: il primo turno può essere
        annullato e riavviato, e rigenerare il seeding a ogni riavvio
        cambierebbe il sorteggio (oltre a violare il vincolo
        `unique_round_classification`).
        """
        existing = SeedingService.get_seeding(gara_id)
        if existing:
            return existing

        seeding: List[RoundClassification] = []
        seen: set[int] = set()
        for player_id in ordered_player_ids:
            if player_id is None or player_id in seen:
                continue
            seen.add(player_id)
            row = RoundClassification(
                gara_id=gara_id,
                round_number=SEEDING_ROUND,
                user_id=player_id,
                position=len(seeding) + 1,
                matches_won=0,
                rack_difference=0,
            )
            db.session.add(row)
            seeding.append(row)

        if seeding:
            db.session.flush()
        return seeding

    @staticmethod
    def clear_seeding(gara_id: int) -> int:
        """Elimina la classifica di partenza. Ritorna il numero di righe."""
        return (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=SEEDING_ROUND)
            .delete()
        )

    @staticmethod
    def sync_inscription_initial_order(gara_id: int) -> None:
        """Allinea `Inscription.initial_order` alla classifica di partenza.

        `initial_order` è il numero mostrato al giocatore come "Ordine
        sorteggio" (`templates/components/_player_inscription_info.html`).
        Storicamente veniva assegnato da un `random.shuffle` in
        `RoundService.start_first_round` scorrelato dal seeding usato per gli
        accoppiamenti: con policy `rating` o `classification` il giocatore
        vedeva un numero che non corrispondeva a nulla. Deve essere la
        posizione di partenza che l'algoritmo usa davvero.
        """
        from models.competition.models import Inscription

        positions = SeedingService.get_seeding_positions(gara_id)
        if not positions:
            return

        inscriptions = db.session.query(Inscription).filter_by(gara_id=gara_id).all()
        for inscription in inscriptions:
            position = positions.get(inscription.user_id)
            if position is not None:
                inscription.initial_order = position

    @staticmethod
    def persist_first_round_seeding(
        gara_id: int, strategy: object, pairings: Sequence[object]
    ) -> None:
        """Materializza il seeding dopo la creazione del primo turno.

        Punto di raccordo unico per i due percorsi che creano il primo turno
        (`RoundService.start_first_round` e
        `RoundCreationService._create_round_impl`). No-op per le strategie che
        non hanno un ordine di partenza significativo, e no-op se il seeding
        esiste già (Amalfi lo salva durante il pairing, gli serve come input).
        """
        if not getattr(strategy, "persists_seeding", False):
            return

        SeedingService.ensure_seeding(
            gara_id, SeedingService.order_from_pairings(pairings)
        )
        SeedingService.sync_inscription_initial_order(gara_id)

    @staticmethod
    def order_from_pairings(pairings: Sequence[object]) -> List[int]:
        """Deriva l'ordine di partenza dagli accoppiamenti del primo turno.

        Per le strategie in cui è il sorteggio a produrre gli accoppiamenti
        (random, round robin) la classifica di partenza non preesiste al
        pairing: si legge *dagli* accoppiamenti, nell'ordine in cui i
        giocatori vi compaiono. Bye e trio sono gestiti naturalmente perché
        `Pairing.players` contiene rispettivamente uno e tre giocatori.
        """
        order: List[int] = []
        seen: set[int] = set()
        for pairing in pairings:
            for player_id in getattr(pairing, "players", ()) or ():
                if player_id is None or player_id in seen:
                    continue
                seen.add(player_id)
                order.append(player_id)
        return order


__all__ = ["SeedingService", "SEEDING_ROUND", "NO_SEEDING_POSITION"]
