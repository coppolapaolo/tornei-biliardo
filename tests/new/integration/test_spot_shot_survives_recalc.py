# tests/new/integration/test_spot_shot_survives_recalc.py
"""Il risultato dello spareggio deve sopravvivere a un ricalcolo.

Nelle gare a triangoli (`RACK`) due giocatori con lo stesso totale sono separati
dallo **Spot Shot Rally**, e il risultato vive in
`gara_classification.spot_shot_wins`. È un fatto — qualcuno ha tirato — non un
derivato ricostruibile dalle partite.

`calculate_gara_classification` però ricostruisce quelle righe con DELETE+INSERT
partendo dalla classifica di turno, e `round_classification` **non ha** una
colonna per l'SSR: il dato non sopravvive al giro di andata e ritorno. Chiunque
ricalcoli — la correzione manuale di un risultato, lo spostamento di una
partecipazione (ADR-048) — azzera lo spareggio e fa ricomparire un pari merito
che era stato risolto sul tavolo.
"""

import uuid
from datetime import date, time, timedelta

import pytest

from models import db
from models.base import utc_now
from models.classification.gara_classification import (
    StrategyBasedClassificationService,
)
from models.classification.models import GaraClassification
from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _user():
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"p_{suffix}",
        email=f"p_{suffix}@example.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("secret123")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def gara_a_triangoli(app, db_session):
    """Gara RACK conclusa: due giocatori a pari triangoli, separati dall'SSR."""
    gara = Gara(
        name="Prova a triangoli",
        number=1,
        date=date.today() - timedelta(days=3),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="random",
        classification_system="RACK",
        status=GaraStatus.COMPLETED.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=10),
        inscription_end=utc_now() - timedelta(days=8),
    )
    db.session.add(gara)
    db.session.flush()

    a, b, c, d = _user(), _user(), _user(), _user()
    for order, u in enumerate((a, b, c, d), start=1):
        db.session.add(Inscription(gara_id=gara.id, user_id=u.id, initial_order=order))

    # a e b vincono 5-2 contro c e d: stessi triangoli, pari merito perfetto.
    for vincitore, perdente in ((a, c), (b, d)):
        db.session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=vincitore.id,
                player2_id=perdente.id,
                player1_score=5,
                player2_score=2,
                winner_id=vincitore.id,
                status=MatchStatus.CONFIRMED_BY_BOTH.value,
                ended_at=utc_now() - timedelta(days=3),
            )
        )
    db.session.flush()

    service = StrategyBasedClassificationService()
    service.calculate_round_classification(gara.id, 1)
    service.calculate_gara_classification(gara.id)

    # Lo spareggio si gioca sul tavolo e si registra qui: `a` ha tirato meglio.
    for utente, punteggio in ((a, 7), (b, 3)):
        riga = GaraClassification.query.filter_by(
            gara_id=gara.id, user_id=utente.id
        ).first()
        riga.spot_shot_wins = punteggio
    db.session.commit()

    return {"gara": gara, "a": a, "b": b}


def test_lo_spareggio_sopravvive_al_ricalcolo(gara_a_triangoli, db_session):
    gara = gara_a_triangoli["gara"]
    a_id, b_id = gara_a_triangoli["a"].id, gara_a_triangoli["b"].id

    service = StrategyBasedClassificationService()
    service.calculate_round_classification(gara.id, 1)
    service.calculate_gara_classification(gara.id)
    db.session.commit()

    per_utente = {
        r.user_id: r for r in GaraClassification.query.filter_by(gara_id=gara.id).all()
    }
    assert per_utente[a_id].spot_shot_wins == 7, (
        "il ricalcolo ha azzerato lo Spot Shot Rally: un risultato tirato sul "
        "tavolo non si ricostruisce dalle partite"
    )
    assert per_utente[b_id].spot_shot_wins == 3


def test_lo_spareggio_continua_a_separare_il_pari_merito(gara_a_triangoli, db_session):
    """Non basta conservare il numero: deve restare il criterio di ordinamento."""
    gara = gara_a_triangoli["gara"]
    a_id, b_id = gara_a_triangoli["a"].id, gara_a_triangoli["b"].id

    service = StrategyBasedClassificationService()
    service.calculate_round_classification(gara.id, 1)
    service.calculate_gara_classification(gara.id)
    db.session.commit()

    posizioni = {
        r.user_id: r.position
        for r in GaraClassification.query.filter_by(gara_id=gara.id).all()
    }
    assert posizioni[a_id] < posizioni[b_id], (
        "chi ha vinto lo spareggio deve restare davanti: se le posizioni "
        "pareggiano, il ricalcolo ha annullato il risultato del tavolo"
    )
