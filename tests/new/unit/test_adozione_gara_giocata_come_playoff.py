"""La finale giocata fuori dal campionato si adotta come gara di playoff.

Il caso vero (campionato 4, 15/09/2026): la scadenza degli inviti coincideva
con l'orario di gioco, dieci inviti su quattordici sono scaduti all'apertura
della pagina e la lista non offriva più niente al direttore, che ha creato una
gara standalone e ci ha giocato la finale in otto. Il campionato è rimasto
«in attesa dei playoff» con una gara di playoff vuota.

`AdozioneGaraGiocata` rimette le cose a posto **senza spostare una riga di
risultato**: la gara giocata entra nel campionato come finale (chiave alla
configurazione, numero, peso), gli inviti di chi ha giocato risultano accettati
e registrati dal direttore, la gara di playoff vuota sparisce e la classifica
generale si ricalcola. Partite, rack, ELO e XP restano dove sono: cambia solo a
chi appartiene la gara.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from models.base import db, utc_now
from models.campionato.models import Campionato
from models.classification.models import Classification
from models.competition.models import Gara, Inscription
from models.exceptions import ConflictError, ValidationError
from models.match.models import Match
from models.playoff.adozione import AdozioneGaraGiocata
from models.playoff.models import (
    PlayoffQualification,
    PlayoffTournament,
    QualificationStatus,
)
from models.playoff.services import PlayoffService
from models.status_enum import (
    ClassificationSystem,
    Discipline,
    GaraStatus,
    MatchStatus,
    TournamentStatus,
)
from tests.new.unit.test_avvio_playoff import _make_config, _make_user, _uid

PESO = 5


def _campionato(db_session, sistema=ClassificationSystem.RACK.value):
    c = Campionato(
        name=f"Camp {_uid()}",
        campionato_type="amalfi",
        is_active=True,
        default_classification_system=sistema,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _gara(db_session, campionato, number, giorno, **campi):
    campi.setdefault("classification_system", ClassificationSystem.RACK.value)
    g = Gara(
        campionato_id=campionato.id if campionato is not None else None,
        number=number,
        name=campi.pop("name", f"Gara {number}"),
        date=date(2026, 9, giorno),
        time=campi.pop("time", time(20, 0)),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        rounds_count=1,
        current_round=1,
        status=GaraStatus.COMPLETED.value,
        **campi,
    )
    db_session.add(g)
    db_session.flush()
    return g


def _partita(db_session, gara, vincitore, perdente, punteggio=(3, 1)):
    m = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=vincitore.id,
        player2_id=perdente.id,
        player1_score=punteggio[0],
        player2_score=punteggio[1],
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        winner_id=vincitore.id,
    )
    db_session.add(m)
    db_session.flush()
    return m


def _iscrivi(db_session, gara, *giocatori):
    for g in giocatori:
        db_session.add(Inscription(user_id=g.id, gara_id=gara.id))
    db_session.flush()


def _invito(cfg, giocatore) -> PlayoffQualification:
    return PlayoffQualification.query.filter_by(
        configuration_id=cfg.id, user_id=giocatore.id
    ).one()


class Scenario:
    """Campionato terminato, inviti partiti, quattro sì e quattro scaduti,
    gara di playoff vuota, finale giocata in otto in una gara standalone."""

    def __init__(self, db_session, *, sistema_finale=ClassificationSystem.RACK.value):
        self.admin = _make_user(db_session, role="admin")
        self.camp = _campionato(db_session)
        self.giocatori = [_make_user(db_session) for _ in range(8)]
        # Trio sui dispari: col sistema a triangoli la X semplice non vale,
        # e la finale eredita la politica dalla prima gara conclusa.
        g1 = _gara(db_session, self.camp, 1, 1, odd_number_policy="trio")
        _iscrivi(db_session, g1, *self.giocatori)
        # Stagione: quattro partite, tutti giocano una volta.
        self.stagione = {}
        for i in range(4):
            v, p = self.giocatori[i], self.giocatori[i + 4]
            _partita(db_session, g1, v, p, (3, i))
            self.stagione[v.id] = 3
            self.stagione[p.id] = i
        self.cfg = _make_config(db_session, self.camp, pos_to=8, max_p=8)
        self.cfg.playoff_weight = PESO
        self.camp.terminated_at = utc_now()
        db_session.commit()

        PlayoffService.start_playoff(self.camp.id)
        self.confermati = self.giocatori[:4]
        self.ritardatari = self.giocatori[4:]
        for g in self.confermati:
            PlayoffService.confirm_qualification(_invito(self.cfg, g).id, g.id)
        # La scadenza passa e la pagina del direttore fa scadere il resto.
        scaduta = utc_now() - timedelta(hours=1)
        self.cfg.response_deadline = scaduta
        for q in PlayoffQualification.query.filter_by(configuration_id=self.cfg.id):
            q.expires_at = scaduta
        db_session.commit()
        PlayoffService.expire_old_qualifications()
        self.vuota = PlayoffService.create_playoff_gara(self.cfg.id)
        self.vuota_id = self.vuota.id

        # La finale giocata davvero, fuori dal campionato.
        self.giocata = _gara(
            db_session,
            None,
            1,
            15,
            name="Playoff giocato a mano",
            classification_system=sistema_finale,
        )
        _iscrivi(db_session, self.giocata, *self.giocatori)
        self.finale = {}
        for i in range(4):
            v, p = self.giocatori[i], self.giocatori[7 - i]
            _partita(db_session, self.giocata, v, p, (3, 2 - (i % 3)))
            self.finale[v.id] = 3
            self.finale[p.id] = 2 - (i % 3)
        db_session.commit()

    def adotta(self, **kw):
        return AdozioneGaraGiocata.esegui(
            self.cfg.id, self.giocata.id, performed_by_id=self.admin.id, **kw
        )


class TestScenarioDiPartenza:
    def test_e_quello_di_produzione(self, db_session):
        s = Scenario(db_session)
        assert s.camp.get_status() == TournamentStatus.AWAITING_PLAYOFF.value
        stati = {g.id: _invito(s.cfg, g).status for g in s.giocatori}
        assert all(stati[g.id] == QualificationStatus.CONFIRMED for g in s.confermati)
        assert all(stati[g.id] == QualificationStatus.EXPIRED for g in s.ritardatari)
        assert s.vuota.playoff_config_id == s.cfg.id
        assert s.giocata.campionato_id is None


class TestAdozione:
    def test_la_gara_giocata_diventa_la_finale(self, db_session):
        s = Scenario(db_session)
        s.adotta()

        gara = db.session.get(Gara, s.giocata.id)
        assert gara.campionato_id == s.camp.id
        assert gara.playoff_config_id == s.cfg.id
        assert gara.number == 2, "prende il numero della gara vuota che sparisce"
        assert gara.weight == PESO
        assert db.session.get(Gara, s.vuota_id) is None
        assert Inscription.query.filter_by(gara_id=s.vuota_id).count() == 0
        torneo = PlayoffTournament.query.filter_by(configuration_id=s.cfg.id).one()
        assert torneo.gara_id == gara.id
        assert torneo.confirmed_participants == 8

    def test_gli_inviti_di_chi_ha_giocato_risultano_accettati_dal_direttore(
        self, db_session
    ):
        s = Scenario(db_session)
        s.adotta()

        for g in s.ritardatari:
            q = _invito(s.cfg, g)
            assert q.status == QualificationStatus.CONFIRMED
            assert q.responded_by_id == s.admin.id
            assert q.answered_on_behalf
            assert q.responded_at is not None
        for g in s.confermati:
            q = _invito(s.cfg, g)
            assert q.status == QualificationStatus.CONFIRMED
            assert q.responded_by_id == g.id, "chi aveva risposto da sé resta così"

    def test_chi_non_ha_giocato_resta_scaduto(self, db_session):
        s = Scenario(db_session)
        assente = s.ritardatari[0]
        Inscription.query.filter_by(gara_id=s.giocata.id, user_id=assente.id).delete()
        db_session.commit()

        s.adotta()

        assert _invito(s.cfg, assente).status == QualificationStatus.EXPIRED

    def test_il_campionato_si_chiude_e_la_classifica_somma_la_finale_pesata(
        self, db_session
    ):
        s = Scenario(db_session)
        s.adotta()

        camp = db.session.get(Campionato, s.camp.id)
        assert camp.get_status() == TournamentStatus.COMPLETED.value
        righe = {
            r.user_id: r
            for r in Classification.query.filter_by(campionato_id=s.camp.id)
        }
        for g in s.giocatori:
            atteso = s.stagione[g.id] + PESO * s.finale[g.id]
            assert righe[g.id].total_racks_won == atteso, g.username
            assert righe[g.id].gare_played == 2

    def test_le_partite_non_si_muovono(self, db_session):
        s = Scenario(db_session)
        prima = {m.id: m.gara_id for m in Match.query.all()}
        s.adotta()
        dopo = {m.id: m.gara_id for m in Match.query.all()}
        assert prima == dopo

    def test_il_nome_si_puo_cambiare(self, db_session):
        s = Scenario(db_session)
        s.adotta(nome="Finalissima")
        assert db.session.get(Gara, s.giocata.id).name == "Finalissima"

    def test_la_gara_adottata_non_si_distingue_da_una_finale_nativa(self, db_session):
        """I campi amministrativi prendono i valori che `create_playoff_gara`
        avrebbe scritto; quelli che dicono come si è giocato restano veri."""
        s = Scenario(db_session)
        s.giocata.director_id = s.admin.id
        s.giocata.inscription_start = utc_now() - timedelta(days=3)
        s.giocata.inscription_end = utc_now() - timedelta(days=1)
        s.giocata.min_participants = 6
        s.giocata.max_participants = None
        db_session.commit()
        nativa = db.session.get(Gara, s.vuota_id)
        attesi = {
            campo: getattr(nativa, campo)
            for campo in (
                "name",
                "director_id",
                "inscription_start",
                "inscription_end",
                "min_participants",
                "max_participants",
                "weight",
                "campionato_id",
                "playoff_config_id",
                "number",
            )
        }

        s.adotta()

        gara = db.session.get(Gara, s.giocata.id)
        assert {campo: getattr(gara, campo) for campo in attesi} == attesi
        assert gara.matchmaking_strategy == s.giocata.matchmaking_strategy
        assert gara.distance == 3 and gara.rounds_count == 1
        torneo = PlayoffTournament.query.filter_by(configuration_id=s.cfg.id).one()
        assert torneo.status == "registration"

    def test_la_data_deve_seguire_l_ultima_gara(self, db_session):
        """ADR-016: la finale è l'ultima gara del campionato."""
        s = Scenario(db_session)
        s.giocata.date = date(2026, 8, 1)
        db_session.commit()
        with pytest.raises(ConflictError, match="data"):
            s.adotta()


class TestPlan:
    def test_non_scrive_niente(self, db_session):
        s = Scenario(db_session)
        report = AdozioneGaraGiocata.plan(
            s.cfg.id, s.giocata.id, performed_by_id=s.admin.id
        )
        db.session.rollback()

        assert db.session.get(Gara, s.giocata.id).campionato_id is None
        assert db.session.get(Gara, s.vuota_id) is not None
        assert all(
            _invito(s.cfg, g).status == QualificationStatus.EXPIRED
            for g in s.ritardatari
        )
        assert report["gara_giocata"]["id"] == s.giocata.id
        assert report["gara_scartata"]["id"] == s.vuota_id
        assert report["numero_assegnato"] == 2
        azioni = {r["user_id"]: r["azione"] for r in report["inviti"]}
        assert all(azioni[g.id] == "confermato d'ufficio" for g in s.ritardatari)
        assert all(azioni[g.id] == "già confermato" for g in s.confermati)
        attesi = {r["user_id"]: r["atteso"] for r in report["classifica_attesa"]}
        for g in s.giocatori:
            assert attesi[g.id] == s.stagione[g.id] + PESO * s.finale[g.id]


class TestRifiuti:
    def test_una_gara_di_campionato_non_si_adotta(self, db_session):
        s = Scenario(db_session)
        s.giocata.campionato_id = s.camp.id
        db_session.commit()
        with pytest.raises(ValidationError, match="standalone"):
            s.adotta()

    def test_una_gara_non_conclusa_non_si_adotta(self, db_session):
        s = Scenario(db_session)
        s.giocata.status = GaraStatus.PLAYING.value
        db_session.commit()
        with pytest.raises(ValidationError, match="conclusa"):
            s.adotta()

    def test_la_gara_di_playoff_con_partite_non_si_scarta(self, db_session):
        s = Scenario(db_session)
        _partita(db_session, s.vuota, s.giocatori[0], s.giocatori[1])
        db_session.commit()
        with pytest.raises(ConflictError, match="partite"):
            s.adotta()

    def test_un_iscritto_senza_invito_ferma_tutto(self, db_session):
        s = Scenario(db_session)
        intruso = _make_user(db_session)
        _iscrivi(db_session, s.giocata, intruso)
        db_session.commit()
        with pytest.raises(ConflictError, match=intruso.username):
            s.adotta()
        assert db.session.get(Gara, s.vuota_id) is not None

    def test_chi_aveva_rifiutato_ferma_tutto(self, db_session):
        s = Scenario(db_session)
        q = _invito(s.cfg, s.ritardatari[0])
        q.status = QualificationStatus.DECLINED
        db_session.commit()
        with pytest.raises(ConflictError, match=s.ritardatari[0].username):
            s.adotta()

    def test_una_finale_sommata_deve_avere_il_sistema_del_campionato(self, db_session):
        s = Scenario(db_session, sistema_finale=ClassificationSystem.WINS.value)
        with pytest.raises(ValidationError, match="sistema"):
            s.adotta()

    def test_il_direttore_deve_esistere(self, db_session):
        s = Scenario(db_session)
        with pytest.raises(ConflictError, match="esegue"):
            AdozioneGaraGiocata.esegui(s.cfg.id, s.giocata.id, performed_by_id=999999)
