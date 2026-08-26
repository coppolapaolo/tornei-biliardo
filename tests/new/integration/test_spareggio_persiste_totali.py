# tests/new/integration/test_spareggio_persiste_totali.py
"""Lo spareggio non deve scrivere la differenza nella colonna dei totali.

`SpareggioService` crea le righe di `GaraClassification` mancanti copiandole
dalla classifica di turno. Fino al 2026-08-26 ci copiava
`RoundClassification.ranking_rack_value`, che è il numero **da mostrare in
classifica** e cambia significato con la configurazione: totale nelle gare
RACK, **differenza** in tutte le altre.

Effetto: in una gara a vittorie che passa da uno spareggio SSR,
`GaraClassification.racks_won` finiva per contenere una differenza — valori
negativi compresi. La colonna la legge
`TournamentStatisticsService._racks_won_of` per i «triangoli totali» della
classifica generale di campionato, che quindi mostrava numeri falsi.

Trovato su dati veri: la gara 38 in produzione (a vittorie, con spareggio per
il primo posto) aveva `racks_won` = -7 su un giocatore.

La correzione è `total_racks_value`, che è **sempre** il totale. Le chiavi di
ordinamento continuano a usare `ranking_rack_value`, e devono: per una gara a
vittorie ordinare su `(vittorie, differenza)` è la regola giusta.
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


def _gara_giocata(classification_system):
    """Un turno, due partite da esattamente 5 triangoli.

    I punteggi sono scelti perché totale e differenza **non coincidano mai**:
    con 4–1 il totale è 4 e la differenza 3, con 3–2 sono 3 e 1. Un test in cui
    i due numeri si somigliano non distinguerebbe la correzione dal difetto.
    """
    direttore = _user("DIR")
    a, b, c, d = (_user(n) for n in ("ANNA", "BRUNO", "CARLA", "DARIO"))

    gara = Gara(
        name=f"Gara {uuid.uuid4().hex[:6]}",
        number=1,
        campionato_id=None,
        date=date.today() - timedelta(days=1),
        time=time(20, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=False,  # esattamente 5 triangoli
        rounds_count=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        classification_system=classification_system,
        director_id=direttore.id,
        status=GaraStatus.COMPLETED.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=5),
        inscription_end=utc_now() - timedelta(days=2),
    )
    db.session.add(gara)
    db.session.flush()

    for order, user in enumerate((a, b, c, d), start=1):
        db.session.add(
            Inscription(gara_id=gara.id, user_id=user.id, initial_order=order)
        )
    db.session.flush()

    for vincitore, perdente, punti_v, punti_p in ((a, b, 4, 1), (c, d, 3, 2)):
        db.session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=vincitore.id,
                player2_id=perdente.id,
                player1_score=punti_v,
                player2_score=punti_p,
                winner_id=vincitore.id,
                status=MatchStatus.CONFIRMED_BY_BOTH.value,
                ended_at=utc_now() - timedelta(days=1),
            )
        )
    db.session.flush()

    StrategyBasedClassificationService().calculate_round_classification(gara.id, 1)
    db.session.commit()
    return gara, {"anna": a, "bruno": b, "carla": c, "dario": d}


def _riga(gara_id, user_id):
    return GaraClassification.query.filter_by(gara_id=gara_id, user_id=user_id).first()


@pytest.mark.parametrize("scrittura", ["save_ssr_scores", "apply_final_positions"])
def test_gara_a_vittorie_persiste_il_totale_non_la_differenza(
    app, db_session, scrittura
):
    """Il caso che ha prodotto `racks_won = -7` in produzione.

    Entrambi i punti che creano una `GaraClassification` dentro lo spareggio
    vanno verificati: la correzione a uno solo dei due lascerebbe il difetto
    vivo sull'altro, che è esattamente com'è sopravvissuto finora.
    """
    gara, p = _gara_giocata("WINS")

    if scrittura == "save_ssr_scores":
        ok, messaggio = SpareggioService.save_ssr_scores(
            gara.id, {p["anna"].id: 2, p["carla"].id: 1}
        )
    else:
        ok, messaggio = SpareggioService.apply_final_positions(gara.id)
    assert ok, messaggio
    db.session.commit()

    anna = _riga(gara.id, p["anna"].id)
    assert anna is not None
    assert anna.racks_won == 4, "totale dei triangoli vinti (4–1), non la differenza"
    assert anna.rack_difference == 3

    if scrittura == "apply_final_positions":
        # Questo percorso crea la riga di *tutti*, non solo di chi ha tirato:
        # è lì che si vedrebbe un totale negativo.
        bruno = _riga(gara.id, p["bruno"].id)
        assert bruno is not None
        assert bruno.racks_won == 1
        assert bruno.rack_difference == -3
        assert bruno.racks_won >= 0, "un totale di triangoli non può essere negativo"


def test_gara_a_triangoli_continua_a_persistere_il_totale(app, db_session):
    """Il controllo opposto: nelle gare RACK il comportamento non cambia.

    Lì `ranking_rack_value` restituiva già il totale, quindi una correzione che
    rompesse questo caso avrebbe scambiato un difetto con un altro.
    """
    gara, p = _gara_giocata("RACK")

    ok, messaggio = SpareggioService.apply_final_positions(gara.id)
    assert ok, messaggio
    db.session.commit()

    assert _riga(gara.id, p["anna"].id).racks_won == 4
    assert _riga(gara.id, p["carla"].id).racks_won == 3
    assert _riga(gara.id, p["dario"].id).racks_won == 2


def test_total_racks_value_e_ranking_rack_value_divergono_solo_dove_devono(
    app, db_session
):
    """Le due property rispondono a due domande diverse, e il test lo fissa.

    `ranking_rack_value` dipende dalla configurazione perché deve: è il numero
    mostrato in classifica. `total_racks_value` non ci dipende, perché «quanti
    triangoli ha vinto» non è una questione di configurazione.
    """
    gara, p = _gara_giocata("WINS")
    riga = RoundClassification.query.filter_by(
        gara_id=gara.id, user_id=p["anna"].id, round_number=1
    ).first()

    assert riga.total_racks_value == 4  # totale, sempre
    assert riga.ranking_rack_value == 3  # differenza: la gara è a vittorie

    gara.classification_system = "RACK"
    db.session.flush()
    db.session.expire(riga)

    assert riga.total_racks_value == 4  # invariato
    assert riga.ranking_rack_value == 4  # ora coincidono: la gara è a triangoli


def test_total_racks_value_sulle_righe_pre_separazione(app, db_session):
    """`racks_won` NULL: nelle gare RACK il totale stava in `rack_difference`.

    Altrove non è ricostruibile dalle colonne e si restituisce 0, non la
    differenza — sommare differenze chiamandole totali è la issue #89.
    """
    gara, p = _gara_giocata("WINS")
    riga = RoundClassification.query.filter_by(
        gara_id=gara.id, user_id=p["anna"].id, round_number=1
    ).first()
    riga.racks_won = None
    db.session.flush()

    assert riga.total_racks_value == 0

    gara.classification_system = "RACK"
    db.session.flush()
    db.session.expire(riga)

    assert riga.total_racks_value == 3  # il valore rimasto in `rack_difference`
