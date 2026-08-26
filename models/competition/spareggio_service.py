"""
Module: models/competition/spareggio_service.py
Purpose: Handle spot shot rally (SSR) tiebreakers for top 3 positions
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple, TypedDict
from sqlalchemy import func
from models.base import db
from models.classification.bracket_standings import bracket_positions
from models.classification.models import RoundClassification, GaraClassification
from models.classification.strategies.position_strategies import NO_BRACKET_POSITION
from models.match.models import Match
from models.transaction.manager import transactional

if TYPE_CHECKING:
    from models.competition.models import Gara

logger = logging.getLogger(__name__)


class TiebreakerGroup(TypedDict):
    """A group of players tied for the same position."""

    position: int  # Starting position (1, 2, or 3)
    rack_totali: int  # Shared rack count
    players: List[Dict]  # List of {user_id, username, current_ssr_score}
    # Quanti punteggi in cima al gruppo devono essere strettamente separati
    # perché lo spareggio sia risolto (vedi positions_to_discriminate).
    needs_distinct_top: int


class SpareggioService:
    """Service for detecting and resolving tiebreakers in top 3 positions."""

    # ------------------------------------------------------------------
    # Regola di risoluzione di un gruppo di parimerito
    # ------------------------------------------------------------------

    @staticmethod
    def tiebreakers_apply_to(gara) -> bool:
        """Se in questa gara lo spareggio ha senso.

        Nel sistema POSITION **no**, ed è una scelta di prodotto: le posizioni
        vengono a bande di pari merito perché chi esce allo stesso turno ha
        fatto lo stesso percorso (i quattro quartifinalisti sono tutti 5°).
        Proporre uno spot shot rally per separarli significherebbe inventare
        una gerarchia che il tabellone non ha prodotto, e nessuno l'ha chiesta.

        Vale per tutte le porte d'ingresso dello spareggio, non solo per la
        schermata: il vincolo sta qui, non nella UI.
        """
        if not getattr(gara, "tiebreaker_enabled", False):
            return False
        return (
            getattr(gara, "classification_system", None) or "WINS"
        ).upper() != "POSITION"

    @staticmethod
    def positions_to_discriminate(
        group_size: int, group_position: int, tiebreaker_limit: int
    ) -> int:
        """Quanti punteggi SSR in cima al gruppo devono essere distinti.

        Lo spareggio serve a decidere le posizioni fino a
        ``tiebreaker_until_position``: sotto quella soglia il parimerito è
        legittimo e non va forzato. Un gruppo che parte dalla posizione ``p``
        con ``n`` giocatori occupa le posizioni ``p .. p+n-1``, di cui solo
        ``tiebreaker_limit - p + 1`` sono contese; per separarle basta che i
        primi ``k`` punteggi siano strettamente decrescenti (il ``k+1``-esimo
        incluso, altrimenti la ``k``-esima posizione resterebbe ambigua).

        Esempio dell'issue #63: gruppo di 4 alla posizione 3 con limite 3 →
        k = 1. Basta un vincitore netto; gli altri tre possono restare a pari
        punteggio, anche tutti a 0.
        """
        if group_size < 2:
            return 0
        contested = tiebreaker_limit - group_position + 1
        return max(0, min(group_size - 1, contested))

    @staticmethod
    def draw_order_map(gara_id: int) -> Dict[int, int]:
        """Mappa user_id -> ordine di estrazione (1-based).

        `Inscription.initial_order` è la proiezione della classifica di
        partenza (turno 0) mostrata al giocatore come "Ordine sorteggio": è il
        criterio con cui elencare i parimerito nella classifica finale
        (issue #67). Chi ne è privo (iscritto dopo l'avvio) ordina in fondo.
        """
        from models.competition.models import Inscription

        rows = (
            db.session.query(Inscription.user_id, Inscription.initial_order)
            .filter(Inscription.gara_id == gara_id)
            .all()
        )
        return {user_id: order for user_id, order in rows if order is not None}

    @staticmethod
    def assign_shared_positions(
        ordered: List[Dict], merit_key
    ) -> List[Tuple[int, Dict]]:
        """Assegna le posizioni "competition ranking" a una lista già ordinata.

        Chi condivide la chiave di merito condivide la posizione, e la
        posizione successiva salta di tanti quanti sono i parimerito
        (1, 2, 2, 4). Prima le posizioni erano sempre progressive: due
        giocatori con gli stessi punti, che nessuno spareggio doveva
        separare, comparivano come 7° e 8° (issue #67).
        """
        result: List[Tuple[int, Dict]] = []
        position = 1
        index = 0
        while index < len(ordered):
            key = merit_key(ordered[index])
            group = [ordered[index]]
            probe = index + 1
            while probe < len(ordered) and merit_key(ordered[probe]) == key:
                group.append(ordered[probe])
                probe += 1
            for item in group:
                result.append((position, item))
            position += len(group)
            index = probe
        return result

    @staticmethod
    def scores_resolve_group(
        scores: List[Optional[int]], needs_distinct_top: int
    ) -> bool:
        """True se i punteggi separano i primi ``needs_distinct_top`` posti.

        Richiede che ogni giocatore abbia un punteggio (0 è valido, ``None``
        significa "non inserito") e che i primi ``needs_distinct_top``
        punteggi in ordine decrescente siano strettamente maggiori del
        successivo. I pari merito oltre quella soglia sono ammessi.
        """
        if any(s is None for s in scores):
            return False
        ordered = sorted((s for s in scores if s is not None), reverse=True)
        return all(
            ordered[i] > ordered[i + 1]
            for i in range(min(needs_distinct_top, len(ordered) - 1))
        )

    @staticmethod
    def _group_by_classification(gara: Gara) -> Tuple[List, Dict]:
        """Carica le RoundClassification del final round e le raggruppa per la
        chiave di parimerito appropriata al ``classification_system`` della gara.

        Una "chiave di parimerito" identifica univocamente lo stato classifica
        di un giocatore: due giocatori che condividono la stessa chiave sono
        parimerito (e candidati a SSR se nelle prime ``tiebreaker_until_position``
        posizioni).

        - **WINS** (default): chiave ``(matches_won, rack_difference)``.
          Due giocatori sono parimerito solo se *entrambi* coincidono. Bug B20:
          prima il servizio raggruppava sempre per ``rack_difference`` solo,
          generando falsi parimerito quando la gara è WINS e due player hanno
          stesso rack_diff ma diversi matches_won.
        - **RACK**: chiave ``rack_difference`` (intero), come prima.
        - **POSITION**: non arriva mai qui, perché lo spareggio è spento
          (``tiebreakers_apply_to``): i pari merito del tabellone sono l'esito
          voluto e non vanno sciolti.

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

        # Spareggio spento per la gara, o sistema POSITION (dove i pari
        # merito sono l'esito voluto): vedi `tiebreakers_apply_to`.
        if not SpareggioService.tiebreakers_apply_to(gara):
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

                    # Il gruppo è risolto quando tutti hanno un punteggio (0 è
                    # valido, None = non inserito) e i punteggi separano le
                    # sole posizioni contese. I pari merito oltre
                    # tiebreaker_until_position sono legittimi (issue #63).
                    needed = SpareggioService.positions_to_discriminate(
                        len(group), current_position, tiebreaker_limit
                    )
                    scores = [p["current_ssr_score"] for p in players]
                    is_resolved = SpareggioService.scores_resolve_group(scores, needed)

                    if not is_resolved:
                        tiebreaker_groups.append(
                            {
                                "position": current_position,
                                "rack_totali": rack_count,
                                "players": players,
                                "needs_distinct_top": needed,
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

        # Spareggio spento per la gara, o sistema POSITION (dove i pari
        # merito sono l'esito voluto): vedi `tiebreakers_apply_to`.
        if not SpareggioService.tiebreakers_apply_to(gara):
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
                        "needs_distinct_top": (
                            SpareggioService.positions_to_discriminate(
                                len(group), current_position, tiebreaker_limit
                            )
                        ),
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

        Risolto = tutti hanno un punteggio (0 è valido) e i primi
        ``needs_distinct_top`` sono strettamente separati. Sotto la soglia
        dello spareggio i pari merito sono ammessi (issue #63).
        """
        scores = [p["current_ssr_score"] for p in group["players"]]
        needed = group.get("needs_distinct_top", len(scores) - 1)
        return SpareggioService.scores_resolve_group(scores, needed)

    @staticmethod
    def validate_ssr_scores_for_group(
        scores: Dict[int, int], needs_distinct_top: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Validate SSR scores for a SINGLE tiebreaker group.

        Scores must be unique only within this group - different groups
        can have overlapping scores.

        Non tutti i punteggi devono essere diversi: vanno separati solo i
        ``needs_distinct_top`` posti realmente contesi (vedi
        ``positions_to_discriminate``). Chi resta fuori dalle posizioni
        oggetto di spareggio può chiudere a pari punteggio — richiederlo
        costringeva il director a inventare punti (issue #63). Con
        ``needs_distinct_top=None`` si mantiene il comportamento storico
        "tutti diversi".

        Args:
            scores: Dict mapping user_id to SSR score for players in ONE group
            needs_distinct_top: quanti punteggi in cima devono essere distinti

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not scores:
            return False, "Nessun punteggio fornito"

        # Check all scores are non-negative integers
        for score in scores.values():
            if not isinstance(score, int) or score < 0:
                return False, "I punteggi devono essere numeri interi non negativi"

        score_values: List[Optional[int]] = list(scores.values())
        needed = (
            len(score_values) - 1 if needs_distinct_top is None else needs_distinct_top
        )
        if not SpareggioService.scores_resolve_group(score_values, needed):
            if needed <= 1:
                # Stesso testo del check lato client (gara_detail.html,
                # `errorSsrGroupDuplicates`): l'utente può incontrare l'uno o
                # l'altro a seconda di dove scatta la validazione.
                return (
                    False,
                    "Serve un vincitore netto: il punteggio più alto del "
                    "gruppo non può essere condiviso",
                )
            return (
                False,
                f"I primi {needed} punteggi devono essere diversi fra loro "
                f"e più alti degli altri",
            )

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

        # Validazione dopo la risoluzione del gruppo: quanti punteggi devono
        # essere separati dipende da quante posizioni del gruppo cadono entro
        # tiebreaker_until_position (issue #63).
        is_valid, error = SpareggioService.validate_ssr_scores_for_group(
            scores, target_group.get("needs_distinct_top")
        )
        if not is_valid:
            return False, error

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
    def has_recorded_ssr(gara_id: int) -> bool:
        """Questa gara ha uno spareggio davvero registrato?

        Uno zero non conta: sulla colonna è indistinguibile da un'assenza, ed è
        lo stesso criterio con cui `_recorded_spot_shot` rilegge i punteggi.
        """
        return (
            db.session.query(GaraClassification.id)
            .filter(
                GaraClassification.gara_id == gara_id,
                GaraClassification.spot_shot_wins > 0,
            )
            .first()
            is not None
        )

    @staticmethod
    def reapply_final_positions_if_resolved(gara_id: int) -> bool:
        """Rimette l'esito dello spareggio nelle posizioni, dopo un ricalcolo.

        `apply_final_positions` scrive l'ordine finale in `GaraClassification`
        **e** lo rispecchia in `RoundClassification.position` dell'ultimo turno,
        perché è quella la classifica che la pagina della gara mostra.

        Un ricalcolo delle classifiche di turno — riassegnazione di una
        partecipazione (ADR-048), unione di due account, correzione di un
        risultato — riscrive quelle righe da zero, e lo specchio torna
        all'ordine puro del turno: (vittorie, differenza, posizione
        precedente). Lo spareggio scompare dalla vista e ricompare un pari
        merito che era già stato sciolto sul tavolo.

        `calculate_gara_classification` si difende già rileggendo i punteggi
        registrati, ma difende **la sua** tabella: la copia mostrata all'utente
        resta indietro. Successo in produzione sulla gara 38, il 2026-08-26:
        il primo in classifica aveva il punteggio di spareggio più basso.

        Si applica **solo** dove uno spareggio c'è stato davvero. Chiamarla
        sempre significherebbe far passare ogni gara ricalcolata da
        `apply_final_positions`, che assegna posizioni condivise ai pari
        merito: un cambiamento di comportamento per gare che non hanno mai
        avuto uno spareggio, e che nessuno ha chiesto.

        Senza `@transactional`: è chiamata dentro contesti già transazionali, e
        annidare i decoratori provoca il rollback del savepoint esterno (stessa
        ragione di `clear_ssr_scores`).

        Returns:
            True se le posizioni sono state riapplicate.
        """
        if not SpareggioService.has_recorded_ssr(gara_id):
            return False
        SpareggioService.apply_final_positions(gara_id)
        return True

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
        return SpareggioService.apply_final_positions(gara_id)

    @staticmethod
    def effective_final_round(gara: Gara) -> int:
        """Turno finale effettivo della gara (API pubblica).

        Chi legge la classifica finale deve usare lo stesso turno su cui
        `apply_final_positions` scrive: con la strategia Random tutti i turni
        sono creati all'avvio e `gara.current_round` può restare indietro.
        """
        return SpareggioService._get_effective_final_round(gara)

    @staticmethod
    def apply_final_positions(gara_id: int) -> Tuple[bool, str]:
        """Riscrive le posizioni finali della gara (parimerito inclusi).

        Stessa logica di `finalize_classification` ma **senza**
        `@transactional`, per poter essere invocata da chi è già dentro una
        transazione (`StateService.complete`) senza annidare i decoratori e
        provocare il rollback del savepoint esterno (vedi CLAUDE.md).

        Va chiamata anche quando la gara si conclude **senza** spareggio: i
        parimerito fuori dalle posizioni contese non generano SSR (issue #63),
        quindi senza questo passaggio conserverebbero le posizioni progressive
        scritte dal calcolo per turno (issue #67). Senza punteggi SSR la
        chiave di merito degrada naturalmente ai soli punti.
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

        # La chiave di MERITO dipende dal classification_system, coerente
        # con _group_by_classification (che definisce quali giocatori sono a
        # pari merito). Lo SSR è il tiebreaker DECISIVO entro gruppi a pari
        # merito, quindi va sempre per ultimo.
        # - RACK: (rack totali DESC, ssr_score DESC)
        # - WINS / POSITION (default): (matches_won DESC, rack_difference DESC,
        #   ssr_score DESC). Senza matches_won il vincitore reale per vittorie
        #   veniva scavalcato (bug high).
        # -1 (SSR non inserito) ordina per ultimo a pari chiave primaria.
        classification_system = (gara.classification_system or "WINS").upper()
        merit_key: Callable[[Dict], Tuple[int, ...]] = (
            (lambda x: (-x["rack_totali"], -x["ssr_score"]))
            if classification_system == "RACK"
            else (lambda x: (-x["matches_won"], -x["rack_totali"], -x["ssr_score"]))
        )

        # POSITION: la classifica la dà il tabellone, non i totali. Chi è
        # uscito allo stesso turno condivide la banda e quindi la chiave, così
        # `assign_shared_positions` gli assegna la stessa posizione — che è
        # esattamente il risultato voluto, non un pareggio da sciogliere.
        # In produzione la classifica finale passa da qui, non da
        # `calculate_gara_classification`.
        if classification_system == "POSITION":
            bracket = bracket_positions(gara)
            if bracket:
                for data in player_data:
                    data["bracket_position"] = bracket.get(
                        data["user_id"], NO_BRACKET_POSITION
                    )
                merit_key = lambda x: (x["bracket_position"],)  # noqa: E731
            else:
                # Gara POSITION senza tabellone persistito: meglio l'ordine
                # per vittorie di una classifica tutta a pari merito.
                logger.warning(
                    "Gara %s è POSITION ma non ha un tabellone persistito: "
                    "posizioni finali calcolate per vittorie",
                    gara_id,
                )

        # A pari merito l'ordine di ELENCAZIONE è quello di estrazione, non la
        # posizione di partenza né il rowid: è l'unico criterio che il
        # giocatore vede e riconosce ("Ordine sorteggio"). Resta fuori dalla
        # chiave di merito, quindi non separa le posizioni (issue #67).
        draw_order = SpareggioService.draw_order_map(gara_id)
        no_draw_order = 10**6
        player_data.sort(
            key=lambda x: (
                merit_key(x),
                draw_order.get(x["user_id"], no_draw_order),
                x["user_id"],
            )
        )

        # Update/create GaraClassification and RoundClassification with
        # correct positions. Chi condivide la chiave di merito condivide la
        # posizione (1, 2, 2, 4): prima erano sempre progressive e due
        # giocatori a pari punti, che nessuno spareggio doveva separare,
        # comparivano come 7° e 8° (issue #67).
        for position, data in SpareggioService.assign_shared_positions(
            player_data, merit_key
        ):
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
