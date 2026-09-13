"""Il tavolo di una partita chiusa passa alla partita in attesa, da ogni strada.

Regressione del 2026-09-13, trovata dall'utente: il direttore che gioca segna
i triangoli della sua partita dal segnapunti; alla distanza la partita si
chiude, il tavolo risulta libero, ma la partita in attesa resta senza tavolo.

Il direttore, e chi perde quando segna il triangolo decisivo, danno la seconda
firma dentro `ScoringService.add_rack_for_player`: la partita si chiude in
`_complete_match_after_confirmation`, che fino a oggi scriveva lo stato finale
ma non liberava il tavolo. Lo faceva solo la conferma esplicita
(`MatchService.confirm_match_result`), quindi le altre strade lo perdevano.

Gara con due tavoli e tre partite: due ai tavoli, una in attesa.
"""

from datetime import date

import pytest

from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User

pytestmark = pytest.mark.unit


@pytest.fixture
def sala(db_session):
    gara = Gara(
        number=1,
        name="Gara coi tavoli",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        min_participants=4,
    )
    gara.available_tables = '["1", "2"]'
    db_session.add(gara)
    db_session.commit()
    giocatori = []
    for n in range(6):
        u = User(username=f"tav_{n}", email=f"tav_{n}@test.local", password_hash="x")
        db_session.add(u)
        giocatori.append(u)
    db_session.commit()

    def partita(p1, p2, tavolo):
        m = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatori[p1].id,
            player2_id=giocatori[p2].id,
            table_assignment=tavolo,
            status=(MatchStatus.PLAYING.value if tavolo else MatchStatus.PENDING.value),
            player1_score=0,
            player2_score=0,
        )
        db_session.add(m)
        db_session.commit()
        return m.id

    return {
        "giocatori": [g.id for g in giocatori],
        "al_tavolo": partita(0, 1, "1"),
        "altra": partita(2, 3, "2"),
        "in_attesa": partita(4, 5, None),
    }


def _verifica_passaggio(db_session, sala):
    db_session.expire_all()
    chiusa = db_session.get(Match, sala["al_tavolo"])
    attesa = db_session.get(Match, sala["in_attesa"])
    assert MatchStatus.is_finished(chiusa.status)
    assert chiusa.table_assignment is None
    assert attesa.table_assignment == "1"
    assert attesa.status == MatchStatus.PLAYING.value


def test_il_direttore_che_gioca_chiude_la_sua_partita_dal_segnapunti(db_session, sala):
    from models.match.scoring_service import ScoringService

    p1 = sala["giocatori"][0]
    for _ in range(3):
        ScoringService.add_rack_for_player(
            sala["al_tavolo"], user_id=p1, winner_id=p1, authoritative=True
        )
    _verifica_passaggio(db_session, sala)


def test_chi_perde_segna_il_triangolo_decisivo(db_session, sala):
    from models.match.scoring_service import ScoringService

    vince, perde = sala["giocatori"][0], sala["giocatori"][1]
    for _ in range(2):
        ScoringService.add_rack_for_player(
            sala["al_tavolo"], user_id=vince, winner_id=vince
        )
    ScoringService.add_rack_for_player(
        sala["al_tavolo"], user_id=perde, winner_id=vince
    )
    _verifica_passaggio(db_session, sala)


def test_la_conferma_esplicita_di_chi_perde(db_session, sala):
    from models.match.match_service import MatchService
    from models.match.scoring_service import ScoringService

    vince, perde = sala["giocatori"][0], sala["giocatori"][1]
    for _ in range(3):
        ScoringService.add_rack_for_player(
            sala["al_tavolo"], user_id=vince, winner_id=vince
        )
    db_session.expire_all()
    assert db_session.get(Match, sala["in_attesa"]).table_assignment is None
    MatchService.confirm_match_result(sala["al_tavolo"], perde)
    _verifica_passaggio(db_session, sala)


def test_il_direttore_segna_la_partita_altrui_dalla_card(db_session, sala):
    from models.match.rack_service import RackService

    RackService.set_match_result_direct(sala["al_tavolo"], 3, 1, parziale=True)
    _verifica_passaggio(db_session, sala)


def test_il_direttore_valida_una_partita_arrivata_alla_distanza(db_session, sala):
    from models.match.scoring_service import ScoringService
    from models.match.validation_service import MatchValidationService

    vince = sala["giocatori"][0]
    for _ in range(3):
        ScoringService.add_rack_for_player(
            sala["al_tavolo"], user_id=vince, winner_id=vince
        )
    MatchValidationService.validate_and_complete(sala["al_tavolo"])
    _verifica_passaggio(db_session, sala)
