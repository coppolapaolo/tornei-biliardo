"""Il campionato concluso e il suo campione (canvas «campionato-concluso»).

Tre regole, prese insieme perché vetrina e pagina del direttore le leggono
dalla stessa fonte (`models/campionato/esito.py`):

* **concluso** vuol dire terminato **e** senza playoff da giocare: durante la
  fase playoff non si sa ancora chi vince, e la pagina non deve dirlo;
* il **campione** è il primo della classifica generale calcolata
  (`calculate_general_classification`), che applica già la modalità di
  classifica finale (ADR-053). Non è il vincitore della gara di playoff: con
  «campionato + playoff» i due possono essere persone diverse;
* il vincitore di ogni gara conclusa, finale compresa, arriva da una query
  sola.
"""

from __future__ import annotations

import pytest

from models.base import utc_now
from models.campionato.esito import (
    campionato_concluso,
    podio_da_classifica,
    vincitori_delle_gare,
)
from models.campionato.showcase_view import costruisci_vetrina_campionato
from models.campionato.tournament_service import TournamentService
from models.competition.models import Gara
from models.playoff.models import PlayoffRankingMode
from models.status_enum import GaraStatus
from tests.new.unit.test_playoff_classifica_finale_e_peso import (
    _campionato_con_playoff,
    _make_campionato,
    _make_gara,
    _make_match,
    _make_user,
    _righe_di_turno,
)

pytestmark = pytest.mark.unit


def _concluso(db_session, mode):
    """Il campionato del test ADR-053, terminato e con la finale chiusa."""
    dati = _campionato_con_playoff(db_session, mode)
    _righe_di_turno(db_session, dati["campionato"])
    dati["campionato"].terminated_at = utc_now()
    db_session.commit()
    return dati


def _podio(campionato):
    return podio_da_classifica(
        TournamentService().calculate_general_classification(campionato.id)
    )


class TestQuandoEConcluso:
    def test_terminato_con_la_finale_chiusa(self, db_session):
        dati = _concluso(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        assert campionato_concluso(dati["campionato"]) is True

    def test_durante_la_finale_non_lo_e(self, db_session):
        dati = _concluso(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        dati["playoff"].status = GaraStatus.PLAYING.value
        db_session.commit()

        assert campionato_concluso(dati["campionato"]) is False

    def test_non_terminato_non_lo_e(self, db_session):
        dati = _campionato_con_playoff(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        assert campionato_concluso(dati["campionato"]) is False

    def test_terminato_senza_playoff_lo_e(self, db_session):
        camp = _make_campionato(db_session)
        camp.terminated_at = utc_now()
        db_session.commit()

        assert campionato_concluso(camp) is True


class TestIlCampione:
    def test_solo_playoff_il_campione_e_chi_ha_vinto_la_finale(self, db_session):
        dati = _concluso(db_session, PlayoffRankingMode.PLAYOFF_ONLY)

        podio = _podio(dati["campionato"])

        assert [p.nome for p in podio] == [
            dati["d"].username,
            dati["c"].username,
            dati["a"].username,
        ]
        assert [p.posizione for p in podio] == [1, 2, 3]

    def test_con_la_somma_il_campione_non_e_il_vincitore_della_finale(self, db_session):
        """D vince la finale, ma con due prove vinte A resta davanti."""
        dati = _concluso(db_session, PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF)

        podio = _podio(dati["campionato"])
        vincitori = vincitori_delle_gare([dati["playoff"]])

        assert podio[0].nome == dati["a"].username
        assert vincitori[dati["playoff"].id] == dati["d"].username

    def test_con_meno_di_tre_giocatori_il_podio_e_corto(self, db_session):
        camp = _make_campionato(db_session)
        a = _make_user(db_session, "a")
        b = _make_user(db_session, "b")
        gara = _make_gara(db_session, camp, 1, 10)
        _make_match(db_session, gara, a, b)
        db_session.commit()
        _righe_di_turno(db_session, camp)

        assert [p.nome for p in _podio(camp)] == [a.username, b.username]

    def test_senza_classifica_non_c_e_podio(self):
        assert podio_da_classifica([]) == []
        assert podio_da_classifica(None) == []


class TestIVincitoriDelleGare:
    def test_ogni_gara_conclusa_finale_compresa(self, db_session):
        dati = _concluso(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        gare = Gara.query.filter_by(campionato_id=dati["campionato"].id).all()

        vincitori = vincitori_delle_gare(gare)

        assert len(vincitori) == 3
        assert vincitori[dati["playoff"].id] == dati["d"].username

    def test_una_gara_non_conclusa_non_ha_vincitore(self, db_session):
        dati = _concluso(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        # Non PLAYING: con tutte le partite chiuse lo stato derivato la dà
        # già per finita, ed è giusto così.
        dati["playoff"].status = GaraStatus.INSCRIPTION.value
        db_session.commit()

        assert dati["playoff"].id not in vincitori_delle_gare([dati["playoff"]])


class TestLaVetrina:
    def test_a_campionato_concluso_porta_il_podio(self, db_session):
        dati = _concluso(db_session, PlayoffRankingMode.PLAYOFF_ONLY)

        vetrina = costruisci_vetrina_campionato(dati["campionato"])

        assert vetrina.concluso is True
        assert [p.nome for p in vetrina.podio][:1] == [dati["d"].username]

    def test_durante_la_finale_niente_campione(self, db_session):
        dati = _concluso(db_session, PlayoffRankingMode.PLAYOFF_ONLY)
        dati["playoff"].status = GaraStatus.PLAYING.value
        db_session.commit()

        vetrina = costruisci_vetrina_campionato(dati["campionato"])

        assert vetrina.concluso is False
        assert vetrina.podio == []
