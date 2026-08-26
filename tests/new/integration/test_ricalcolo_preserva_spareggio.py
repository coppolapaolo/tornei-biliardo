# tests/new/integration/test_ricalcolo_preserva_spareggio.py
"""Un ricalcolo delle classifiche non deve disfare lo spareggio già giocato.

`apply_final_positions` scrive l'ordine finale — spareggio compreso — in
`GaraClassification` **e** lo rispecchia in `RoundClassification.position`
dell'ultimo turno, perché è quella la classifica che la pagina della gara
mostra.

Un ricalcolo dei turni riscrive quelle righe da zero, e lo specchio torna
all'ordine puro del turno: `(vittorie, differenza, posizione precedente)`. Lo
spareggio sparisce dalla vista, e ricompare un pari merito che era già stato
sciolto sul tavolo.

`calculate_gara_classification` una difesa ce l'aveva già — rilegge i punteggi
registrati invece di pretenderli dal chiamante — ma difende **la sua** tabella.
La copia mostrata all'utente restava indietro.

Successo in produzione il 2026-08-26 sulla gara 38, dopo una riassegnazione di
partecipazione (ADR-048): in cima alla classifica compariva il giocatore con il
punteggio di spareggio **più basso**.
"""

import uuid
from datetime import date, time, timedelta

import pytest

from models import db
from models.base import utc_now
from models.classification.gara_classification import (
    StrategyBasedClassificationService,
)
from models.classification.models import GaraClassification, RoundClassification
from models.competition.models import Gara, Inscription
from models.competition.spareggio_service import SpareggioService
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _user(name):
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{name}_{suffix}",
        email=f"{name.lower()}_{suffix}@example.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("secret123")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def gara_con_spareggio(app, db_session):
    """Due giocatori identici per vittorie e differenza, separati dallo spareggio.

    Un turno solo, due partite: ANNA e CARLA vincono entrambe 4–1, quindi
    hanno gli stessi numeri e nessun criterio di merito le distingue. È
    esattamente la condizione in cui lo spareggio è l'**unico** ordinatore, e
    quindi l'unica in cui perderlo si vede.
    """
    direttore = _user("DIR")
    anna, bruno, carla, dario = (_user(n) for n in ("ANNA", "BRUNO", "CARLA", "DARIO"))

    gara = Gara(
        name=f"Gara {uuid.uuid4().hex[:6]}",
        number=1,
        campionato_id=None,
        date=date.today() - timedelta(days=1),
        time=time(20, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=False,
        rounds_count=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        classification_system="WINS",
        director_id=direttore.id,
        status=GaraStatus.COMPLETED.value,
        current_round=1,
        tiebreaker_until_position=3,
        inscription_start=utc_now() - timedelta(days=5),
        inscription_end=utc_now() - timedelta(days=2),
    )
    db.session.add(gara)
    db.session.flush()

    # `initial_order` decide chi viene prima a pari merito: ANNA è davanti, così
    # se lo spareggio andasse perduto la classifica ricadrebbe su di lei — ed è
    # CARLA a vincerlo. Senza questa asimmetria il test passerebbe per caso.
    for order, user in enumerate((anna, bruno, carla, dario), start=1):
        db.session.add(
            Inscription(gara_id=gara.id, user_id=user.id, initial_order=order)
        )
    db.session.flush()

    for vincitore, perdente in ((anna, bruno), (carla, dario)):
        db.session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=vincitore.id,
                player2_id=perdente.id,
                player1_score=4,
                player2_score=1,
                winner_id=vincitore.id,
                status=MatchStatus.CONFIRMED_BY_BOTH.value,
                ended_at=utc_now() - timedelta(days=1),
            )
        )
    db.session.flush()

    servizio = StrategyBasedClassificationService()
    servizio.calculate_round_classification(gara.id, 1)
    servizio.calculate_gara_classification(gara.id)

    # Lo spareggio: CARLA batte ANNA.
    ok, messaggio = SpareggioService.save_ssr_scores_for_group(
        gara.id, 1, {carla.id: 1, anna.id: 0}
    )
    assert ok, messaggio
    ok, messaggio = SpareggioService.finalize_classification(gara.id)
    assert ok, messaggio
    db.session.commit()

    return gara, {"anna": anna, "bruno": bruno, "carla": carla, "dario": dario}


def _posizione_di_turno(gara_id, user_id):
    riga = RoundClassification.query.filter_by(
        gara_id=gara_id, round_number=1, user_id=user_id
    ).first()
    return riga.position if riga else None


def _posizione_finale(gara_id, user_id):
    riga = GaraClassification.query.filter_by(gara_id=gara_id, user_id=user_id).first()
    return riga.position if riga else None


def test_lo_spareggio_decide_prima_del_ricalcolo(gara_con_spareggio):
    """Punto di partenza: CARLA è prima in entrambe le classifiche."""
    gara, p = gara_con_spareggio

    assert _posizione_finale(gara.id, p["carla"].id) == 1
    assert _posizione_di_turno(gara.id, p["carla"].id) == 1


def test_il_ricalcolo_non_riporta_in_cima_chi_ha_perso_lo_spareggio(
    gara_con_spareggio,
):
    """Il difetto: dopo un ricalcolo la pagina mostrava di nuovo ANNA prima."""
    gara, p = gara_con_spareggio

    servizio = StrategyBasedClassificationService()
    servizio.calculate_round_classification(gara.id, 1)
    servizio.calculate_gara_classification(gara.id)
    SpareggioService.reapply_final_positions_if_resolved(gara.id)
    db.session.commit()

    assert _posizione_di_turno(gara.id, p["carla"].id) == 1
    assert _posizione_di_turno(gara.id, p["anna"].id) == 2
    assert _posizione_finale(gara.id, p["carla"].id) == 1


def test_la_riassegnazione_di_una_partecipazione_lo_conserva(gara_con_spareggio):
    """Il percorso reale: ADR-048 su una gara con spareggio.

    Sostituire DARIO — che nello spareggio non c'entra — non deve toccare
    l'ordine deciso fra ANNA e CARLA.
    """
    from models.competition.participant_reassign_service import (
        GaraParticipantReassignService,
    )

    gara, p = gara_con_spareggio
    admin = User(
        username=f"admin_{uuid.uuid4().hex[:8]}",
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        role=UserRole.ADMIN.value,
    )
    admin.set_password("secret123")
    subentrato = _user("ELIA")
    db.session.add(admin)
    db.session.flush()
    db.session.commit()

    GaraParticipantReassignService.reassign(
        gara_id=gara.id,
        source_id=p["dario"].id,
        target_id=subentrato.id,
        performed_by_id=admin.id,
    )
    db.session.commit()

    assert _posizione_di_turno(gara.id, p["carla"].id) == 1
    assert _posizione_di_turno(gara.id, p["anna"].id) == 2


def test_una_gara_senza_spareggio_non_passa_dalla_finalizzazione(app, db_session):
    """La riapplicazione è mirata, non un passaggio obbligato per tutti.

    `apply_final_positions` assegna posizioni condivise ai pari merito: farci
    passare ogni gara ricalcolata sarebbe un cambiamento di comportamento per
    gare che uno spareggio non l'hanno mai avuto.
    """
    gara = Gara(
        name=f"Gara {uuid.uuid4().hex[:6]}",
        number=1,
        date=date.today(),
        time=time(20, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        rounds_count=1,
        min_participants=2,
        matchmaking_strategy="amalfi",
        director_id=_user("DIR2").id,
        status=GaraStatus.COMPLETED.value,
        current_round=1,
    )
    db.session.add(gara)
    db.session.flush()

    assert SpareggioService.has_recorded_ssr(gara.id) is False
    assert SpareggioService.reapply_final_positions_if_resolved(gara.id) is False


def test_uno_zero_registrato_non_e_uno_spareggio(gara_con_spareggio):
    """Coerente con `_recorded_spot_shot`: solo i punteggi > 0 contano.

    Sulla colonna uno zero è indistinguibile da un'assenza, e i due punti che
    la interrogano devono usare lo stesso criterio — altrimenti uno crede che
    lo spareggio ci sia e l'altro no.
    """
    gara, p = gara_con_spareggio

    for riga in GaraClassification.query.filter_by(gara_id=gara.id).all():
        riga.spot_shot_wins = 0
    db.session.flush()

    assert SpareggioService.has_recorded_ssr(gara.id) is False
