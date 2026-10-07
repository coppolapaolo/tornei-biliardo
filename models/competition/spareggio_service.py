"""
Module: models/competition/spareggio_service.py
Purpose: Handle spot shot rally (SSR) tiebreakers for top 3 positions
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, TypedDict
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
    # Le posizioni che lo spareggio decide: dalla posizione del gruppo fino a
    # tiebreaker_until_position (vedi posti_in_palio). Serve a dire al
    # direttore *che* spareggio è — per il 2° e il 3°, o solo per il 3°.
    posti_in_palio: List[int]


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
        from models.classification.catene import (
            catena_di_gara,
            ordina_con_la_catena,
            sistema_dichiarato,
        )
        from models.classification.ordinamento import ssr_della_catena

        if not ordina_con_la_catena(sistema_dichiarato(gara)):
            return False
        return ssr_della_catena(catena_di_gara(gara)) is not None

    @staticmethod
    def ssr_fino_al(gara) -> int:
        """Il posto fin dove lo spareggio SSR della catena di gara decide."""
        from models.classification.catene import catena_di_gara
        from models.classification.ordinamento import (
            SSR_FINO_AL_DEFAULT,
            ssr_della_catena,
        )

        voce = ssr_della_catena(catena_di_gara(gara))
        if voce is None or voce.fino_al is None:
            return SSR_FINO_AL_DEFAULT
        return voce.fino_al

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
    def posti_in_palio(
        group_size: int, group_position: int, tiebreaker_limit: int
    ) -> List[int]:
        """Le posizioni che lo spareggio di questo gruppo decide.

        Un gruppo di ``n`` alla posizione ``p`` occupa ``p .. p+n-1``, ma solo
        quelle fino a ``tiebreaker_limit`` sono in palio: quattro giocatori al
        3° posto con limite 3 si contendono il 3° e basta, e gli altri tre
        restano a pari merito (issue #63). È la stessa regola di
        `positions_to_discriminate`, detta in posti invece che in punteggi:
        per assegnare ``k`` posti bastano ``k`` punteggi distinti in cima, ma
        se i posti sono tanti quanti i giocatori l'ultimo si deduce.
        """
        if group_size < 2:
            return []
        ultimo = min(group_position + group_size - 1, tiebreaker_limit)
        return list(range(group_position, ultimo + 1))

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
    def _fasce(gara: Gara, fino_allo_ssr: bool = False) -> List[Tuple[int, List]]:
        """Le righe dell'ultimo turno in fasce: vedi `_fasce_e_gironi`."""
        return SpareggioService._fasce_e_gironi(gara, fino_allo_ssr)[0]

    @staticmethod
    def _fasce_e_gironi(
        gara: Gara, fino_allo_ssr: bool = False
    ) -> Tuple[List[Tuple[int, List]], Dict[int, Tuple[int, int]]]:
        """Le righe dell'ultimo turno in fasce, secondo la catena di gara.

        Il secondo valore, nel girone all'italiana a più gironi, dice per ogni
        giocatore girone e posizione nel girone (ADR-076): lì la gara mette
        prima i primi di ogni girone, poi i secondi, e lo spareggio scioglie
        i pari di questa classifica. Vuoto con il girone unico.

        Una fascia è ``(posizione, righe)``: più righe sono un pari merito. È
        **l'unica** risposta alla domanda «chi è a pari merito?», per lo
        spareggio da giocare come per la classifica finale (ADR-078). Prima
        la si calcolava in tre posti, ciascuno con la sua chiave.

        Con ``fino_allo_ssr`` la catena si ferma prima dello spareggio: sono i
        pari che lo spareggio deve sciogliere, se partono entro il suo posto.
        Il sistema POSITION non arriva mai qui (``tiebreakers_apply_to``).
        """
        from models.classification.catene import (
            catena_di_gara,
            scontri_delle_gare,
            sistema_della_gara,
            usa_scontri,
        )
        from models.classification.ordinamento import (
            Concorrente,
            chiave_di_sorteggio,
            criterio_principale,
            ordina,
            prima_dello_ssr,
            seme_della_gara,
        )

        final_round = SpareggioService._get_effective_final_round(gara)
        righe = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara.id, round_number=final_round)
            .order_by(RoundClassification.position)
            .all()
        )
        if not righe:
            return [], {}
        ssr = {
            gc.user_id: gc.spot_shot_wins
            for gc in db.session.query(GaraClassification)
            .filter_by(gara_id=gara.id)
            .all()
        }
        sistema = sistema_della_gara(gara)
        catena = catena_di_gara(gara)
        if fino_allo_ssr:
            catena = prima_dello_ssr(catena)
        seme = seme_della_gara(gara)
        concorrenti = [
            Concorrente(
                player_id=rc.user_id,
                vittorie=rc.matches_won or 0,
                # `total_racks_value`: il totale, con il ripiego per le righe
                # scritte prima della separazione delle colonne (20260728).
                rack_vinti=rc.total_racks_value,
                differenza_rack=rc.rack_difference or 0,
                punti=rc.points or 0,
                ssr=ssr.get(rc.user_id),
                posizione_precedente=rc.previous_position,
                sorteggio=chiave_di_sorteggio(seme, rc.user_id),
            )
            for rc in righe
        ]
        per_id = {rc.user_id: rc for rc in righe}
        from models.competition.gironi_service import GironiService

        girone = GironiService.girone_dei_giocatori(gara)
        if girone:
            from models.classification.gironi_della_gara import classifica_a_gironi

            esito = classifica_a_gironi(
                gara, concorrenti, girone, catena, final_round, completa=False
            )
            return [
                (fascia.posizione, [per_id[c.player_id] for c in fascia.giocatori])
                for fascia in esito.fasce
            ], {
                pid: (esito.girone[pid], esito.posizione_nel_girone[pid])
                for pid in esito.girone
            }
        scontri = (
            scontri_delle_gare([gara.id], final_round) if usa_scontri(catena) else ()
        )
        return [
            (fascia.posizione, [per_id[c.player_id] for c in fascia.giocatori])
            for fascia in ordina(
                concorrenti, criterio_principale(sistema), catena, scontri=scontri
            )
        ], {}

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

        tiebreaker_limit = SpareggioService.ssr_fino_al(gara)

        tiebreaker_groups: List[TiebreakerGroup] = []
        # `rack_totali` è il valore su cui il gruppo è pari: la differenza
        # nel sistema a vittorie, il totale nel sistema a rack.
        for current_position, group in SpareggioService._fasce(
            gara, fino_allo_ssr=True
        ):
            # Oltre il posto dello spareggio i pari merito restano tali.
            if current_position > tiebreaker_limit:
                break
            if len(group) < 2:
                continue
            rack_count = (
                group[0].ranking_rack_value
                if (gara.classification_system or "WINS").upper() == "RACK"
                else group[0].rack_difference or 0
            )
            existing_gara_class = (
                db.session.query(GaraClassification)
                .filter(
                    GaraClassification.gara_id == gara_id,
                    GaraClassification.user_id.in_([c.user_id for c in group]),
                )
                .all()
            )
            ssr_scores = {gc.user_id: gc.spot_shot_wins for gc in existing_gara_class}

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

            # Il gruppo è risolto quando tutti hanno un punteggio (0 è
            # valido, None = non inserito) e i punteggi separano le sole
            # posizioni contese. I pari merito oltre il posto dello
            # spareggio sono legittimi (issue #63).
            needed = SpareggioService.positions_to_discriminate(
                len(group), current_position, tiebreaker_limit
            )
            scores = [p["current_ssr_score"] for p in players]
            if not SpareggioService.scores_resolve_group(scores, needed):
                tiebreaker_groups.append(
                    {
                        "position": current_position,
                        "rack_totali": rack_count,
                        "players": players,
                        "needs_distinct_top": needed,
                        "posti_in_palio": SpareggioService.posti_in_palio(
                            len(group), current_position, tiebreaker_limit
                        ),
                    }
                )

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

        tiebreaker_limit = SpareggioService.ssr_fino_al(gara)

        all_groups: List[TiebreakerGroup] = []
        # `rack_totali` è il valore su cui il gruppo è pari: la differenza
        # nel sistema a vittorie, il totale nel sistema a rack.
        for current_position, group in SpareggioService._fasce(
            gara, fino_allo_ssr=True
        ):
            # Oltre il posto dello spareggio i pari merito restano tali.
            if current_position > tiebreaker_limit:
                break
            if len(group) < 2:
                continue
            rack_count = (
                group[0].ranking_rack_value
                if (gara.classification_system or "WINS").upper() == "RACK"
                else group[0].rack_difference or 0
            )
            existing_gara_class = (
                db.session.query(GaraClassification)
                .filter(
                    GaraClassification.gara_id == gara_id,
                    GaraClassification.user_id.in_([c.user_id for c in group]),
                )
                .all()
            )
            ssr_scores = {gc.user_id: gc.spot_shot_wins for gc in existing_gara_class}

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
                    "posti_in_palio": SpareggioService.posti_in_palio(
                        len(group), current_position, tiebreaker_limit
                    ),
                }
            )

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
                    # `total_racks_value`, non `ranking_rack_value`: qui si
                    # **persiste** un totale, e il secondo restituisce la
                    # differenza in ogni gara che non sia RACK.
                    racks_won=round_class.total_racks_value,
                    rack_difference=round_class.rack_difference or 0,
                    points=round_class.points,
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
                    # `total_racks_value`, non `ranking_rack_value`: qui si
                    # **persiste** un totale, e il secondo restituisce la
                    # differenza in ogni gara che non sia RACK.
                    racks_won=round_class.total_racks_value,
                    rack_difference=round_class.rack_difference or 0,
                    points=round_class.points,
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
        transazionale (`StateService.cancel_ssr`), che salva. Annidare i
        decoratori non provoca più rollback dal 2026-09-13 (ADR-061).
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

        Senza `@transactional`: è chiamata dentro contesti già transazionali,
        che salvano (stessa ragione di `clear_ssr_scores`).

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

        existing_gara_class = {
            gc.user_id: gc
            for gc in db.session.query(GaraClassification)
            .filter_by(gara_id=gara_id)
            .all()
        }

        # POSITION: la classifica la dà il tabellone, non i totali. Chi è
        # uscito allo stesso turno condivide la banda e quindi la posizione —
        # che è esattamente il risultato voluto, non un pareggio da sciogliere
        # (ADR-040). Tutti gli altri sistemi passano dalla catena di gara
        # (ADR-078): chi resta pari dopo la catena condivide la posizione.
        classification_system = (gara.classification_system or "WINS").upper()
        fasce: Optional[List[Tuple[int, List]]] = None
        gironi: Dict[int, Tuple[int, int]] = {}
        if classification_system == "POSITION":
            fasce = SpareggioService._fasce_del_tabellone(gara, final_round)
        if fasce is None:
            fasce, gironi = SpareggioService._fasce_e_gironi(gara)

        # A pari merito l'ordine di ELENCAZIONE è quello di estrazione, non la
        # posizione di partenza né il rowid: è l'unico criterio che il
        # giocatore vede e riconosce ("Ordine sorteggio"). Non separa le
        # posizioni (issue #67).
        draw_order = SpareggioService.draw_order_map(gara_id)
        no_draw_order = 10**6

        for position, righe in fasce:
            righe = sorted(
                righe,
                key=lambda rc: (draw_order.get(rc.user_id, no_draw_order), rc.user_id),
            )
            for round_class in righe:
                gara_class = existing_gara_class.get(round_class.user_id)
                if not gara_class:
                    gara_class = GaraClassification(
                        gara_id=gara_id,
                        user_id=round_class.user_id,
                        # `total_racks_value`, non `ranking_rack_value`: qui si
                        # **persiste** un totale.
                        racks_won=round_class.total_racks_value,
                        rack_difference=round_class.rack_difference or 0,
                        matches_won=round_class.matches_won,
                        points=round_class.points,
                    )
                    db.session.add(gara_class)
                gara_class.position = position
                gara_class.points = round_class.points
                # Anche la classifica di turno, perché è quella che la pagina
                # mostra.
                round_class.position = position
                if gironi:
                    gruppo, nel_girone = gironi.get(round_class.user_id, (None, None))
                    gara_class.group_index = round_class.group_index = gruppo
                    gara_class.group_position = round_class.group_position = (
                        nel_girone
                    )

        return True, "Classifica finale aggiornata"

    @staticmethod
    def _fasce_del_tabellone(
        gara: Gara, final_round: int
    ) -> Optional[List[Tuple[int, List]]]:
        """Le fasce del sistema POSITION: la banda del tabellone (ADR-040).

        None se la gara non ha un tabellone persistito: allora si ordina per
        vittorie con la catena, che è meglio di una classifica tutta a pari.
        """
        bracket = bracket_positions(gara)
        if not bracket:
            logger.warning(
                "Gara %s è POSITION ma non ha un tabellone persistito: "
                "posizioni finali calcolate per vittorie",
                gara.id,
            )
            return None
        righe = (
            db.session.query(RoundClassification)
            .filter_by(gara_id=gara.id, round_number=final_round)
            .order_by(RoundClassification.position)
            .all()
        )
        per_banda: Dict[int, List] = {}
        for rc in righe:
            per_banda.setdefault(
                bracket.get(rc.user_id, NO_BRACKET_POSITION), []
            ).append(rc)
        fasce: List[Tuple[int, List]] = []
        posizione = 1
        for banda in sorted(per_banda):
            fasce.append((posizione, per_banda[banda]))
            posizione += len(per_banda[banda])
        return fasce
