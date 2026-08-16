"""Production regression — gara standalone 6 iscritti, 2026-05-20.

Ricostruisce lo scenario reale che ha esposto 4 bug (vedi piano associato):

  1. Anti-rematch fallito: PIETRO vs GABRIELE duplicato a T3 e T4 nonostante
     con 6 giocatori siano possibili 5 turni round-robin completi senza reincontri.
  2. Validazione lato player mancante: 3-2 (totale 5) con limite "4 rack esatti".
  3. Wizard standalone privo di `classification_system`.
  4. Classifica e SSR non rispettavano `classification_system`.

I 12 match reali (con i punteggi) sono in `SCENARIO_2026_05_20`. Setup tramite
`setup_scenario_2026_05_20`: bypassa il matchmaking creando direttamente i match
coi punteggi reali — utile per testare la classifica/SSR indipendentemente dal
fix anti-rematch.
"""

import pytest
import uuid
from datetime import date, timedelta
from typing import Dict, List, Tuple

from models import User, Gara, Match
from models.user.role_enum import UserRole
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.match.scoring_service import ScoringService
from models.match.models import Rack
from models.base import utc_now, db

# (round, p1, p2, p1_score, p2_score)
SCENARIO_2026_05_20: List[Tuple[int, str, str, int, int]] = [
    (1, "MAX P", "GABRIELE", 3, 2),
    (1, "EMILIO", "PIETRO", 2, 3),
    (1, "PAOLO", "SAMUEL", 1, 4),
    (2, "EMILIO", "MAX P", 3, 1),
    (2, "SAMUEL", "PIETRO", 1, 3),
    (2, "PAOLO", "GABRIELE", 1, 3),
    (3, "SAMUEL", "MAX P", 2, 2),
    (3, "PAOLO", "EMILIO", 4, 0),
    (3, "PIETRO", "GABRIELE", 2, 2),
    (4, "PAOLO", "MAX P", 5, 0),
    (4, "SAMUEL", "EMILIO", 3, 2),
    (4, "PIETRO", "GABRIELE", 3, 2),  # bug reale: duplicato di T3
]

PLAYER_NAMES = ["MAX P", "GABRIELE", "EMILIO", "PIETRO", "PAOLO", "SAMUEL"]


@pytest.fixture
def director(db_session) -> User:
    uid = str(uuid.uuid4())[:8]
    u = User(
        username=f"director_{uid}",
        email=f"director_{uid}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    u.set_password("director123")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def players_by_name(db_session) -> Dict[str, User]:
    """6 player con nomi reali della gara di produzione."""
    uid = str(uuid.uuid4())[:8]
    out: Dict[str, User] = {}
    for name in PLAYER_NAMES:
        u = User(
            username=f"{name.replace(' ', '_').lower()}_{uid}",
            email=f"{name.replace(' ', '_').lower()}_{uid}@test.com",
            role=UserRole.PLAYER.value,
        )
        u.set_password("player123")
        db_session.add(u)
        out[name] = u
    db_session.commit()
    return out


def _create_random_gara(
    director_id: int,
    rounds_count: int,
    *,
    distance: int = 5,
    is_race_to: bool = True,
    classification_system: str = "WINS",
    tiebreaker_enabled: bool = False,
) -> Gara:
    # Per RACK il validator rifiuta `bye` semplice (0 rack penalizza); usa
    # `bye_with_challenge`. Con 6 player pari (scenario di produzione) la
    # policy non viene comunque esercitata.
    odd_policy = "bye_with_challenge" if classification_system == "RACK" else "bye"
    return GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Regression 2026-05-20",
        date=date.today() + timedelta(days=7),
        location="Test Venue",
        description="Regression test",
        rounds_count=rounds_count,
        min_participants=4,
        max_participants=20,
        entry_fee=0.0,
        discipline="8_ball",
        distance=distance,
        is_race_to=is_race_to,
        director_id=director_id,
        matchmaking_strategy="random",
        first_round_policy="random",
        odd_number_policy=odd_policy,
        anti_rematch_enabled=True,
        classification_system=classification_system,
        tiebreaker_enabled=tiebreaker_enabled,
    )


def _inscribe_all(gara: Gara, players: List[User]) -> None:
    inscription_start = utc_now() - timedelta(hours=1)
    inscription_end = utc_now() + timedelta(hours=1)
    InscriptionService.open_inscriptions(gara.id, inscription_start, inscription_end)
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)


# ────────────────────────────────────────────────────────────────────────
# Bug 1 — Random anti-rematch
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_regression_random_4_rounds_no_rematches(
    director: User, players_by_name: Dict[str, User], db_session
):
    """Scenario produzione: 6 player × 4 turni random → 0 reincontri."""
    gara = _create_random_gara(director.id, rounds_count=4)
    _inscribe_all(gara, list(players_by_name.values()))

    RoundService.start_first_round(gara.id)

    # Raccoglie tutti i pair generati
    pairs: List[frozenset] = []
    for round_num in range(1, 5):
        matches = Match.query.filter_by(gara_id=gara.id, round_number=round_num).all()
        for m in matches:
            if m.is_bye or m.is_trio or m.player2_id is None:
                continue
            pairs.append(frozenset([m.player1_id, m.player2_id]))

    assert len(pairs) == len(set(pairs)), (
        f"Reincontri trovati: 4 turni su 6 player devono essere zero "
        f"reincontri ma {len(pairs) - len(set(pairs))} duplicati presenti"
    )


@pytest.mark.integration
def test_random_full_schedule_at_least_n_minus_1_rounds(
    director: User, players_by_name: Dict[str, User], db_session
):
    """6 player × 5 round (N-1) → round-robin completo, 0 reincontri."""
    gara = _create_random_gara(director.id, rounds_count=5)
    _inscribe_all(gara, list(players_by_name.values()))

    RoundService.start_first_round(gara.id)

    pairs: List[frozenset] = []
    for round_num in range(1, 6):
        for m in Match.query.filter_by(gara_id=gara.id, round_number=round_num).all():
            if m.is_bye or m.is_trio or m.player2_id is None:
                continue
            pairs.append(frozenset([m.player1_id, m.player2_id]))

    # 6 player × 5 turni × 3 match/turno = 15 = C(6, 2) → tutti i pair distinti
    assert len(pairs) == 15
    assert len(set(pairs)) == 15


# ────────────────────────────────────────────────────────────────────────
# Bug 2 — Player path validation in modalità "rack esatti"
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_player_path_rejects_exceeding_total_in_exact_mode(
    director: User, players_by_name: Dict[str, User], db_session
):
    """Match RACKS_EXACT 4: il 5° rack via player path solleva ValueError."""
    gara = _create_random_gara(
        director.id, rounds_count=1, distance=4, is_race_to=False
    )
    _inscribe_all(gara, list(players_by_name.values()))
    RoundService.start_first_round(gara.id)

    match = (
        Match.query.filter_by(gara_id=gara.id, round_number=1)
        .filter(Match.player2_id.isnot(None))
        .first()
    )
    assert match is not None, "Match valido a 2 giocatori atteso"

    # Porta lo score a 2-2 via player path (totale = distance.racks = 4)
    ScoringService.add_rack_for_player(match.id, match.player1_id, match.player1_id)
    ScoringService.add_rack_for_player(match.id, match.player2_id, match.player2_id)
    ScoringService.add_rack_for_player(match.id, match.player1_id, match.player1_id)
    ScoringService.add_rack_for_player(match.id, match.player2_id, match.player2_id)

    fresh = db.session.get(Match, match.id)
    assert (fresh.player1_score, fresh.player2_score) == (2, 2)

    # Il 5° rack DEVE essere rifiutato
    with pytest.raises(ValueError, match="limite|rack totali"):
        ScoringService.add_rack_for_player(match.id, match.player1_id, match.player1_id)

    # Lo score resta 2-2 (nessun rack persistito post-rollback)
    fresh = db.session.get(Match, match.id)
    assert (fresh.player1_score, fresh.player2_score) == (2, 2)
    active_racks = Rack.query.filter_by(match_id=match.id, is_deleted=False).count()
    assert active_racks == 4


@pytest.mark.integration
def test_player_path_respects_round_override_adr_027(
    director: User, players_by_name: Dict[str, User], db_session
):
    """ADR-027: scoring legge match.distance_config, non gara.distance.

    Gara default (race-to 5), turno 3 override a (4 esatti). Il 5° rack su un
    match del turno 3 deve essere rifiutato indipendentemente dal default
    della gara.
    """
    from models.competition.round_configuration import RoundConfiguration

    gara = _create_random_gara(director.id, rounds_count=3, distance=5, is_race_to=True)
    # Override prima dell'apertura iscrizioni (status=setup richiesto).
    override = RoundConfiguration(
        gara_id=gara.id, round_number=3, distance=4, is_race_to=False
    )
    db.session.add(override)
    db.session.commit()

    _inscribe_all(gara, list(players_by_name.values()))
    RoundService.start_first_round(gara.id)

    match_t3 = (
        Match.query.filter_by(gara_id=gara.id, round_number=3)
        .filter(Match.player2_id.isnot(None))
        .first()
    )
    assert match_t3 is not None
    # Porta a 2-2
    ScoringService.add_rack_for_player(
        match_t3.id, match_t3.player1_id, match_t3.player1_id
    )
    ScoringService.add_rack_for_player(
        match_t3.id, match_t3.player2_id, match_t3.player2_id
    )
    ScoringService.add_rack_for_player(
        match_t3.id, match_t3.player1_id, match_t3.player1_id
    )
    ScoringService.add_rack_for_player(
        match_t3.id, match_t3.player2_id, match_t3.player2_id
    )

    with pytest.raises(ValueError):
        ScoringService.add_rack_for_player(
            match_t3.id, match_t3.player1_id, match_t3.player1_id
        )


# ────────────────────────────────────────────────────────────────────────
# Bug 4 — Classification system rispettato
# ────────────────────────────────────────────────────────────────────────


def _setup_scenario_with_results(
    director: User,
    players_by_name: Dict[str, User],
    classification_system: str,
    tiebreaker_enabled: bool = False,
) -> Gara:
    """Bypassa matchmaking: crea direttamente i 12 match coi punteggi reali.

    Usato dai test di classifica/SSR per validare il sort indipendentemente
    dal fix anti-rematch.
    """
    gara = _create_random_gara(
        director.id,
        rounds_count=4,
        classification_system=classification_system,
        tiebreaker_enabled=tiebreaker_enabled,
    )
    _inscribe_all(gara, list(players_by_name.values()))
    RoundService.start_first_round(gara.id)

    # Override degli abbinamenti: assegna i match in modo da matchare i nomi
    # reali (potrebbe non corrispondere a quanto generato dal matchmaking,
    # quindi cancelliamo i match esistenti e creiamo quelli scriptati).
    Match.query.filter_by(gara_id=gara.id).delete()
    db.session.commit()

    for round_num, p1_name, p2_name, p1_score, p2_score in SCENARIO_2026_05_20:
        p1 = players_by_name[p1_name]
        p2 = players_by_name[p2_name]
        match = Match(
            gara_id=gara.id,
            round_number=round_num,
            player1_id=p1.id,
            player2_id=p2.id,
            player1_score=p1_score,
            player2_score=p2_score,
            status="completed",
            winner_id=(
                p1.id
                if p1_score > p2_score
                else (p2.id if p2_score > p1_score else None)
            ),
        )
        db.session.add(match)
    # Avanza current_round all'ultimo round dello scenario in modo che
    # l'aggregator processi tutti i turni.
    gara.current_round = max(r for r, *_ in SCENARIO_2026_05_20)
    db.session.commit()
    return gara


@pytest.mark.integration
def test_classification_wins_pietro_above_paolo(
    director: User, players_by_name: Dict[str, User], db_session
):
    """WINS: PIETRO (3W +4) sopra PAOLO (2W +4)."""
    from models.classification.gara_classification import (
        StrategyBasedClassificationService,
    )

    gara = _setup_scenario_with_results(
        director, players_by_name, classification_system="WINS"
    )
    service = StrategyBasedClassificationService()
    result = service.calculate_gara_classification(gara.id)

    by_uid = {e.player_id: e for e in result.entries}
    pietro_pos = by_uid[players_by_name["PIETRO"].id].position
    paolo_pos = by_uid[players_by_name["PAOLO"].id].position
    assert pietro_pos < paolo_pos, (
        f"In modalità WINS, PIETRO (3W) deve precedere PAOLO (2W). "
        f"Posizioni: PIETRO={pietro_pos}, PAOLO={paolo_pos}"
    )


@pytest.mark.integration
def test_classification_rack_paolo_pietro_tied_ssr_visible(
    director: User, players_by_name: Dict[str, User], db_session
):
    """RACK: PAOLO e PIETRO hanno entrambi rack-diff +4 → parimerito visibile
    al gruppamento SSR."""
    from models.classification.gara_classification import (
        StrategyBasedClassificationService,
    )

    gara = _setup_scenario_with_results(
        director,
        players_by_name,
        classification_system="RACK",
        tiebreaker_enabled=True,
    )
    service = StrategyBasedClassificationService()
    result = service.calculate_gara_classification(gara.id)

    by_uid = {e.player_id: e for e in result.entries}
    paolo_entry = by_uid[players_by_name["PAOLO"].id]
    pietro_entry = by_uid[players_by_name["PIETRO"].id]

    # Senza player_id nel sort key, due giocatori con stessa rack-diff e stesso
    # racks_won DOVREBBERO ricevere la stessa position (has_ties=True).
    # Sappiamo dallo scenario: PAOLO racks_won=11 (1+1+4+5), PIETRO racks_won=11
    # (3+3+2+3). Rack-diff entrambi +4. Stessa chiave → stessa position.
    assert paolo_entry.position == pietro_entry.position, (
        f"PAOLO e PIETRO devono essere parimerito (entrambi rack-diff +4): "
        f"PAOLO position={paolo_entry.position}, "
        f"PIETRO position={pietro_entry.position}"
    )


# ────────────────────────────────────────────────────────────────────────
# Bug 3 — Wizard standalone persists classification_system
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_wizard_standalone_persists_classification_system(app, db_session):
    """GaraFormParser (standalone branch) propaga classification_system.

    Test del solo parser (Bug 3 è una riga in `form_parser.py`): construct
    un fake request.form e verifica che il dict restituito contenga la
    chiave attesa. Va oltre la verifica di "default WINS" che esisteva.
    """
    from routes.admin.competition.form_parser import GaraFormParser

    form_fields = {
        "name": "Wizard test RACK",
        "date": (date.today() + timedelta(days=10)).isoformat(),
        "time": "20:00",
        "discipline": "8_ball",
        "distance": "5",
        "rounds_count": "3",
        "min_participants": "4",
        "max_participants": "10",
        "entry_fee": "0",
        "matchmaking_strategy": "amalfi",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "classification_system": "RACK",
    }
    with app.test_request_context(
        "/admin/gara/create_standalone", method="POST", data=form_fields
    ):
        parser = GaraFormParser(campionato=None)
        data = parser.parse()

    assert data["classification_system"] == "RACK"

    # Verifica anche il default quando il campo manca → WINS
    form_no_cs = {k: v for k, v in form_fields.items() if k != "classification_system"}
    with app.test_request_context(
        "/admin/gara/create_standalone", method="POST", data=form_no_cs
    ):
        parser = GaraFormParser(campionato=None)
        data_default = parser.parse()
    assert data_default["classification_system"] == "WINS"
