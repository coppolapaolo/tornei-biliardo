"""Il primo abbinamento proposto dal campionato alle sue gare (ADR-075).

Il campionato dice una volta come si abbina il turno 1 di ogni gara —
casuale, sul rating, sulla classifica del campionato — e le gare lo ricevono
quando nascono, come i dispari e i turni. Girone all'italiana e Random
sorteggiano sempre (`STRATEGY_CONSTRAINTS`): a loro la proposta arriva come
sorteggio, invece di far rifiutare la gara. Il percorso intero, con una gara
giocata e la seconda che parte dalla classifica, è in
`tests/new/e2e/test_campionato_e2e_primo_turno_da_classifica.py`.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.campionato.proposte import CAMPI_PROPOSTI, proposta
from models.competition.services import GaraService
from models.matchmaking.configuration import (
    FirstRoundPolicy,
    MatchmakingStrategy,
    first_round_policy_for_strategy,
)
from models.storia.regolamento import CAMPI_DEL_CAMPIONATO

CLASSIFICA = FirstRoundPolicy.CLASSIFICATION.value
CASUALE = FirstRoundPolicy.RANDOM.value


def _campionato(tipo=MatchmakingStrategy.AMALFI.value, **extra) -> Campionato:
    camp = Campionato(
        name=f"Lunedì {uuid.uuid4().hex[:6]}",
        campionato_type=tipo,
        default_classification_system="WINS",
        is_active=True,
        **extra,
    )
    db.session.add(camp)
    db.session.commit()
    return camp


def _gara(camp, numero=1, **extra):
    return GaraService.create_gara(
        campionato_id=camp.id,
        number=numero,
        name=f"Gara {numero}",
        date=date.today() + timedelta(days=7 * numero),
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        matchmaking_strategy=extra.pop("matchmaking_strategy", camp.campionato_type),
        odd_number_policy="bye",
        rounds_count=3,
        **extra,
    )


@pytest.mark.unit
class TestLaFormaCheLaStrategiaAmmette:
    @pytest.mark.parametrize(
        "strategia",
        [
            MatchmakingStrategy.AMALFI,
            MatchmakingStrategy.DIRECT_ELIMINATION,
            MatchmakingStrategy.DOUBLE_KNOCKOUT,
        ],
    )
    def test_amalfi_e_tabelloni_la_tengono(self, strategia):
        assert first_round_policy_for_strategy(strategia, CLASSIFICA) == CLASSIFICA

    @pytest.mark.parametrize(
        "strategia", [MatchmakingStrategy.ROUND_ROBIN, MatchmakingStrategy.RANDOM]
    )
    def test_girone_e_random_sorteggiano(self, strategia):
        assert first_round_policy_for_strategy(strategia.value, CLASSIFICA) == CASUALE

    def test_niente_o_ignoto_vale_sorteggio(self):
        assert first_round_policy_for_strategy("amalfi", None) == CASUALE
        assert first_round_policy_for_strategy("amalfi", "bogus") == CASUALE
        assert first_round_policy_for_strategy("bogus", CLASSIFICA) == CASUALE


@pytest.mark.unit
class TestLaGaraLaRiceveQuandoNasce:
    def test_amalfi(self, db_session):
        camp = _campionato(default_first_round_policy=CLASSIFICA)
        assert _gara(camp).first_round_policy == CLASSIFICA

    def test_un_campionato_di_prima_resta_casuale(self, db_session):
        """La colonna NULL dei campionati nati prima del 2026-10-16."""
        camp = _campionato()
        camp.default_first_round_policy = None
        db.session.commit()
        assert _gara(camp).first_round_policy == CASUALE

    def test_la_scelta_della_gara_vince(self, db_session):
        camp = _campionato(default_first_round_policy=CLASSIFICA)
        assert _gara(camp, first_round_policy=CASUALE).first_round_policy == CASUALE

    def test_a_piazzamenti_una_serata_a_girone_sorteggia(self, db_session):
        camp = _campionato(default_first_round_policy=CLASSIFICA)
        gara = _gara(camp, matchmaking_strategy=MatchmakingStrategy.ROUND_ROBIN.value)
        assert gara.first_round_policy == CASUALE


@pytest.mark.unit
class TestIlCampionatoLaPropone:
    def test_e_un_valore_proposto_e_scritto_nella_storia(self):
        assert CAMPI_PROPOSTI["default_first_round_policy"] == "first_round_policy"
        assert "default_first_round_policy" in CAMPI_DEL_CAMPIONATO

    def test_alle_gare_non_avviate(self, db_session):
        camp = _campionato()
        gara = _gara(camp)
        righe = proposta(camp, {"default_first_round_policy": (CASUALE, CLASSIFICA)})
        assert [
            (r.gara.id, c.campo_gara, c.nuovo, c.spuntato)
            for r in righe
            for c in r.campi
        ] == [(gara.id, "first_round_policy", CLASSIFICA, True)]

    def test_non_a_una_serata_a_girone(self, db_session):
        camp = _campionato()
        _gara(camp, matchmaking_strategy=MatchmakingStrategy.ROUND_ROBIN.value)
        assert (
            proposta(camp, {"default_first_round_policy": (CASUALE, CLASSIFICA)}) == []
        )


@pytest.mark.unit
class TestLaStoriaLaDiceInParole:
    def test_i_valori(self, app):
        from models.storia.etichette import etichetta, valore

        with app.test_request_context():
            assert (
                valore("first_round_policy", CLASSIFICA)
                == "Basato sulla classifica del campionato"
            )
            assert valore("default_first_round_policy", CASUALE) == "Casuale"
            assert (
                etichetta("default_first_round_policy") == "Primo abbinamento proposto"
            )
