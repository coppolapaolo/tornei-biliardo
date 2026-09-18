"""All'avvio di un turno con la X ogni tavolo va a una partita sola.

Gara 3 della Ronin Cup, 16/09/2026: all'avvio del primo turno il primo tavolo
della lista è finito a due partite e l'ultimo è rimasto vuoto.

Il meccanismo: la X si chiude da sola *mentre* il turno sta nascendo
(`create_matches_from_pairings` → `to_completed`), e ogni chiusura fa scattare
il riassegnamento dei tavoli liberi alle partite in attesa. Le partite create
**prima** della X ricevono quindi un tavolo già lì. Poi
`assign_tables_to_round` scorreva la lista dei tavoli dall'inizio senza
guardare quelli occupati: la prima partita ancora senza tavolo riceveva di
nuovo il primo.

Il sintomo dipende dalla posizione della X fra gli abbinamenti: in testa non
succede niente, in coda nemmeno. Per questo il test la mette in mezzo.
"""

from collections import Counter
from datetime import date

import pytest

from models import BilliardHall, Gara, Match, User
from models.competition.round_creation import create_matches_from_pairings
from models.match.table_assignment_service import TableAssignmentService
from models.matchmaking.strategies.base import Pairing
from models.status_enum import Discipline, GaraStatus, MatchStatus

TAVOLI = ["1", "2", "3", "4"]


@pytest.fixture
def gara(db_session):
    venue = BilliardHall(
        name="Sala della X", number_of_tables=4, is_active=True, verified=True
    )
    venue.set_table_names(TAVOLI)
    db_session.add(venue)
    gara = Gara(
        number=1,
        name="Gara con la X",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        location=venue.name,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        min_participants=6,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


@pytest.fixture
def giocatori(db_session):
    utenti = []
    for i in range(9):
        utente = User(
            username=f"giocatore{i + 1}",
            email=f"giocatore{i + 1}@test.com",
            password_hash="test",
        )
        db_session.add(utente)
        utenti.append(utente)
    db_session.commit()
    return [u.id for u in utenti]


def _abbinamenti(giocatori, posizione_x):
    """Quattro partite e una X, con la X alla posizione richiesta."""
    coppie = [Pairing(players=(giocatori[i], giocatori[i + 1])) for i in range(0, 8, 2)]
    coppie.insert(posizione_x, Pairing(players=(giocatori[8],), is_bye=True))
    return coppie


@pytest.mark.unit
@pytest.mark.parametrize("posizione_x", [0, 1, 2, 3, 4])
def test_ogni_tavolo_a_una_partita_sola(db_session, gara, giocatori, posizione_x):
    create_matches_from_pairings(
        gara=gara,
        pairings=_abbinamenti(giocatori, posizione_x),
        round_number=1,
        round_distance=5,
    )
    TableAssignmentService.assign_tables_to_round(gara.id, round_number=1)

    in_corso = Match.query.filter_by(
        gara_id=gara.id, status=MatchStatus.PLAYING.value
    ).all()
    assegnati = Counter(m.table_assignment for m in in_corso)

    doppi = {tavolo: n for tavolo, n in assegnati.items() if n > 1}
    assert not doppi, f"tavoli assegnati a più partite: {doppi}"
    # Quattro partite, quattro tavoli: nessuno resta vuoto.
    assert sorted(assegnati) == TAVOLI
