"""I giocatori di un campionato si contano una volta sola.

`calculate_campionato_statistics` conta chi ha partecipato al campionato e
chi è iscritto adesso a una gara con le iscrizioni aperte. Chi gioca tre gare
è un giocatore, non tre.

Il conteggio era `query(distinct(user_id)).count()`, che SQLAlchemy 2.1
segnala (`SAWarning`: un `distinct()` di colonna fuori da un'aggregazione).
Riscritto come `count(distinct(user_id))` durante il passaggio alla 2.1
(settembre 2026). Nessun test verificava quei numeri: questo li fissa prima
del cambio, così un conteggio che raddoppia non passa in silenzio.
"""

from __future__ import annotations

import uuid
from datetime import date, time

from models import Gara, Inscription, User
from models.campionato.models import Campionato
from models.campionato.statistics_service import TournamentStatisticsService
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import ClassificationSystem, GaraStatus
from models.user.role_enum import UserRole


def _utente(db_session, ruolo: str = UserRole.PLAYER.value) -> User:
    suffix = str(uuid.uuid4())[:8]
    utente = User(username=f"u_{suffix}", email=f"u_{suffix}@test.com", role=ruolo)
    utente.set_password("x")
    db_session.add(utente)
    db_session.flush()
    return utente


def _gara(db_session, campionato: Campionato, direttore: User, numero: int, stato: str):
    gara = Gara(
        number=numero,
        name=f"Gara {numero}",
        date=date(2026, 1, numero),
        time=time(18, 0),
        discipline="9_ball",
        distance=3,
        is_race_to=True,
        director_id=direttore.id,
        campionato_id=campionato.id,
        rounds_count=1,
        min_participants=2,
        matchmaking_strategy=MatchmakingStrategy.RANDOM.value,
        classification_system=ClassificationSystem.WINS.value,
        status=stato,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def test_chi_gioca_piu_gare_conta_una_volta(db_session):
    direttore = _utente(db_session, UserRole.DIRECTOR.value)
    campionato = Campionato(
        name=f"Campionato {uuid.uuid4().hex[:8]}",
        campionato_type=MatchmakingStrategy.RANDOM.value,
        default_classification_system=ClassificationSystem.WINS.value,
        planned_gare_count=3,
    )
    db_session.add(campionato)
    db_session.flush()

    conclusa = _gara(db_session, campionato, direttore, 1, GaraStatus.COMPLETED.value)
    aperta = _gara(db_session, campionato, direttore, 2, GaraStatus.INSCRIPTION.value)

    anna, bruno, carla = (_utente(db_session) for _ in range(3))
    # Anna e Bruno giocano la prima; Anna e Carla sono iscritte alla seconda.
    for gara, giocatori in ((conclusa, (anna, bruno)), (aperta, (anna, carla))):
        for giocatore in giocatori:
            db_session.add(Inscription(user_id=giocatore.id, gara_id=gara.id))
    db_session.commit()

    statistiche = TournamentStatisticsService().calculate_campionato_statistics(
        campionato.id
    )

    assert statistiche["total_unique_players"] == 3
    assert statistiche["currently_inscribed_players"] == 2
