"""
Rating Calculation Service

Handles the mathematical logic for updating Elo ratings based on match results.
Supports both standard 1v1 matches and Trio matches (treated as multi-way comparison).
"""

import math
from typing import Dict, List, Optional, Tuple
from models.rating.models import RatingSystem, PlayerRating, MatchRatingHistory
from models.match.models import Match, TrioMatch
from models.rating.eligibility import RatingEligibility
from models.base import db
import logging

logger = logging.getLogger(__name__)

ELO_K_FACTOR = 32


class RatingCalculationService:
    """Service for calculating rating updates."""

    @staticmethod
    def calculate_expected_score(user_rating: int, opponent_rating: int) -> float:
        """
        Calculate expected score based on Elo formula.
        E = 1 / (1 + 10 ^ ((R_opp - R_user) / 400))
        """
        return 1.0 / (1.0 + math.pow(10, (opponent_rating - user_rating) / 400.0))

    @staticmethod
    def calculate_new_rating(
        current_rating: int,
        expected_score: float,
        actual_score: float,
        k_factor: int = ELO_K_FACTOR,
    ) -> int:
        """
        Calculate new rating based on standard Elo formula.
        R_new = R_old + K * (S - E)
        """
        delta = k_factor * (actual_score - expected_score)
        return int(round(current_rating + delta))

    @staticmethod
    def process_match_result(match: Match, systems=None) -> None:
        """
        Process the result of a completed (tournament) match and update ratings.

        Dual pool: di default aggiorna SIA ELO (competitivo) SIA ELO_GLOBAL
        (tornei + casual). I match di torneo contano in entrambi i pool; il
        pool globale è solo-display e NON tocca categoria/handicap/User.elo_rating.

        Idempotente PER POOL: se esiste già history per (match, sistema) quel
        pool è un no-op. Protegge da MatchCompletedEvent ri-emessi
        (reset→ricompletamento) e da recalc su match già processati.

        `systems` permette ai recalc di limitarsi a un singolo pool (il recalc
        globale, path-dependent, fonde con i casual e gira separato).

        NB: il caller (RatingEventHandlers / recalc) è responsabile di NON
        chiamare questo metodo per i match che `RatingEligibility` esclude
        (walkover, e handicap fra categorie diverse o non assegnate) — qui non
        rileggiamo la policy per non duplicarla, ma l'idempotenza resta una
        rete di sicurezza.
        """
        if systems is None:
            systems = [RatingSystem.ELO, RatingSystem.ELO_GLOBAL]

        for system in systems:
            if MatchRatingHistory.exists_for_match(match.id, system):
                logger.info(
                    f"Match {match.id} già processato per {system.value}, skip "
                    f"(idempotenza)."
                )
                continue

            if match.is_trio and match.trio_match:
                RatingCalculationService._process_trio_match(
                    match.trio_match, match.id, system
                )
            else:
                RatingCalculationService._process_standard_match(match, system)

    @staticmethod
    def process_individual_match_result(individual_match) -> None:
        """Aggiorna SOLO il pool ELO_GLOBAL per un match individuale VALIDATO.

        I casual non toccano l'ELO competitivo (riservato ai tornei arbitrati).
        Idempotente per (individual_match, ELO_GLOBAL): protegge da eventi
        ri-emessi (es. reject→re-conferma) e dal recalc globale.
        """
        system = RatingSystem.ELO_GLOBAL
        if MatchRatingHistory.exists_for_individual_match(individual_match.id, system):
            logger.info(
                f"Casual {individual_match.id} già processato per "
                f"{system.value}, skip (idempotenza)."
            )
            return

        RatingCalculationService._process_two_player(
            individual_match.player1_id,
            individual_match.player2_id,
            individual_match.player1_score or 0,
            individual_match.player2_score or 0,
            system,
            individual_match_id=individual_match.id,
        )

    @staticmethod
    def recalculate_all_elo() -> dict:
        """Reset and replay ALL ELO ratings from finished matches.

        Pure/in-transaction: no app context, no commit, no I/O. The caller is
        responsible for the transaction boundary (``@transactional``) and for
        committing/rolling back.

        Resets ``User.elo_rating`` (→ None), deletes ELO ``PlayerRating`` and
        ``MatchRatingHistory`` rows, then replays every finished match
        (``completed`` + ``validated``) in chronological order, skipping
        walkover and handicap matches (coherent with the rating event policy).

        Returns:
            dict: counters ``{processed, skipped, total}``.
        """
        from models.user.models import User
        from models.status_enum import MatchStatus

        # 1. Reset User.elo_rating (None = "not yet rated").
        for user in User.query.all():
            user.elo_rating = None
            db.session.add(user)

        # 2. Drop ELO PlayerRating + history so the replay starts from default.
        db.session.query(PlayerRating).filter_by(
            rating_system=RatingSystem.ELO
        ).delete()
        db.session.query(MatchRatingHistory).filter_by(
            rating_system=RatingSystem.ELO
        ).delete()
        db.session.flush()

        # 3. Replay finished matches chronologically.
        matches = (
            Match.query.filter(Match.status.in_(MatchStatus.finished_values()))
            .order_by(Match.ended_at.asc(), Match.id.asc())
            .all()
        )
        # Le categorie di tutte le gare toccate in una query sola: senza,
        # l'eleggibilità farebbe due letture per ogni match del replay.
        categorie = RatingEligibility.build_index(matches)
        processed = 0
        skipped = 0
        for match in matches:
            if not RatingEligibility.counts_for_rating(match, categorie):
                skipped += 1
                continue
            # Solo pool competitivo: il pool globale è path-dependent e va
            # ricalcolato fondendo i casual (recalculate_all_elo_global).
            RatingCalculationService.process_match_result(
                match, systems=[RatingSystem.ELO]
            )
            processed += 1

        return {"processed": processed, "skipped": skipped, "total": len(matches)}

    @staticmethod
    def recalculate_all_elo_global() -> dict:
        """Reset e replay del pool ELO_GLOBAL (tornei + casual VALIDATED).

        ELO è path-dependent: i match di torneo e i casual vanno fusi in UN
        unico ordine cronologico (``ended_at``, poi ``id``). Resetta SOLO il
        pool ELO_GLOBAL: NON tocca ``User.elo_rating`` né il pool competitivo.

        Pure/in-transaction come ``recalculate_all_elo``: il caller gestisce la
        transazione.

        Returns:
            dict: counters ``{processed, skipped, total}``.
        """
        from models.status_enum import MatchStatus
        from models.individual_match.models import IndividualMatch

        # 1. Drop SOLO il pool globale (PlayerRating + history).
        db.session.query(PlayerRating).filter_by(
            rating_system=RatingSystem.ELO_GLOBAL
        ).delete()
        db.session.query(MatchRatingHistory).filter_by(
            rating_system=RatingSystem.ELO_GLOBAL
        ).delete()
        db.session.flush()

        # 2. Carica torneo (finished) + casual (VALIDATED), entrambi con un
        #    marcatore di sorgente, e fondili per ordine cronologico.
        tournament = [
            ("match", m)
            for m in Match.query.filter(
                Match.status.in_(MatchStatus.finished_values())
            ).all()
        ]
        casual = [
            ("individual", im)
            for im in IndividualMatch.query.filter(
                IndividualMatch.status == MatchStatus.CONFIRMED_BY_BOTH
            ).all()
        ]

        def _sort_key(item):
            _kind, obj = item
            # ended_at può essere None su dati vecchi: spingili in coda con un
            # sentinel alto ma deterministico, poi ordina per id.
            return (obj.ended_at is None, obj.ended_at, obj.id)

        merged = sorted(tournament + casual, key=_sort_key)

        categorie = RatingEligibility.build_index([m for _kind, m in tournament])

        processed = 0
        skipped = 0
        for kind, obj in merged:
            if kind == "match":
                if not RatingEligibility.counts_for_rating(obj, categorie):
                    skipped += 1
                    continue
                RatingCalculationService.process_match_result(
                    obj, systems=[RatingSystem.ELO_GLOBAL]
                )
            else:  # individual (casual) — forfait già esclusi (solo VALIDATED)
                RatingCalculationService.process_individual_match_result(obj)
            processed += 1

        return {"processed": processed, "skipped": skipped, "total": len(merged)}

    @staticmethod
    def revert_match_result(match: Match) -> None:
        """Annulla i delta di rating applicati per questo match.

        Per ogni record di history: sottrae il delta dal rating corrente e
        decrementa robustness, poi elimina il record. Usato quando un match
        completato viene riaperto/resettato o prima di eliminarlo.

        Path-dependency: sottrarre il delta (anziché ripristinare il valore
        assoluto) è esatto se il match è l'ultimo processato per quei giocatori
        — il caso tipico di un reset. Per un match "in mezzo" i rating restano
        approssimati finché non si rilancia recalc_elo.
        """
        from models.user.models import User

        records = MatchRatingHistory.query.filter_by(match_id=match.id).all()
        if not records:
            return

        for rec in records:
            rating_obj = PlayerRating.get_user_rating(rec.user_id, rec.rating_system)
            if rating_obj:
                rating_obj.rating_value = rating_obj.rating_value - rec.delta
                rating_obj.robustness = max(
                    0, rating_obj.robustness - rec.robustness_increment
                )
                db.session.add(rating_obj)
                if rec.rating_system == RatingSystem.ELO:
                    user = db.session.get(User, rec.user_id)
                    if user:
                        user.elo_rating = rating_obj.rating_value
                        db.session.add(user)
            db.session.delete(rec)

        logger.info(
            f"Revert rating per match {match.id}: annullati {len(records)} delta."
        )

    @staticmethod
    def _process_standard_match(
        match: Match, rating_system: RatingSystem = RatingSystem.ELO
    ) -> None:
        """Handle standard 1v1 (tournament) match per il pool indicato."""
        RatingCalculationService._process_two_player(
            match.player1_id,
            match.player2_id,
            match.player1_score or 0,
            match.player2_score or 0,
            rating_system,
            match_id=match.id,
        )

    @staticmethod
    def _process_two_player(
        player1_id: Optional[int],
        player2_id: Optional[int],
        rack1: int,
        rack2: int,
        rating_system: RatingSystem,
        match_id: Optional[int] = None,
        individual_match_id: Optional[int] = None,
    ) -> None:
        """Aggiornamento 1v1 a partire dai **rack**, non da chi ha vinto.

        Le regole stanno in `rack_engine`, che non conosce il database; qui
        c'è solo la persistenza. Prima di ADR-052 questa funzione leggeva
        `winner_id`, e un 7-0 valeva quanto un 7-6.

        `robustness` conta i **rack**: è la *robustness*, e regola la
        sensibilità dell'aggiornamento.
        """
        from . import rack_engine

        source = match_id if match_id is not None else individual_match_id
        if not player1_id or not player2_id:
            logger.warning(
                f"Match {source} missing players, skipping rating update "
                f"({rating_system.value})."
            )
            return
        if rack1 + rack2 <= 0:
            logger.info(
                f"Match {source}: nessun rack giocato, nessun aggiornamento "
                f"({rating_system.value})."
            )
            return

        obj1 = PlayerRating.get_user_rating(player1_id, rating_system)
        obj2 = PlayerRating.get_user_rating(player2_id, rating_system)
        r1 = obj1.rating_value if obj1 else rack_engine.PARTENZA
        r2 = obj2.rating_value if obj2 else rack_engine.PARTENZA
        giocati1 = obj1.robustness if obj1 else 0
        giocati2 = obj2.robustness if obj2 else 0

        delta = rack_engine.variazione(r1, r2, rack1, rack2, giocati1, giocati2)
        totale = rack1 + rack2

        for user_id, vecchio, nuovo_valore, obj in (
            (player1_id, r1, r1 + delta, obj1),
            (player2_id, r2, r2 - delta, obj2),
        ):
            RatingCalculationService._update_player_rating_db(
                user_id,
                vecchio,
                nuovo_valore,
                obj,
                rating_system,
                match_id=match_id,
                individual_match_id=individual_match_id,
                robustness_increment=totale,
            )

        logger.info(
            "Rating %s, match %s: %s-%s → delta %+.2f",
            rating_system.value,
            source,
            rack1,
            rack2,
            delta,
        )

    @staticmethod
    def _process_trio_match(
        trio: TrioMatch,
        match_id: int,
        rating_system: RatingSystem = RatingSystem.ELO,
    ) -> None:
        """Il trio si scompone nei suoi tre confronti veri (ADR-052).

        Un trio è un girone interno: i tre si affrontano a coppie, a turno,
        mentre il terzo aspetta. `TrioRack` registra per **ogni rack** chi
        erano i due al tavolo (`player1_id`, `player2_id`) e chi ha vinto,
        quindi la scomposizione non va indovinata: sta nei dati.

        Prima di ADR-052 qui si collassava tutto in un 1 / 0.5 / 0 per
        giocatore, confrontato con la media dei rating degli altri due — un
        avversario che non esiste. Ora ogni coppia è un confronto a sé, con i
        suoi rack, e l'aggiornamento conserva il punteggio come in una
        partita normale.

        Un trio **senza** righe `TrioRack` non si può scomporre: sono dati
        vecchi, e si saltano dicendolo. Inventare una ripartizione dei rack
        complessivi sarebbe peggio di non contarli.
        """
        from models.match.models import TrioRack

        racks = TrioRack.query.filter_by(trio_match_id=trio.id, is_deleted=False).all()
        if not racks:
            logger.info(
                "Trio %s senza righe TrioRack: non scomponibile, saltato (%s).",
                trio.id,
                rating_system.value,
            )
            return

        # (id_minore, id_maggiore) -> [vinti dal minore, vinti dal maggiore]
        scontri: Dict[Tuple[int, int], List[int]] = {}
        for rack in racks:
            a, b = rack.player1_id, rack.player2_id
            if a is None or b is None or rack.winner_id is None:
                continue
            coppia = (a, b) if a < b else (b, a)
            conteggio = scontri.setdefault(coppia, [0, 0])
            conteggio[0 if rack.winner_id == coppia[0] else 1] += 1

        # I tre confronti si calcolano tutti sui rating **d'inizio trio** e si
        # applicano insieme. Due ragioni: `match_rating_history` ammette una
        # sola riga per (partita, giocatore, sistema) — tre aggiornamenti
        # separati la violerebbero — e così sparisce la dipendenza dall'ordine
        # in cui si guardano le coppie, che non ha alcun significato.
        from . import rack_engine

        partecipanti = sorted({pid for coppia in scontri for pid in coppia})
        oggetti = {
            pid: PlayerRating.get_user_rating(pid, rating_system)
            for pid in partecipanti
        }
        rating = {
            pid: (obj.rating_value if obj else rack_engine.PARTENZA)
            for pid, obj in oggetti.items()
        }
        giocati = {pid: (obj.robustness if obj else 0) for pid, obj in oggetti.items()}
        delta = {pid: 0.0 for pid in partecipanti}
        rack_del_giocatore = {pid: 0 for pid in partecipanti}

        for (p1, p2), (vinti1, vinti2) in sorted(scontri.items()):
            variazione = rack_engine.variazione(
                rating[p1], rating[p2], vinti1, vinti2, giocati[p1], giocati[p2]
            )
            delta[p1] += variazione
            delta[p2] -= variazione
            rack_del_giocatore[p1] += vinti1 + vinti2
            rack_del_giocatore[p2] += vinti1 + vinti2

        for pid in partecipanti:
            RatingCalculationService._update_player_rating_db(
                pid,
                rating[pid],
                rating[pid] + delta[pid],
                oggetti[pid],
                rating_system,
                match_id=match_id,
                robustness_increment=rack_del_giocatore[pid],
            )

        logger.info(
            "Trio %s (%s): %d confronti, delta %s",
            trio.id,
            rating_system.value,
            len(scontri),
            {pid: round(d, 2) for pid, d in delta.items()},
        )

    @staticmethod
    def _update_player_rating_db(
        user_id: int,
        old_val: float,
        new_val: float,
        exist_obj: Optional[PlayerRating],
        rating_system: RatingSystem,
        match_id: Optional[int] = None,
        individual_match_id: Optional[int] = None,
        robustness_increment: int = 1,
    ) -> None:
        """Salva il rating, registra la history e (solo ELO competitivo) sincronizza
        User.elo_rating.

        Vincolo display-only: per ELO_GLOBAL NON si scrive `User.elo_rating`, che
        resta la fonte autorevole del solo pool competitivo (categoria/handicap).
        """
        # Update/Create PlayerRating per il pool indicato
        if exist_obj:
            exist_obj.update_rating(new_val, robustness_increment)
        else:
            new_rating = PlayerRating(
                user_id=user_id,
                rating_system=rating_system,
                rating_value=new_val,
                robustness=robustness_increment,
            )
            db.session.add(new_rating)

        # Record history per idempotenza + revert (sorgente polimorfa)
        db.session.add(
            MatchRatingHistory(
                match_id=match_id,
                individual_match_id=individual_match_id,
                user_id=user_id,
                rating_system=rating_system,
                old_rating=old_val,
                new_rating=new_val,
                delta=new_val - old_val,
                robustness_increment=robustness_increment,
            )
        )

        # Sync su User SOLO per l'ELO competitivo (display-only per ELO_GLOBAL
        # e per il pool RACK, che non è ancora mostrato da nessuna parte)
        if rating_system == RatingSystem.ELO:
            from models.user.models import User

            user = db.session.get(User, user_id)
            if user:
                # Colonna intera: il rating vive in virgola mobile
                # su PlayerRating, qui si mostra arrotondato.
                user.elo_rating = int(round(new_val))
                db.session.add(user)
