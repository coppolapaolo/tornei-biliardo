"""Il campionato a piazzamenti ammette gare di ogni formato (ADR-080).

Decisione dell'utente del 2026-10-11 (SPECIFICHE.md, «Classifica», nota del
2026-10-11): sommare i totali di gare con gironi di taglia diversa non è
sensato, perché chi sta nel girone più numeroso gioca una partita in più.
Quindi:

* il campionato **a piazzamenti** (punti per posto, `position_points`) ammette
  gare di qualunque formato — Amalfi, casuale, girone all'italiana a uno o più
  gironi, tabellone — e ne prende il piazzamento finale;
* il sistema della gara ordina solo la serata; nei campionati a piazzamenti
  lo propone il campionato (`default_gara_classification_system`);
* nei campionati che **sommano i totali** le gare hanno tutte il sistema del
  campionato e restano a **girone unico**;
* chi non gioca una serata prende zero; il peso della gara vale.

Un campionato a tabellone esistente resta identico: è a piazzamenti per tipo,
e le sue gare restano a tabellone.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest

from models.campionato.models import Campionato
from models.campionato.piazzamenti import (
    e_a_piazzamenti,
    gironi_ammessi,
    sistema_del_campionato,
    sistema_delle_gare,
    sistema_per_la_gara,
    somma_i_totali,
    strategie_per_sistema,
)
from models.classification.models import GaraClassification
from models.competition.models import Gara
from models.exceptions import ValidationError
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User


class _Camp:
    """Un campionato finto, per le regole pure."""

    def __init__(self, tipo="amalfi", sistema="WINS", sistema_gare=None):
        self.campionato_type = tipo
        self.default_classification_system = sistema
        self.default_gara_classification_system = sistema_gare

    def __getattr__(self, nome):
        # Gli altri valori proposti: assenti, come su un campionato appena
        # creato che non li ha scritti.
        return None


@pytest.mark.unit
class TestQualeCampionatoEAPiazzamenti:
    def test_a_piazzamenti_col_sistema_position(self):
        assert e_a_piazzamenti(_Camp("amalfi", "POSITION"))
        assert e_a_piazzamenti(_Camp("round_robin", "POSITION"))

    def test_a_tabellone_anche_senza_il_sistema_scritto(self):
        """I campionati a tabellone nati prima che POSITION si scegliesse."""
        assert e_a_piazzamenti(_Camp("direct_elimination", "WINS"))
        assert e_a_piazzamenti(_Camp("double_knockout", "POSITION"))

    @pytest.mark.parametrize("sistema", ["WINS", "RACK", "POINTS"])
    def test_gli_altri_sommano_i_totali(self, sistema):
        camp = _Camp("amalfi", sistema)
        assert not e_a_piazzamenti(camp)
        assert somma_i_totali(camp)

    def test_una_gara_singola_non_somma_niente(self):
        assert not somma_i_totali(None)
        assert not e_a_piazzamenti(None)


@pytest.mark.unit
class TestIlSistemaDelleGare:
    def test_a_piazzamenti_le_serate_si_ordinano_a_vittorie_di_norma(self):
        assert sistema_delle_gare(_Camp("amalfi", "POSITION")) == "WINS"
        assert sistema_delle_gare(_Camp("direct_elimination", "POSITION")) == "WINS"

    def test_a_piazzamenti_il_campionato_lo_propone(self):
        camp = _Camp("round_robin", "POSITION", "POINTS")
        assert sistema_delle_gare(camp) == "POINTS"

    def test_sommando_i_totali_e_quello_del_campionato(self):
        """La proposta per le serate non si legge: conta il sistema."""
        assert sistema_delle_gare(_Camp("amalfi", "RACK", "POINTS")) == "RACK"

    def test_il_tabellone_ha_il_piazzamento(self):
        camp = _Camp("amalfi", "POSITION", "POINTS")
        assert sistema_per_la_gara(camp, "direct_elimination") == "POSITION"
        assert sistema_per_la_gara(camp, "double_knockout", "RACK") == "POSITION"

    def test_a_piazzamenti_la_gara_sceglie(self):
        camp = _Camp("amalfi", "POSITION", "POINTS")
        assert sistema_per_la_gara(camp, "amalfi") == "POINTS"
        assert sistema_per_la_gara(camp, "round_robin", "RACK") == "RACK"
        # POSITION non è un sistema da serata: si ripiega sulla proposta.
        assert sistema_per_la_gara(camp, "random", "POSITION") == "WINS"

    def test_sommando_i_totali_la_gara_non_sceglie(self):
        camp = _Camp("amalfi", "WINS")
        assert sistema_per_la_gara(camp, "round_robin", "RACK") == "WINS"

    def test_chi_propone_il_tabellone_e_a_piazzamenti(self):
        assert sistema_del_campionato("direct_elimination", "WINS") == "POSITION"
        assert sistema_del_campionato("amalfi", "POSITION") == "POSITION"
        assert sistema_del_campionato("round_robin", "POINTS") == "POINTS"
        assert sistema_del_campionato("amalfi", "boh") == "WINS"

    def test_le_strategie_che_ogni_sistema_propone(self):
        mappa = strategie_per_sistema()
        assert set(mappa["POSITION"]) == {
            "amalfi",
            "random",
            "round_robin",
            "direct_elimination",
            "double_knockout",
        }
        for sistema in ("WINS", "RACK", "POINTS"):
            assert set(mappa[sistema]) == {"amalfi", "random", "round_robin"}


# ── Database ────────────────────────────────────────────────────────────────


def _utente(db_session, prefisso):
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}", email=f"{prefisso}_{s}@test.com", role="player"
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _campionato(db_session, sistema="POSITION", tipo="amalfi", **campi):
    camp = Campionato(
        name=f"Camp {uuid.uuid4().hex[:6]}",
        campionato_type=tipo,
        default_classification_system=sistema,
        is_active=True,
        planned_gare_count=3,
        default_rounds_count=1,
        **campi,
    )
    db_session.add(camp)
    db_session.flush()
    return camp


def _gara_conclusa(db_session, camp, numero, partite, piazzamenti, **campi):
    """Una gara conclusa: le partite del turno 1 e il piazzamento finale.

    `partite` è `[(vince, perde)]`; `piazzamenti` è `[(giocatore, posto)]`.
    """
    from models.classification.gara_classification import RoundClassificationService

    gara = Gara(
        campionato_id=camp.id,
        number=numero,
        name=f"Serata {numero}",
        date=date(2026, 1, 10 + numero),
        time=time(20, 0),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        rounds_count=1,
        current_round=1,
        status=GaraStatus.COMPLETED.value,
        **campi,
    )
    db_session.add(gara)
    db_session.flush()
    for vince, perde in partite:
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=vince.id,
                player2_id=perde.id,
                player1_score=3,
                player2_score=1,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
                winner_id=vince.id,
            )
        )
    db_session.flush()
    RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
    for giocatore, posto in piazzamenti:
        riga = GaraClassification.query.filter_by(
            gara_id=gara.id, user_id=giocatore.id
        ).first()
        if riga is None:
            riga = GaraClassification(gara_id=gara.id, user_id=giocatore.id)
            db_session.add(riga)
        riga.position = posto
    db_session.flush()
    return gara


def _punti(camp):
    from models.campionato.tournament_service import TournamentService

    return {
        d["user_id"]: (pos, d.get("total_points", 0))
        for pos, d in TournamentService().calculate_general_classification(camp.id)
    }


@pytest.mark.unit
class TestLaClassificaGeneraleAPiazzamenti:
    def test_gare_di_formati_diversi_danno_i_punti_del_piazzamento(self, db_session):
        """Una serata Amalfi a vittorie, una a gironi a punti, un tabellone.

        Tabella di default: 25, 18, 15, 12. A: 1º, 2º, 1º → 68; B: 2º, 1º,
        assente → 43; C: 3º, 3º, 2º → 48; D: 4º, 4º, assente → 24.
        """
        camp = _campionato(db_session)
        a, b, c, d = (_utente(db_session, n) for n in "abcd")
        _gara_conclusa(
            db_session,
            camp,
            1,
            [(a, c), (b, d)],
            [(a, 1), (b, 2), (c, 3), (d, 4)],
            matchmaking_strategy="amalfi",
            classification_system="WINS",
        )
        _gara_conclusa(
            db_session,
            camp,
            2,
            [(b, a), (c, d)],
            [(b, 1), (a, 2), (c, 3), (d, 4)],
            matchmaking_strategy="round_robin",
            classification_system="POINTS",
            max_groups=2,
        )
        _gara_conclusa(
            db_session,
            camp,
            3,
            [(a, c)],
            [(a, 1), (c, 2)],
            matchmaking_strategy="direct_elimination",
            classification_system="POSITION",
        )
        punti = _punti(camp)
        assert punti[a.id] == (1, 68)
        assert punti[c.id] == (2, 48)
        assert punti[b.id] == (3, 43)  # assente alla terza: zero
        assert punti[d.id] == (4, 24)

    def test_chi_resta_pari_nella_gara_prende_gli_stessi_punti(self, db_session):
        """Due secondi a pari merito (1, 2, 2, 4): 18 punti a testa."""
        camp = _campionato(db_session)
        a, b, c, d = (_utente(db_session, n) for n in "abcd")
        _gara_conclusa(
            db_session,
            camp,
            1,
            [(a, c), (b, d)],
            [(a, 1), (b, 2), (c, 2), (d, 4)],
            matchmaking_strategy="round_robin",
            classification_system="WINS",
            max_groups=2,
        )
        punti = _punti(camp)
        assert punti[b.id][1] == punti[c.id][1] == 18
        assert punti[d.id][1] == 12

    def test_oltre_la_tabella_si_prende_zero(self, db_session):
        camp = _campionato(db_session, position_points='{"1": 10, "2": 6}')
        a, b, c, d = (_utente(db_session, n) for n in "abcd")
        _gara_conclusa(
            db_session,
            camp,
            1,
            [(a, c), (b, d)],
            [(a, 1), (b, 2), (c, 3), (d, 4)],
            matchmaking_strategy="amalfi",
            classification_system="WINS",
        )
        punti = _punti(camp)
        assert [punti[g.id][1] for g in (a, b, c, d)] == [10, 6, 0, 0]

    def test_il_peso_della_gara_vale(self, db_session):
        camp = _campionato(db_session)
        a, b = (_utente(db_session, n) for n in "ab")
        _gara_conclusa(
            db_session,
            camp,
            1,
            [(a, b)],
            [(a, 1), (b, 2)],
            matchmaking_strategy="round_robin",
            classification_system="RACK",
            weight=2,
        )
        punti = _punti(camp)
        assert punti[a.id][1] == 50
        assert punti[b.id][1] == 36

    def test_un_campionato_a_tabellone_resta_identico(self, db_session):
        """Tipo a tabellone, nessun sistema per le serate: come prima."""
        camp = _campionato(db_session, sistema="POSITION", tipo="direct_elimination")
        assert camp.default_gara_classification_system is None
        a, b = (_utente(db_session, n) for n in "ab")
        _gara_conclusa(
            db_session,
            camp,
            1,
            [(a, b)],
            [(a, 1), (b, 2)],
            matchmaking_strategy="direct_elimination",
            classification_system="POSITION",
        )
        punti = _punti(camp)
        assert punti[a.id] == (1, 25)
        assert punti[b.id] == (2, 18)


def _crea_gara(camp, numero=1, **campi):
    from models.competition.services import GaraService

    valori = dict(
        matchmaking_strategy="round_robin",
        first_round_policy="random",
        odd_number_policy="bye",
        rounds_count=3,
    )
    valori.update(campi)
    return GaraService.create_gara(
        campionato_id=camp.id,
        number=numero,
        name=f"Serata {numero}",
        date=date.today() + timedelta(days=7 * numero),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        **valori,
    )


@pytest.mark.unit
class TestIGironiSoloDoveNonSiSomma:
    def test_sommando_i_totali_la_gara_resta_a_girone_unico(self, db_session):
        camp = _campionato(db_session, sistema="WINS", tipo="round_robin")
        db_session.commit()
        with pytest.raises(ValueError, match="girone unico"):
            _crea_gara(camp, max_groups=2, classification_system="WINS")

    def test_sommando_i_totali_la_modifica_li_rifiuta(self, db_session):
        from models.competition.services import GaraService

        camp = _campionato(db_session, sistema="POINTS", tipo="round_robin")
        db_session.commit()
        gara = _crea_gara(camp, classification_system="POINTS")
        db_session.commit()
        with pytest.raises(ValueError, match="girone unico"):
            GaraService.update_gara(gara.id, max_groups=3)

    def test_a_piazzamenti_i_gironi_sono_liberi(self, db_session):
        camp = _campionato(db_session, sistema="POSITION", tipo="round_robin")
        db_session.commit()
        gara = _crea_gara(camp, max_groups=2, classification_system="WINS")
        assert gara.max_groups == 2

    def test_la_gara_singola_ha_i_gironi_liberi(self):
        class _G:
            campionato = None

        assert gironi_ammessi(_G())

    def test_il_campionato_che_somma_non_li_propone(self, db_session):
        from models.campionato.tournament_service import TournamentService

        utente = _utente(db_session, "dir")
        db_session.commit()
        with pytest.raises(ValidationError, match="girone unico"):
            TournamentService().create_campionato_with_director(
                name=f"Camp {uuid.uuid4().hex[:6]}",
                creator_user_id=utente.id,
                campionato_type="round_robin",
                default_classification_system="WINS",
                default_max_groups=2,
            )

    def test_a_piazzamenti_li_propone(self, db_session):
        from models.campionato.tournament_service import TournamentService

        utente = _utente(db_session, "dir")
        db_session.commit()
        camp = TournamentService().create_campionato_with_director(
            name=f"Camp {uuid.uuid4().hex[:6]}",
            creator_user_id=utente.id,
            campionato_type="round_robin",
            default_classification_system="POSITION",
            default_gara_classification_system="POINTS",
            default_max_groups=2,
        )
        assert camp.default_max_groups == 2
        assert camp.default_gara_classification_system == "POINTS"


@pytest.mark.unit
class TestCambiareComeSiEntraNelCampionato:
    def test_passando_alla_somma_i_gironi_tornano_unici(self, db_session):
        """Le gare da avviare ricevono il sistema e il girone unico."""
        from models.campionato.tournament_service import TournamentService

        camp = _campionato(
            db_session, sistema="POSITION", tipo="round_robin", default_max_groups=2
        )
        db_session.commit()
        gara = _crea_gara(camp, classification_system="POINTS")
        db_session.commit()
        assert gara.max_groups == 2
        TournamentService().update_campionato(
            camp.id, default_classification_system="WINS"
        )
        db_session.commit()
        assert db_session.get(Campionato, camp.id).default_max_groups == 1
        gara = db_session.get(Gara, gara.id)
        assert gara.max_groups == 1
        assert gara.classification_system == "WINS"

    def test_passando_alla_somma_con_gironi_chiesti_si_rifiuta(self, db_session):
        from models.campionato.tournament_service import TournamentService

        camp = _campionato(db_session, sistema="POSITION", tipo="round_robin")
        db_session.commit()
        with pytest.raises(ValidationError, match="girone unico"):
            TournamentService().update_campionato(
                camp.id, default_classification_system="RACK", default_max_groups=2
            )

    def test_un_tabellone_ferma_il_passaggio_alla_somma(self, db_session):
        from models.campionato.tournament_service import TournamentService

        camp = _campionato(db_session, sistema="POSITION", tipo="amalfi")
        db_session.commit()
        _crea_gara(
            camp,
            matchmaking_strategy="direct_elimination",
            classification_system="POSITION",
            max_participants=8,
            is_race_to=True,
        )
        db_session.commit()
        with pytest.raises(ValidationError, match="tabellone"):
            TournamentService().update_campionato(
                camp.id, default_classification_system="WINS"
            )

    def test_passando_ai_piazzamenti_le_serate_tengono_il_loro_sistema(
        self, db_session
    ):
        from models.campionato.tournament_service import TournamentService

        camp = _campionato(db_session, sistema="RACK", tipo="amalfi")
        db_session.commit()
        gara = _crea_gara(
            camp,
            matchmaking_strategy="amalfi",
            classification_system="RACK",
            odd_number_policy="no",
        )
        db_session.commit()
        TournamentService().update_campionato(
            camp.id,
            default_classification_system="POSITION",
            default_gara_classification_system="RACK",
        )
        db_session.commit()
        assert db_session.get(Gara, gara.id).classification_system == "RACK"


@pytest.mark.unit
class TestIlModuloDellaGaraNelCampionato:
    BASE = {
        "date": "2026-12-01",
        "time": "20:00",
        "discipline": "8_ball",
        "distance": "3",
        "rounds_count": "3",
        "min_participants": "2",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
    }

    def _parse(self, app, camp, **extra):
        from routes.admin.competition.form_parser import GaraFormParser

        with app.test_request_context(method="POST", data={**self.BASE, **extra}):
            return GaraFormParser(campionato=camp).parse()

    def test_a_piazzamenti_la_gara_sceglie_formato_e_sistema(self, app):
        camp = _Camp("amalfi", "POSITION", "WINS")
        dati = self._parse(
            app,
            camp,
            matchmaking_strategy="round_robin",
            classification_system="POINTS",
            max_groups="2",
        )
        assert dati["matchmaking_strategy"] == "round_robin"
        assert dati["classification_system"] == "POINTS"
        assert dati["max_groups"] == 2

    def test_a_piazzamenti_senza_scelta_vale_la_proposta(self, app):
        camp = _Camp("random", "POSITION", "RACK")
        dati = self._parse(app, camp)
        assert dati["matchmaking_strategy"] == "random"
        assert dati["classification_system"] == "RACK"

    def test_a_piazzamenti_un_tabellone(self, app):
        camp = _Camp("amalfi", "POSITION")
        dati = self._parse(app, camp, matchmaking_strategy="direct_elimination")
        assert dati["classification_system"] == "POSITION"

    def test_sommando_i_totali_decide_il_campionato(self, app):
        camp = _Camp("amalfi", "WINS")
        dati = self._parse(
            app,
            camp,
            matchmaking_strategy="direct_elimination",
            classification_system="RACK",
        )
        assert dati["matchmaking_strategy"] == "amalfi"
        assert dati["classification_system"] == "WINS"


@pytest.mark.unit
class TestLaFinaleDeiPlayoff:
    def test_a_piazzamenti_ogni_finale_si_somma(self):
        """Della finale si prende il piazzamento, qualunque sia il formato."""
        from models.playoff.services import PlayoffService

        class _Config:
            decides_final_ranking = False
            campionato = _Camp("amalfi", "POSITION")

        PlayoffService._verifica_finale_sommabile(_Config(), "WINS")
        PlayoffService._verifica_finale_sommabile(_Config(), "POSITION")

    def test_sommando_i_totali_la_finale_conta_la_stessa_cosa(self, app):
        from models.playoff.services import PlayoffService

        class _Camp2(_Camp):
            @property
            def classification_system(self):
                from models.status_enum import ClassificationSystem

                return ClassificationSystem.resolve(self.default_classification_system)

        class _Config:
            decides_final_ranking = False
            campionato = _Camp2("amalfi", "WINS")

        with app.test_request_context():
            with pytest.raises(ValidationError):
                PlayoffService._verifica_finale_sommabile(_Config(), "POSITION")
