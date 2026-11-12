"""Due che hanno giocato non si reincontrano, comunque si sia chiusa la partita.

Produzione, gara 54 dell'11/11/2026: Amalfi a 14 iscritti, anti-reincontro
attivo, e al turno 3 è uscita di nuovo la partita del turno 1. Quella partita
l'aveva segnata dal segnapunti il direttore che ci giocava.

L'anti-reincontro leggeva solo la tabella `player_encounter`, e quella riga la
scriveva una strada sola: `MatchStateService.to_completed`. La doppia firma dei
giocatori chiude la partita da un'altra parte
(`_complete_match_after_confirmation`) e la riga non nasceva: per
l'abbinamento quei due non si erano mai visti.
"""

from datetime import date

import pytest

from models.classification.encounter_service import PlayerEncounterService
from models.classification.models import PlayerEncounter
from models.competition.models import Gara
from models.match.models import Match
from models.match.match_service import MatchService
from models.match.scoring_service import ScoringService
from models.match.state_service import MatchStateService
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User

pytestmark = pytest.mark.unit


@pytest.fixture
def partita(db_session):
    """Una partita «esattamente 2 triangoli» fra due giocatori, in corso."""
    gara = Gara(
        number=1,
        name="Gara degli incontri",
        date=date.today(),
        discipline=Discipline.NINE_BALL.value,
        distance=2,
        is_race_to=False,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        min_participants=4,
    )
    db_session.add(gara)
    a = User(username="inc_a", email="inc_a@test.local", password_hash="x")
    b = User(username="inc_b", email="inc_b@test.local", password_hash="x")
    db_session.add_all([a, b])
    db_session.commit()
    m = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=a.id,
        player2_id=b.id,
        status=MatchStatus.PLAYING.value,
        player1_score=0,
        player2_score=0,
    )
    db_session.add(m)
    db_session.commit()
    return {"gara": gara.id, "id": m.id, "a": a.id, "b": b.id}


def _si_sono_incontrati(db_session, partita) -> bool:
    db_session.expire_all()
    assert MatchStatus.is_finished(db_session.get(Match, partita["id"]).status)
    matrice = PlayerEncounterService.get_encounter_matrix(partita["gara"])
    # La riga agli atti nasce alla chiusura, non solo la lettura delle partite.
    assert PlayerEncounter.have_played(partita["gara"], partita["a"], partita["b"])
    return bool(matrice.get((partita["a"], partita["b"]))) and bool(
        matrice.get((partita["b"], partita["a"]))
    )


def test_chi_perde_segna_il_triangolo_decisivo(db_session, partita):
    p = partita
    ScoringService.add_rack_for_player(p["id"], p["a"], p["a"])
    ScoringService.add_rack_for_player(p["id"], p["b"], p["a"])
    assert _si_sono_incontrati(db_session, p)


def test_chi_perde_conferma_dopo(db_session, partita):
    p = partita
    ScoringService.add_rack_for_player(p["id"], p["a"], p["a"])
    ScoringService.add_rack_for_player(p["id"], p["a"], p["a"])
    MatchService.confirm_match_result(p["id"], p["b"])
    assert _si_sono_incontrati(db_session, p)


def test_il_direttore_che_gioca_segna_un_pareggio(db_session, partita):
    """Il caso della gara 54: 3-3 segnato dal direttore al tavolo."""
    p = partita
    ScoringService.add_rack_for_player(p["id"], p["a"], p["a"], authoritative=True)
    ScoringService.add_rack_for_player(p["id"], p["a"], p["b"], authoritative=True)
    assert _si_sono_incontrati(db_session, p)


def test_il_pareggio_firmato_dai_due(db_session, partita):
    p = partita
    ScoringService.add_rack_for_player(p["id"], p["a"], p["a"])
    ScoringService.add_rack_for_player(p["id"], p["a"], p["b"])
    MatchService.confirm_match_result(p["id"], p["a"])
    MatchService.confirm_match_result(p["id"], p["b"])
    assert _si_sono_incontrati(db_session, p)


def test_la_chiusura_del_direttore(db_session, partita):
    p = partita
    ScoringService.add_rack_for_player(p["id"], p["a"], p["a"])
    ScoringService.add_rack_for_player(p["id"], p["a"], p["a"])
    MatchStateService.to_completed(p["id"])
    db_session.commit()
    assert _si_sono_incontrati(db_session, p)


def test_una_partita_conclusa_senza_riga_conta_lo_stesso(db_session, partita):
    """Le gare già in corso: partite chiuse prima della correzione."""
    p = partita
    m = db_session.get(Match, p["id"])
    m.player1_score, m.player2_score = 1, 1
    m.status = MatchStatus.CONFIRMED_BY_BOTH.value
    db_session.commit()
    assert not PlayerEncounter.have_played(p["gara"], p["a"], p["b"])

    matrice = PlayerEncounterService.get_encounter_matrix(p["gara"])
    assert matrice.get((p["a"], p["b"])) and matrice.get((p["b"], p["a"]))


def test_una_partita_in_corso_non_e_ancora_un_incontro(db_session, partita):
    p = partita
    assert PlayerEncounterService.get_encounter_matrix(p["gara"]) == {}


def test_la_matrice_non_resta_in_memoria(db_session, partita):
    """Tre processi in produzione: una matrice in cache sarebbe vecchia."""
    p = partita
    assert PlayerEncounterService.get_encounter_matrix(p["gara"]) == {}
    m = db_session.get(Match, p["id"])
    m.status = MatchStatus.CLOSED_UNILATERALLY.value
    db_session.commit()
    assert PlayerEncounterService.get_encounter_matrix(p["gara"]) != {}
