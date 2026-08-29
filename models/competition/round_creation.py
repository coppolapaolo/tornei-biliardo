"""
Module: models/competition/round_creation.py
Purpose: Round creation logic (create_round_with_strategy, start_next_round,
_create_round_impl)
"""

from __future__ import annotations

from typing import Optional, Set

from models.base import db, transactional
from models.status_enum import GaraStatus
from .models import Gara


def resolve_round_overrides(gara: Gara, round_number: int) -> dict:
    """Risolvi gli override per turno (RoundConfiguration) su una gara.

    ADR-027: dato il modello override-NULL=fallback-gara, restituisce un
    dict pronto per essere espanso negli kwarg di create_matches_from_pairings.
    Centralizza la logica per evitare duplicazione tra round_creation e
    round_service (entrambi creano match e devono propagare le stesse regole).
    """
    from models.competition.round_configuration import RoundConfiguration

    round_config = RoundConfiguration.get_for_gara_round(gara.id, round_number)
    if not round_config:
        return {
            "round_distance": gara.distance,
            "round_discipline": None,
            "round_is_race_to": gara.is_race_to,
            "round_is_multi_set": gara.is_multi_set,
            "round_match_distance": gara.match_distance,
            "round_is_race_to_sets": getattr(gara, "is_race_to_sets", True),
        }
    return {
        "round_distance": round_config.get_effective_distance(gara.distance),
        "round_discipline": round_config.discipline,
        "round_is_race_to": round_config.get_effective_is_race_to(gara.is_race_to),
        "round_is_multi_set": round_config.get_effective_is_multi_set(
            gara.is_multi_set
        ),
        "round_match_distance": round_config.get_effective_match_distance(
            gara.match_distance
        ),
        "round_is_race_to_sets": round_config.get_effective_is_race_to_sets(
            getattr(gara, "is_race_to_sets", True)
        ),
    }


def create_matches_from_pairings(
    gara: Gara,
    pairings: list,
    round_number: int,
    round_distance: int,
    round_discipline: Optional[str] = None,
    forfeit_user_ids: Optional[Set[int]] = None,
    round_is_race_to: Optional[bool] = None,
    round_is_multi_set: Optional[bool] = None,
    round_match_distance: Optional[int] = None,
    round_is_race_to_sets: Optional[bool] = None,
) -> None:
    """Create Match (and TrioMatch) objects from strategy pairings.

    ADR-027: oltre a discipline e distance, propaga gli override per turno
    (is_race_to, is_multi_set, match_distance multi-set, is_race_to_sets) a
    ogni Match creato. I parametri round_* nullable=None mantengono il default
    della gara, NON solo per back-compat ma per esprimere "nessun override".
    """
    from models.match.models import Match, TrioMatch
    from models.match.state_service import MatchStateService

    if forfeit_user_ids is None:
        forfeit_user_ids = set()

    # Override risolti: passati esplicitamente o ereditati dalla gara.
    is_multi_set = (
        round_is_multi_set if round_is_multi_set is not None else gara.is_multi_set
    )
    # Per single-set: match_distance memorizza i rack-per-vincere del round.
    # Per multi-set: match_distance memorizza i set-per-vincere il match.
    if is_multi_set:
        match_distance_field = (
            round_match_distance
            if round_match_distance is not None
            else (gara.match_distance or 1)
        )
    else:
        match_distance_field = round_distance

    # is_race_to / is_race_to_sets sono nullable su Match: NULL = eredita gara.
    # Memorizziamo l'override esplicito solo se differisce dalla gara, per
    # tenere lo schema parlante (NULL = "nessun override").
    is_race_to_override = (
        round_is_race_to
        if (round_is_race_to is not None and round_is_race_to != gara.is_race_to)
        else None
    )
    gara_irts = getattr(gara, "is_race_to_sets", True)
    is_race_to_sets_override = (
        round_is_race_to_sets
        if (round_is_race_to_sets is not None and round_is_race_to_sets != gara_irts)
        else None
    )

    common_kwargs = {
        "gara_id": gara.id,
        "round_number": round_number,
        "discipline": round_discipline,
        "match_distance": match_distance_field,
        "is_multi_set": is_multi_set,
        "is_race_to": is_race_to_override,
        "is_race_to_sets": is_race_to_sets_override,
    }

    # Per il forfeit "winning_score" è il numero di rack del round, non la
    # match_distance (che in multi-set è il numero di set): chi vince a
    # tavolino prende il punteggio pieno, perché l'avversario si è ritirato.
    winning_score = round_distance

    # La X *non* è un forfeit, e non prende il punteggio pieno.
    # `SPECIFICHE.md` righe 64 e 71: la X assegna «il match vinto, ma con zero
    # differenza punti», così chi riposa si piazza «migliore di tutti i
    # perdenti e peggiore di tutti i vincenti». Con `round_distance` era il
    # contrario — la X valeva quanto la vittoria più larga possibile e chi
    # riposava scavalcava chi aveva vinto giocando.
    # Lo dichiarava già `validators._validate_rack_system`, che vieta il bye
    # semplice col sistema RACK proprio perché «il giocatore con bye
    # riceverebbe 0 rack»: quel divieto e questa riga adesso concordano.
    # La variante con challenge (riga 65) sovrascrive questo punteggio quando
    # la prova viene completata — vedi `AmalfiChallengeByeService`.
    bye_score = 0

    for pairing in pairings:
        # Le coordinate variano per pairing, quindi non possono stare in
        # common_kwargs. getattr con default perché diversi test passano
        # pairing duck-typed che non hanno questi attributi.
        bracket_kwargs = {
            "bracket_type": getattr(pairing, "bracket_type", None),
            "bracket_round": getattr(pairing, "bracket_round", None),
            "bracket_slot": getattr(pairing, "bracket_slot", None),
            "bracket_group": getattr(pairing, "bracket_group", None),
        }

        if len(pairing.players) == 1 and pairing.is_bye:
            match = Match(
                **common_kwargs,
                **bracket_kwargs,
                player1_id=pairing.players[0],
                player2_id=None,
                is_bye=True,
                player1_score=bye_score,
                winner_id=pairing.players[0],
                status="pending",
            )
            db.session.add(match)
            db.session.flush()
            MatchStateService.to_completed(match.id)
        elif len(pairing.players) == 2 and not pairing.is_bye:
            player1_forfeit = pairing.players[0] in forfeit_user_ids
            player2_forfeit = pairing.players[1] in forfeit_user_ids

            if player1_forfeit or player2_forfeit:
                if player1_forfeit and player2_forfeit:
                    winner_id = pairing.players[0]
                    player1_score = winning_score
                    player2_score = 0
                elif player1_forfeit:
                    winner_id = pairing.players[1]
                    player1_score = 0
                    player2_score = winning_score
                else:
                    winner_id = pairing.players[0]
                    player1_score = winning_score
                    player2_score = 0

                match = Match(
                    **common_kwargs,
                    **bracket_kwargs,
                    player1_id=pairing.players[0],
                    player2_id=pairing.players[1],
                    is_bye=False,
                    player1_score=player1_score,
                    player2_score=player2_score,
                    winner_id=winner_id,
                    status="pending",
                )
                db.session.add(match)
                db.session.flush()
                # La partita nasce già decisa e non passa mai da PLAYING:
                # chiuderla da PENDING è una facoltà del direttore, e ora si
                # dichiara. Prima lo si comunicava scrivendo
                # `match.validated_by_admin = True` — un attributo che su
                # `Match` non esiste (vive su `Rack`) e che `to_completed`
                # rileggeva col `getattr`. Il `# type: ignore[attr-defined]`
                # che serviva a zittire pyright era il codice che lo ammetteva
                # da solo.
                MatchStateService.to_completed(match.id, closed_by_director=True)
            else:
                match = Match(
                    **common_kwargs,
                    **bracket_kwargs,
                    player1_id=pairing.players[0],
                    player2_id=pairing.players[1],
                    is_bye=False,
                )
                db.session.add(match)
        elif len(pairing.players) == 3:
            p0, p1, p2 = pairing.players
            n_forfeit = sum(1 for p in pairing.players if p in forfeit_user_ids)

            if n_forfeit == 0:
                # Trio: i trio non sono multi-set e usano match_distance per
                # racks (TrioConfig calcola da effective_distance).
                trio_kwargs = {
                    **common_kwargs,
                    "is_multi_set": False,
                    "match_distance": round_distance,
                }
                match = Match(
                    **trio_kwargs,
                    player1_id=p0,
                    player2_id=p1,
                    is_bye=False,
                    is_trio=True,
                )
                db.session.add(match)
                db.session.flush()

                trio_match = TrioMatch(
                    match_id=match.id,
                    player1_id=p0,
                    player2_id=p1,
                    player3_id=p2,
                )
                db.session.add(trio_match)
                db.session.flush()
                trio_match.initialize_matchup()
            elif n_forfeit == 1:
                survivors = [p for p in pairing.players if p not in forfeit_user_ids]
                match = Match(
                    **common_kwargs,
                    player1_id=survivors[0],
                    player2_id=survivors[1],
                    is_bye=False,
                    is_trio=False,
                )
                db.session.add(match)
            else:
                if n_forfeit == 2:
                    winner_id = next(
                        p for p in pairing.players if p not in forfeit_user_ids
                    )
                else:
                    winner_id = p0

                trio_kwargs = {
                    **common_kwargs,
                    "is_multi_set": False,
                    "match_distance": round_distance,
                }
                match = Match(
                    **trio_kwargs,
                    player1_id=p0,
                    player2_id=p1,
                    is_bye=False,
                    is_trio=True,
                    player1_score=winning_score,
                    player2_score=0,
                    winner_id=winner_id,
                    status="pending",
                )
                db.session.add(match)
                db.session.flush()

                trio_match = TrioMatch(
                    match_id=match.id,
                    player1_id=p0,
                    player2_id=p1,
                    player3_id=p2,
                    winner_id=winner_id,
                    is_completed=True,
                )
                db.session.add(trio_match)
                db.session.flush()
                trio_match.initialize_matchup()
                MatchStateService.to_completed(match.id)


class RoundCreationService:
    """Round creation and match generation logic."""

    @staticmethod
    @transactional(domain="competition")
    def create_round_with_strategy(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int]:
        """Crea un turno usando la strategia configurata nella gara.

        Returns:
            Tuple con (total_matches, normal_matches, bye_matches, trio_matches)
        """
        return RoundCreationService._create_round_impl(
            gara_id, round_number, discipline_override
        )

    @staticmethod
    @transactional(domain="competition")
    def start_next_round(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int, int]:
        """Create a round and advance the gara state.

        Combines round creation, state transition to PLAYING,
        current_round update, and table assignment in one transaction.

        Returns:
            Tuple: (total, normal, bye, trio, tables_assigned)
        """
        from models.competition.state_service import StateService
        from models.match.table_assignment_service import TableAssignmentService

        total, n_normal, n_bye, n_trio = RoundCreationService._create_round_impl(
            gara_id, round_number, discipline_override
        )

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if gara.status != GaraStatus.PLAYING.value:
            StateService.start_playing(gara)
            db.session.refresh(gara)

        gara.current_round = round_number

        # Un turno oltre quelli programmati puo' esistere solo se la strategia
        # l'ha riconosciuto (il guard sopra), e allora la gara ne ha uno in
        # piu': la bella del doppio KO. Il numero si aggiorna qui, sul turno
        # **appena creato**, e non in anticipo su un turno che meta' delle
        # volte non nascera'. E' lo stesso momento in cui il sorteggio scrive
        # `rounds_count` smettendo di stimarlo (ADR-038).
        if round_number > (gara.rounds_count or 0):
            gara.rounds_count = round_number

        tables_assigned = TableAssignmentService.assign_tables_to_round(
            gara_id, round_number
        )

        return total, n_normal, n_bye, n_trio, tables_assigned

    @staticmethod
    def _create_round_impl(
        gara_id: int, round_number: int, discipline_override: Optional[str] = None
    ) -> tuple[int, int, int, int]:
        """Core round creation (no @transactional, called inside a transaction)."""
        from models.match.models import Match, TrioMatch

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        # Verifica precondizioni. Il limite non e' `rounds_count` ma cio' che
        # la strategia riconosce come turno: nel doppio KO la bella sta un
        # turno oltre quelli programmati, e solo se la finale la richiede.
        from models.matchmaking.bootstrap import strategy_for_gara

        strategia = strategy_for_gara(gara)
        turno_valido = (
            strategia.has_round(gara, round_number)
            if strategia is not None
            else 1 <= round_number <= gara.rounds_count
        )
        if not turno_valido:
            raise ValueError(f"Turno {round_number} non valido")

        # Verifica se esistono già match per questo turno
        existing_matches = (
            db.session.query(Match)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .count()
        )
        if existing_matches > 0:
            # I match esistono già, ritorna i conteggi attuali
            matches = (
                db.session.query(Match)
                .filter_by(gara_id=gara_id, round_number=round_number)
                .all()
            )
            normal_matches = sum(
                1 for m in matches if not m.is_bye and not getattr(m, "is_trio", False)
            )
            bye_matches = sum(1 for m in matches if m.is_bye)
            trio_matches = sum(1 for m in matches if getattr(m, "is_trio", False))
            return (len(matches), normal_matches, bye_matches, trio_matches)

        # Ottieni la strategia configurata (unica fonte per la mappatura)
        from models.matchmaking.bootstrap import strategy_for_gara

        strategy = strategy_for_gara(gara)
        if not strategy:
            raise ValueError(f"Strategia '{gara.matchmaking_strategy}' non trovata")

        # Genera gli abbinamenti usando l'interfaccia della strategia
        pairings = strategy.create_round(gara, round_number)

        # Un turno senza accoppiamenti non e' uno stato: e' un turno che non
        # doveva aprirsi. Il doppio KO lo dichiarava legittimo — "zero pairing
        # significa torneo concluso" — e la gara restava PLAYING per sempre su
        # un turno senza partite (issue #239). Ora la domanda "questo turno
        # esiste?" si pone **prima**, con `strategy.has_round`, e arrivare qui
        # a mani vuote significa che quella domanda e la generazione si sono
        # disallineate: e' un difetto, e va detto invece che materializzato.
        if not pairings:
            raise ValueError(
                f"Il turno {round_number} della gara {gara_id} non produce "
                f"accoppiamenti: non c'e' nessun turno da avviare"
            )

        # Materializza la classifica di partenza (turno 0) al primo turno.
        if round_number == 1:
            from models.classification.seeding_service import SeedingService

            SeedingService.persist_first_round_seeding(gara_id, strategy, pairings)

        # Get forfeit players for this gara to handle completed matches
        from models.competition.withdraw_policy_service import WithdrawPolicyService

        forfeit_user_ids = WithdrawPolicyService.get_forfeit_user_ids(gara_id)

        # ADR-027: risolvi tutti gli override per turno via helper.
        overrides = resolve_round_overrides(gara, round_number)
        # discipline_override (param routes) vince su quello della config.
        if discipline_override:
            overrides["round_discipline"] = discipline_override

        create_matches_from_pairings(
            gara=gara,
            pairings=pairings,
            forfeit_user_ids=forfeit_user_ids,
            round_number=round_number,
            **overrides,
        )

        # Conta i risultati
        matches = (
            db.session.query(Match)
            .filter_by(gara_id=gara_id, round_number=round_number)
            .all()
        )
        normal_matches = sum(1 for m in matches if not m.is_bye and not m.is_trio)
        bye_matches = sum(1 for m in matches if m.is_bye)
        trio_matches = (
            db.session.query(TrioMatch)
            .join(Match)
            .filter(Match.gara_id == gara_id, Match.round_number == round_number)
            .count()
        )
        total_matches = len(matches)

        # Lock previous round matches when creating a new round
        if round_number > 1:
            previous_round_matches = (
                db.session.query(Match)
                .filter_by(gara_id=gara_id, round_number=round_number - 1)
                .all()
            )
            for match in previous_round_matches:
                match.round_locked = True
                db.session.add(match)

        return (total_matches, normal_matches, bye_matches, trio_matches)
