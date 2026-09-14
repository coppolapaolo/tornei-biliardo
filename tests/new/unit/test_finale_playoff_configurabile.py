"""La finale dei playoff: tutto si eredita, tutto si può cambiare.

Una regola sola, decisa il 2026-09-14: ogni opzione della finale — disciplina,
distanza, turni, strategia, dispari, sistema di classifica — nasce **ereditata**
e il direttore la può sovrascrivere. Il vincolo di coerenza è uno, e dipende
dalla modalità della classifica finale (`SPECIFICHE.md` riga 289, presidiata in
`test_specifiche_conformita.py`): quando la finale si somma al campionato deve
contare la stessa cosa.

Qui i dettagli che la specifica non nomina:

* **da dove si eredita.** Dalla prima gara conclusa, come da sempre, e anche la
  distanza «al N»: senza, una stagione giocata «al 5» si chiudeva con una finale
  «esattamente 5». Dal campionato solo se non c'è ancora una gara conclusa;
* **la finale a tabellone** prende i campi che sul tabellone non sono una
  scelta (distanza «al N», minimo del formato), come una gara creata dal form;
* **la finale già creata** non si vede imporre strategia e sistema del
  campionato dal form di modifica gara.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models import Campionato
from models.competition.models import Gara
from models.exceptions import ValidationError
from models.playoff.models import PlayoffConfiguration, PlayoffType
from models.playoff.services import PlayoffService
from models.status_enum import Discipline, GaraStatus
from routes.admin.competition.form_parser import GaraFormParser


def _campionato(db_session, sistema: str = "WINS", **campi) -> Campionato:
    campionato = Campionato(
        name=f"Camp {uuid.uuid4().hex[:8]}",
        campionato_type="amalfi",
        is_active=True,
        default_classification_system=sistema,
        **campi,
    )
    db_session.add(campionato)
    db_session.flush()
    return campionato


def _gara_conclusa(db_session, campionato, **campi) -> Gara:
    valori = dict(
        campionato_id=campionato.id,
        name="Gara 1",
        number=1,
        date=date(2026, 1, 1),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=False,
        status=GaraStatus.COMPLETED.value,
        rounds_count=3,
        classification_system=campionato.default_classification_system,
        matchmaking_strategy="amalfi",
        odd_number_policy="bye_with_challenge",
    )
    valori.update(campi)
    gara = Gara(**valori)
    db_session.add(gara)
    db_session.flush()
    return gara


def _configurazione(db_session, campionato, **campi) -> PlayoffConfiguration:
    configurazione = PlayoffConfiguration(
        campionato_id=campionato.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        max_participants=8,
        positions_from=1,
        positions_to=8,
        is_active=True,
        auto_generate=True,
        min_garas_played=0,
        **campi,
    )
    db_session.add(configurazione)
    db_session.flush()
    return configurazione


@pytest.mark.unit
class TestDaDoveSiEredita:
    def test_la_finale_eredita_al_n_dalla_stagione(self, db_session):
        campionato = _campionato(db_session)
        _gara_conclusa(db_session, campionato, is_race_to=True)
        configurazione = _configurazione(db_session, campionato)
        db_session.commit()

        gara = PlayoffService.create_playoff_gara(configurazione.id)

        assert gara.is_race_to is True

    def test_senza_gare_concluse_valgono_i_default_del_campionato(self, db_session):
        campionato = _campionato(
            db_session, default_rounds_count=4, default_odd_policy="trio"
        )
        configurazione = _configurazione(db_session, campionato)
        db_session.commit()

        params = configurazione.get_gara_params()

        assert params["rounds_count"] == 4
        assert params["odd_number_policy"] == "trio"

    def test_la_gara_conclusa_vince_sui_default_del_campionato(self, db_session):
        """È l'ordine di sempre: la finale somiglia a ciò che si è giocato, non
        a ciò che il campionato proponeva quando è nato."""
        campionato = _campionato(
            db_session, default_rounds_count=4, default_odd_policy="trio"
        )
        _gara_conclusa(db_session, campionato, rounds_count=2)
        configurazione = _configurazione(db_session, campionato)
        db_session.commit()

        params = configurazione.get_gara_params()

        assert params["rounds_count"] == 2
        assert params["odd_number_policy"] == "bye_with_challenge"


@pytest.mark.unit
class TestIlSistemaScelto:
    def test_con_solo_playoff_la_finale_usa_il_sistema_scelto(self, db_session):
        campionato = _campionato(db_session, "WINS")
        _gara_conclusa(db_session, campionato)
        configurazione = _configurazione(
            db_session,
            campionato,
            final_ranking_mode="playoff_only",
            classification_system="RACK",
        )
        db_session.commit()

        gara = PlayoffService.create_playoff_gara(configurazione.id)

        assert gara.classification_system == "RACK"

    def test_in_modalita_sommata_un_sistema_diverso_e_rifiutato(self, db_session):
        campionato = _campionato(db_session, "WINS")
        configurazione = _configurazione(db_session, campionato)
        db_session.commit()
        configurazione_id = configurazione.id

        with pytest.raises(ValidationError):
            PlayoffService.update_configuration(
                configurazione_id, classification_system="RACK"
            )

        db_session.expire_all()
        rimasta = db_session.get(PlayoffConfiguration, configurazione_id)
        assert rimasta.classification_system is None

    def test_in_modalita_sommata_il_tabellone_e_rifiutato(self, db_session):
        campionato = _campionato(db_session, "WINS")
        configurazione = _configurazione(db_session, campionato)
        db_session.commit()

        with pytest.raises(ValidationError):
            PlayoffService.update_configuration(
                configurazione.id, strategy_type="double_knockout"
            )

    def test_con_solo_playoff_si_sceglie_anche_il_tabellone(self, db_session):
        campionato = _campionato(db_session, "WINS")
        configurazione = _configurazione(
            db_session, campionato, final_ranking_mode="playoff_only"
        )
        db_session.commit()
        configurazione_id = configurazione.id

        PlayoffService.update_configuration(
            configurazione_id, strategy_type="double_knockout"
        )

        db_session.expire_all()
        aggiornata = db_session.get(PlayoffConfiguration, configurazione_id)
        assert aggiornata.strategy_type == "double_knockout"


@pytest.mark.unit
class TestValoriAmmessi:
    @pytest.mark.parametrize(
        "campo, valore",
        [
            ("strategy_type", "spazzatura"),
            ("odd_number_policy", "spazzatura"),
            ("classification_system", "POSITION"),
            ("discipline", "spazzatura"),
        ],
    )
    def test_un_valore_che_l_app_non_conosce_e_rifiutato(
        self, db_session, campo, valore
    ):
        """POSITION non si sceglie: lo porta il tabellone da solo."""
        campionato = _campionato(db_session)
        configurazione = _configurazione(
            db_session, campionato, final_ranking_mode="playoff_only"
        )
        db_session.commit()

        with pytest.raises(ValidationError):
            PlayoffService.update_configuration(configurazione.id, **{campo: valore})

    def test_svuotare_un_campo_torna_a_ereditare(self, db_session):
        campionato = _campionato(db_session)
        configurazione = _configurazione(
            db_session,
            campionato,
            final_ranking_mode="playoff_only",
            classification_system="RACK",
            strategy_type="random",
        )
        db_session.commit()
        configurazione_id = configurazione.id

        PlayoffService.update_configuration(
            configurazione_id, classification_system=None, strategy_type=None
        )

        db_session.expire_all()
        aggiornata = db_session.get(PlayoffConfiguration, configurazione_id)
        assert aggiornata.classification_system is None
        assert aggiornata.strategy_type is None


class _CampionatoFinto:
    """Il minimo che `GaraFormParser` legge da un campionato."""

    campionato_type = "amalfi"
    default_rounds_count = 3
    default_entry_fee = 0
    default_anti_rematch = True
    default_odd_policy = "bye"
    default_classification_system = "WINS"


class _FinaleFinta:
    is_playoff = True
    matchmaking_strategy = "random"
    classification_system = "RACK"


def _form_modifica(app, **extra):
    base = {
        "date": "2026-12-01",
        "time": "20:00",
        "discipline": "8_ball",
        "distance": "5",
        "rounds_count": "3",
        "min_participants": "2",
        "matchmaking_strategy": "amalfi",
        "first_round_policy": "random",
        # Nessun prerequisito: la X con esercizio pretenderebbe un esercizio.
        "odd_number_policy": "no",
    }
    base.update(extra)
    return app.test_request_context(method="POST", data=base)


@pytest.mark.unit
class TestIlFormDiModificaDellaFinale:
    def test_la_finale_tiene_strategia_e_sistema_suoi(self, app):
        with _form_modifica(app):
            data = GaraFormParser(
                campionato=_CampionatoFinto(), gara=_FinaleFinta()
            ).parse()

        assert data["matchmaking_strategy"] == "random"
        assert data["classification_system"] == "RACK"

    def test_una_gara_di_serata_resta_quella_del_campionato(self, app):
        with _form_modifica(app):
            data = GaraFormParser(campionato=_CampionatoFinto()).parse()

        assert data["matchmaking_strategy"] == "amalfi"
        assert data["classification_system"] == "WINS"
