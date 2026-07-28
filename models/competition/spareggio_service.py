"""
Module: models/competition/spareggio_service.py
Purpose: Handle spot shot rally (SSR) tiebreakers for top 3 positions
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, TypedDict
from sqlalchemy import func
from models.base import db
from models.classification.models import RoundClassification, GaraClassification
from models.match.models import Match
from models.transaction.manager import transactional

if TYPE_CHECKING:
    from models.competition.models import Gara


class TiebreakerGroup(TypedDict):
    """A group of players tied for the same position."""

    position: int  # Starting position (1, 2, or 3)
    rack_totali: int  # Shared rack count
    players: List[Dict]  # List of {user_id, username, current_ssr_score}


class SpareggioService:
    """Service for detecting and resolving tiebreakers in top 3 positions."""

    @staticmethod
    def _group_by_classification(gara: Gara) -> Tuple[List, Dict]:
        """Carica le RoundClassification del final round e le raggruppa per la
        chiave di parimerito appropriata al ``classification_system`` della gara.

        Una "chiave di parimerito" identifica univocamente lo stato classifica
        di un giocatore: due giocatori che condividono la stessa chiave sono
        parimerito (e candidati a SSR se nelle prime ``tiebreaker_until_position``
        posizioni).

        - **WINS** (default), **POSITION**: chiave ``(matches_won, rack_difference)``.
          Due giocatori sono parimerito solo se *entrambi* coincidono. Bug B20:
          prima il servizio raggruppava sempre per ``rack_difference`` solo,
          generando falsi parimerito quando la gara è WINS e due player hanno
          stesso rack_diff ma diversi matches_won.
        - **RACK**: chiave ``rack_difference`` (intero), come prima.

        Returns:
            Tuple ``(sorted_keys, groups_by_key)``. Le keys sono ordinate
            descending; per le tuple WINS lessicograficamente ``(wins, diff)``.
            Lista vuota se non ci sono classifications per il final round.
        """
        classification_system = (gara.classification_system or "WINS").upper()
        final_round = SpareggioService._get_effective_final_round(gara)
        query = db.session.query(RoundClassification).filter_by(
            gara_id=gara.id, round_number=final_round
        )
        if classification_system == "RACK":
            # `ranking_rack_value` in SQL: `racks_won` con fallback su
            # `rack_difference` per le righe scritte prima della separazione
            # delle due colonne (migration 20260728).
            rack_total = func.coalesce(
                RoundClassification.racks_won, RoundClassification.rack_difference
            )
            classifications = query.order_by(rack_total.desc()).all()
        else:
            classifications = query.order_by(
                RoundClassification.matches_won.desc(),
                RoundClassification.rack_difference.desc(),
            ).all()

        if not classifications:
            return [], {}

        def classification_key(c):
            if classification_system == "RACK":
                return c.ranking_rack_value
            return (c.matches_won, c.rack_difference)

        groups_by_key: Dict = {}
        for c in classifications:
            key = classification_key(c)
            groups_by_key.setdefault(key, []).append(c)

        sorted_keys = sorted(groups_by_key.keys(), reverse=True)
        return sorted_keys, groups_by_key

    @staticmethod
    def _get_effective_final_round(gara: Gara) -> int:
        """Get the effective final round for classification.

        For Random strategy, all rounds are created at startup so
        gara.current_round may lag behind. Use max(Match.round_number) instead.
        For other strategies, fall back to gara.current_round or gara.rounds_count.
        """
        max_round = (
            db.session.query(func.max(Match.round_number))
            .filter(Match.gara_id == gara.id)
            .scalar()
        )
        return max_round or gara.current_round or gara.rounds_count

    @staticmethod
    def detect_tiebreakers(gara_id: int) -> List[TiebreakerGroup]:
        """
        Detect tiebreaker groups in the top 3 positions.

        A tiebreaker is needed when multiple players have the same rack count
        and at least one of them would be in the top 3.

        Args:
            gara_id: ID of the gara

        Returns:
            List of TiebreakerGroup dictionaries, empty if no tiebreakers needed
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return []

        # Check if tiebreaker is enabled for this gara
        if not gara.tiebreaker_enabled:
            return []

        # Get the position limit for tiebreakers (default to 3 if not set)
        tiebreaker_limit = gara.tiebreaker_until_position or 3

        sorted_keys, groups_by_key = SpareggioService._group_by_classification(gara)
        if not sorted_keys:
            return []

        # Find groups that affect top 3 positions
        tiebreaker_groups: List[TiebreakerGroup] = []
        current_position = 1

        for key in sorted_keys:
            group = groups_by_key[key]
            # rack_totali nel TiebreakerGroup tiene il rack_difference comune
            # del gruppo (per WINS è il secondo elemento della tuple, per RACK
            # è la chiave intera). Mantenuto per compat col template.
            rack_count = key[1] if isinstance(key, tuple) else key

            # Check if this group includes any position within tiebreaker limit
            if current_position <= tiebreaker_limit and len(group) > 1:
                # If the group spans into top positions, it needs a tiebreaker
                if current_position <= tiebreaker_limit:
                    # Check existing SSR scores to see if already resolved
                    existing_gara_class = (
                        db.session.query(GaraClassification)
                        .filter(
                            GaraClassification.gara_id == gara_id,
                            GaraClassification.user_id.in_([c.user_id for c in group]),
                        )
                        .all()
                    )
                    ssr_scores = {
                        gc.user_id: gc.spot_shot_wins for gc in existing_gara_class
                    }

                    # Build player list with SSR scores
                    players = []
                    for c in group:
                        user = c.user
                        players.append(
                            {
                                "user_id": c.user_id,
                                "username": (
                                    user.username if user else f"User {c.user_id}"
                                ),
                                "current_ssr_score": ssr_scores.get(
                                    c.user_id
                                ),  # None if not entered
                            }
                        )

                    # Check if this tiebreaker is already resolved
                    # All players must have a score AND all scores must be different
                    # 0 is a valid score, None means not entered
                    scores = [p["current_ssr_score"] for p in players]
                    all_scores_entered = all(s is not None for s in scores)
                    all_scores_different = len(scores) == len(set(scores))
                    is_resolved = all_scores_entered and all_scores_different

                    if not is_resolved:
                        tiebreaker_groups.append(
                            {
                                "position": current_position,
                                "rack_totali": rack_count,
                                "players": players,
                            }
                        )

            current_position += len(group)

            # Stop if we've passed the tiebreaker position limit
            if current_position > tiebreaker_limit:
                break

        return tiebreaker_groups

    @staticmethod
    def has_unresolved_tiebreakers(gara_id: int) -> bool:
        """
        Check if there are any unresolved tiebreakers in top 3.

        Args:
            gara_id: ID of the gara

        Returns:
            True if there are unresolved tiebreakers
        """
        return len(SpareggioService.detect_tiebreakers(gara_id)) > 0

    @staticmethod
    def get_all_ssr_groups(gara_id: int) -> List[TiebreakerGroup]:
        """
        Get ALL tiebreaker groups (resolved and unresolved) for display.

        Unlike detect_tiebreakers() which only returns unresolved groups,
        this method returns all groups for showing SSR scores in the UI.

        Args:
            gara_id: ID of the gara

        Returns:
            List of TiebreakerGroup dictionaries (both resolved and unresolved)
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return []

        # Check if tiebreaker is enabled for this gara
        if not gara.tiebreaker_enabled:
            return []

        # Get the position limit for tiebreakers (default to 3 if not set)
        tiebreaker_limit = gara.tiebreaker_until_position or 3

        sorted_keys, groups_by_key = SpareggioService._group_by_classification(gara)
        if not sorted_keys:
            return []

        # Find ALL groups that affect top 3 positions (resolved or not)
        all_groups: List[TiebreakerGroup] = []
        current_position = 1

        for key in sorted_keys:
            group = groups_by_key[key]
            # rack_totali è il rack_difference comune del gruppo (per WINS è il
            # secondo elemento della tuple, per RACK è la chiave intera).
            rack_count = key[1] if isinstance(key, tuple) else key

            # Check if this group includes any position within tiebreaker
            # limit AND has multiple players
            if current_position <= tiebreaker_limit and len(group) > 1:
                # Get existing SSR scores
                existing_gara_class = (
                    db.session.query(GaraClassification)
                    .filter(
                        GaraClassification.gara_id == gara_id,
                        GaraClassification.user_id.in_([c.user_id for c in group]),
                    )
                    .all()
                )
                ssr_scores = {
                    gc.user_id: gc.spot_shot_wins for gc in existing_gara_class
                }

                # Build player list with SSR scores
                players = []
                for c in group:
                    user = c.user
                    players.append(
                        {
                            "user_id": c.user_id,
                            "username": user.username if user else f"User {c.user_id}",
                            "current_ssr_score": ssr_scores.get(
                                c.user_id
                            ),  # None if not entered
                        }
                    )

                all_groups.append(
                    {
                        "position": current_position,
                        "rack_totali": rack_count,
                        "players": players,
                    }
                )

            current_position += len(group)

            # Stop if we've passed the tiebreaker position limit
            if current_position > tiebreaker_limit:
                break

        return all_groups

    @staticmethod
    def is_group_resolved(group: TiebreakerGroup) -> bool:
        """
        Check if a single tiebreaker group is resolved.

        A group is resolved when all SSR scores are different (0 is valid).
        """
        scores = [p["current_ssr_score"] for p in group["players"]]
        return len(scores) == len(set(scores))

    @staticmethod
    def validate_ssr_scores_for_group(scores: Dict[int, int]) -> Tuple[bool, str]:
        """
        Validate SSR scores for a SINGLE tiebreaker group.

        Scores must be unique only within this group - different groups
        can have overlapping scores.

        Args:
            scores: Dict mapping user_id to SSR score for players in ONE group

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not scores:
            return False, "Nessun punteggio fornito"

        # Check all scores are non-negative integers
        for score in scores.values():
            if not isinstance(score, int) or score < 0:
                return False, "I punteggi devono essere numeri interi non negativi"

        # Check all scores are different within the group
        score_values = list(scores.values())
        if len(score_values) != len(set(score_values)):
            return False, "I punteggi devono essere diversi all'interno del gruppo"

        return True, ""

    @staticmethod
    def validate_ssr_scores(scores: Dict[int, int]) -> Tuple[bool, str]:
        """
        Validate SSR scores for a tiebreaker group.

        Args:
            scores: Dict mapping user_id to SSR score

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not scores:
            return False, "Nessun punteggio inserito"

        # Check all scores are non-negative integers
        for score in scores.values():
            if not isinstance(score, int) or score < 0:
                return (
                    False,
                    "Tutti i punteggi devono essere numeri interi non negativi",
                )

        # Check all scores are different
        score_values = list(scores.values())
        if len(score_values) != len(set(score_values)):
            return (
                False,
                "I punteggi devono essere tutti diversi per risolvere il parimerito",
            )

        return True, ""

    @staticmethod
    @transactional(domain="competition")
    def save_ssr_scores(gara_id: int, scores: Dict[int, int]) -> Tuple[bool, str]:
        """
        Save SSR scores for tiebreaker resolution.

        Args:
            gara_id: ID of the gara
            scores: Dict mapping user_id to SSR score

        Returns:
            Tuple of (success, message)
        """
        from models.competition.models import Gara

        # Validate scores
        is_valid, error = SpareggioService.validate_ssr_scores(scores)
        if not is_valid:
            return False, error

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata"

        # Get or create GaraClassification entries for all players
        # First, ensure all players in the tiebreaker have GaraClassification entries
        final_round = SpareggioService._get_effective_final_round(gara)

        for user_id, ssr_score in scores.items():
            # Get round classification to get stats
            round_class = (
                db.session.query(RoundClassification)
                .filter_by(gara_id=gara_id, round_number=final_round, user_id=user_id)
                .first()
            )

            if not round_class:
                continue

            # Get or create gara classification
            gara_class = (
                db.session.query(GaraClassification)
                .filter_by(gara_id=gara_id, user_id=user_id)
                .first()
            )

            if not gara_class:
                gara_class = GaraClassification(
                    gara_id=gara_id,
                    user_id=user_id,
                    position=round_class.position,
                    matches_won=round_class.matches_won,
                    racks_won=round_class.ranking_rack_value,
                    rack_difference=round_class.rack_difference or 0,
                )
                db.session.add(gara_class)

            # Update SSR score
            gara_class.spot_shot_wins = ssr_score
            gara_class.tiebreaker_resolved = True

        return True, "Punteggi spareggio salvati con successo"

    @staticmethod
    @transactional(domain="competition")
    def save_ssr_scores_for_group(
        gara_id: int, group_position: int, scores: Dict[int, int]
    ) -> Tuple[bool, str]:
        """
        Save SSR scores for a SINGLE tiebreaker group.

        This validates scores only within the specified group, allowing
        different groups to have overlapping SSR values.

        Args:
            gara_id: ID of the gara
            group_position: Position of the tiebreaker group (1, 2, or 3)
            scores: Dict mapping user_id to SSR score for this group

        Returns:
            Tuple of (success, message)
        """
        from models.competition.models import Gara

        # Validate scores for this group
        is_valid, error = SpareggioService.validate_ssr_scores_for_group(scores)
        if not is_valid:
            return False, error

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata"

        # Verify the group exists and contains the specified user_ids
        all_groups = SpareggioService.get_all_ssr_groups(gara_id)
        target_group: Optional[TiebreakerGroup] = None
        for group in all_groups:
            if group["position"] == group_position:
                target_group = group
                break

        if not target_group:
            return (
                False,
                f"Gruppo di parimerito alla posizione {group_position} non trovato",
            )

        # Verify all user_ids in scores belong to this group
        group_user_ids = {p["user_id"] for p in target_group["players"]}
        for user_id in scores.keys():
            if user_id not in group_user_ids:
                return False, f"Giocatore {user_id} non appartiene a questo gruppo"

        # Get final round for stats lookup
        final_round = SpareggioService._get_effective_final_round(gara)

        # Save scores for this group
        for user_id, ssr_score in scores.items():
            # Get round classification to get stats
            round_class = (
                db.session.query(RoundClassification)
                .filter_by(gara_id=gara_id, round_number=final_round, user_id=user_id)
                .first()
            )

            if not round_class:
                continue

            # Get or create gara classification
            gara_class = (
                db.session.query(GaraClassification)
                .filter_by(gara_id=gara_id, user_id=user_id)
                .first()
            )

            if not gara_class:
                gara_class = GaraClassification(
                    gara_id=gara_id,
                    user_id=user_id,
                    position=round_class.position,
                    matches_won=round_class.matches_won,
                    racks_won=round_class.ranking_rack_value,
                    rack_difference=round_class.rack_difference or 0,
                )
                db.session.add(gara_class)

            # Update SSR score
            gara_class.spot_shot_wins = ssr_score
            gara_class.tiebreaker_resolved = True

        return True, f"Punteggi SSR per posizione {group_position} salvati"

    @staticmethod
    def clear_ssr_scores(gara_id: int) -> int:
        """Azzera i punteggi di spareggio di una gara. Restituisce le righe toccate.

        Serve all'annullamento della fase SSR: tornando a `playing` il director
        può modificare i match, quindi la classifica — e con essa chi è a pari
        merito — può cambiare. Punteggi sopravvissuti si riferirebbero a una
        classifica che non esiste più, e `finalize_classification` li userebbe
        senza modo di accorgersene.

        Le righe `GaraClassification` non vengono cancellate: contengono anche
        posizione e statistiche, che il prossimo ricalcolo riscrive.

        Senza `@transactional`: è sempre chiamato dentro un contesto
        transazionale (`StateService.cancel_ssr`), e annidare i decoratori
        provoca rollback del savepoint esterno.
        """
        rows = db.session.query(GaraClassification).filter_by(gara_id=gara_id).all()
        for row in rows:
            row.spot_shot_wins = 0
            row.tiebreaker_resolved = False
        return len(rows)

    @staticmethod
    @transactional(domain="competition")
    def finalize_classification(gara_id: int) -> Tuple[bool, str]:
        """
        Finalize classification after SSR scores are saved.

        Recalculates positions based on (rack_totali DESC, spot_shot_wins DESC).

        Args:
            gara_id: ID of the gara

        Returns:
            Tuple of (success, message)
        """
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if not gara:
            return False, "Gara non trovata"

        final_round = SpareggioService._get_effective_final_round(gara)

        # Expire all to ensure we get fresh data from DB
        db.session.expire_all()

        # Get all round classifications.
        # `order_by(position)` non è cosmetico: il sort qui sotto è stabile e
        # non ha criteri oltre lo SSR, quindi i parimerito che lo SSR non
        # risolve (o le gare con tiebreaker disabilitato) ereditano l'ordine di
        # questa lista. Senza order_by sarebbe l'ordine di rowid, cioè le
        # posizioni di quando le righe furono create la prima volta, e il
        # parimerito risolto per posizione di partenza andrebbe perso proprio
        # nella classifica finale.
        round_classifications = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara_id, round_number=final_round)
            .order_by(RoundClassification.position)
            .all()
        )

        # Build a map for quick lookup
        round_class_map = {rc.user_id: rc for rc in round_classifications}

        # Get existing gara classifications (with SSR scores)
        existing_gara_class = {
            gc.user_id: gc
            for gc in db.session.query(GaraClassification)
            .filter_by(gara_id=gara_id)
            .all()
        }

        # Build combined data for sorting
        player_data = []
        for rc in round_classifications:
            gc = existing_gara_class.get(rc.user_id)
            # SSR score: None means not entered, treat as -1 for sorting (lowest)
            ssr_score = (
                gc.spot_shot_wins if gc and gc.spot_shot_wins is not None else -1
            )
            player_data.append(
                {
                    "user_id": rc.user_id,
                    # Criterio di classifica della gara: totale rack se RACK,
                    # differenza altrove. La scelta è dentro
                    # `ranking_rack_value`, unico punto che conosce la
                    # configurazione.
                    "rack_totali": rc.ranking_rack_value,
                    "rack_difference": rc.rack_difference or 0,
                    "ssr_score": ssr_score,
                    "matches_won": rc.matches_won,
                }
            )

        # La chiave di ordinamento dipende dal classification_system, coerente
        # con _group_by_classification (che definisce quali giocatori sono a
        # pari merito). Lo SSR è il tiebreaker DECISIVO entro gruppi a pari
        # merito, quindi va sempre per ultimo.
        # - RACK: (rack totali DESC, ssr_score DESC)
        # - WINS / POSITION (default): (matches_won DESC, rack_difference DESC,
        #   ssr_score DESC). Senza matches_won il vincitore reale per vittorie
        #   veniva scavalcato (bug high).
        # -1 (SSR non inserito) ordina per ultimo a pari chiave primaria.
        classification_system = (gara.classification_system or "WINS").upper()
        if classification_system == "RACK":
            player_data.sort(key=lambda x: (-x["rack_totali"], -x["ssr_score"]))
        else:
            player_data.sort(
                key=lambda x: (-x["matches_won"], -x["rack_totali"], -x["ssr_score"])
            )

        # Update/create GaraClassification and RoundClassification with
        # correct positions
        for position, data in enumerate(player_data, 1):
            gara_class = existing_gara_class.get(data["user_id"])

            if not gara_class:
                gara_class = GaraClassification(
                    gara_id=gara_id,
                    user_id=data["user_id"],
                    racks_won=data["rack_totali"],
                    rack_difference=data["rack_difference"],
                    matches_won=data["matches_won"],
                )
                db.session.add(gara_class)

            gara_class.position = position

            # Also update RoundClassification position so UI shows correct ordering
            round_class = round_class_map.get(data["user_id"])
            if round_class:
                round_class.position = position

        return True, "Classifica finale aggiornata"
