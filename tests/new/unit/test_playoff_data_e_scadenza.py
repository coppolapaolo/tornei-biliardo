"""Data dei playoff e scadenza degli inviti: le sceglie il direttore.

Rilievo del 2026-09-13. Nessuna schermata permetteva di impostarle:
`PlayoffConfiguration.scheduled_date` restava vuota, quindi la gara di playoff
nasceva datata il giorno della creazione, e la scadenza degli inviti era sempre
«fra sette giorni». Decisione dell'utente: il direttore le sceglie quando avvia
i playoff, e restano modificabili finché la gara di playoff non comincia.

Senza valori `start_playoff` fa quello che faceva: la competizione di prova e
gli altri chiamanti non devono cambiare.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.competition.models import Gara
from models.exceptions import ConflictError, ValidationError
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    QualificationStatus,
)
from models.playoff.services import PlayoffService
from models.status_enum import GaraStatus
from tests.new.unit.test_avvio_playoff import (
    _make_campionato,
    _make_classification,
    _make_config,
    _make_gara,
    _make_inscription,
    _make_user,
)

pytestmark = pytest.mark.unit


def _pronto(db_session, posti: int = 4):
    """Campionato terminato, playoff configurato, inviti non ancora partiti."""
    campionato = _make_campionato(db_session, terminated=True)
    cfg = _make_config(db_session, campionato, pos_to=posti, max_p=posti)
    gara = _make_gara(db_session, campionato)
    giocatori = []
    for posizione in range(1, posti + 1):
        giocatore = _make_user(db_session)
        _make_classification(db_session, campionato, giocatore, posizione)
        _make_inscription(db_session, giocatore, gara)
        giocatori.append(giocatore)
    db_session.commit()
    return campionato, cfg, giocatori


def _inviti(cfg) -> list[PlayoffQualification]:
    return PlayoffQualification.query.filter_by(configuration_id=cfg.id).all()


def _accetta(cfg, giocatore) -> None:
    invito = PlayoffQualification.query.filter_by(
        configuration_id=cfg.id, user_id=giocatore.id
    ).first()
    PlayoffService.confirm_qualification(invito.id, giocatore.id)


def _al_minuto(quando):
    return quando.replace(second=0, microsecond=0)


class TestAllAvvio:
    def test_data_e_scadenza_scelte_dal_direttore_valgono_per_gli_inviti(
        self, db_session
    ):
        campionato, cfg, _giocatori = _pronto(db_session)
        quando = _al_minuto(utc_now() + timedelta(days=14))
        scadenza = _al_minuto(utc_now() + timedelta(days=5))

        PlayoffService.start_playoff(
            campionato.id, scheduled_date=quando, response_deadline=scadenza
        )

        config = db.session.get(PlayoffConfiguration, cfg.id)
        assert config.scheduled_date == quando
        assert config.response_deadline == scadenza
        inviti = _inviti(cfg)
        assert inviti and all(q.expires_at == scadenza for q in inviti)

    def test_senza_valori_la_scadenza_resta_fra_una_settimana(self, db_session):
        campionato, cfg, _giocatori = _pronto(db_session)

        PlayoffService.start_playoff(campionato.id)

        config = db.session.get(PlayoffConfiguration, cfg.id)
        distanza = config.response_deadline - utc_now()
        assert timedelta(days=6, hours=23) < distanza <= timedelta(days=7)
        assert config.scheduled_date is None

    def test_una_scadenza_nel_passato_si_rifiuta(self, db_session):
        campionato, cfg, _giocatori = _pronto(db_session)

        with pytest.raises(ValidationError):
            PlayoffService.start_playoff(
                campionato.id, response_deadline=utc_now() - timedelta(hours=1)
            )

        assert _inviti(cfg) == []

    def test_una_data_nel_passato_si_rifiuta(self, db_session):
        campionato, cfg, _giocatori = _pronto(db_session)

        with pytest.raises(ValidationError):
            PlayoffService.start_playoff(
                campionato.id, scheduled_date=utc_now() - timedelta(days=1)
            )

        assert _inviti(cfg) == []

    def test_la_gara_di_playoff_nasce_nel_giorno_scelto(self, db_session):
        campionato, cfg, giocatori = _pronto(db_session)
        quando = _al_minuto(utc_now() + timedelta(days=20))
        PlayoffService.start_playoff(campionato.id, scheduled_date=quando)
        for giocatore in giocatori:
            _accetta(cfg, giocatore)

        gara = PlayoffService.create_playoff_gara(cfg.id)

        assert gara.date == quando.date()


class TestModificaDopoLAvvio:
    def test_la_scadenza_si_sposta_e_con_lei_gli_inviti_in_attesa(self, db_session):
        campionato, cfg, giocatori = _pronto(db_session)
        prima = _al_minuto(utc_now() + timedelta(days=3))
        dopo = _al_minuto(utc_now() + timedelta(days=10))
        PlayoffService.start_playoff(campionato.id, response_deadline=prima)
        _accetta(cfg, giocatori[0])

        PlayoffService.aggiorna_calendario(cfg.id, response_deadline=dopo)

        assert db.session.get(PlayoffConfiguration, cfg.id).response_deadline == dopo
        for invito in _inviti(cfg):
            if invito.status == QualificationStatus.PENDING:
                assert invito.expires_at == dopo
            else:
                # Chi ha già risposto non ha più una scadenza da rispettare.
                assert invito.expires_at == prima

    def test_la_data_si_sposta_anche_sulla_gara_gia_creata(self, db_session):
        campionato, cfg, giocatori = _pronto(db_session)
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori:
            _accetta(cfg, giocatore)
        gara = PlayoffService.create_playoff_gara(cfg.id)
        nuova = _al_minuto(utc_now() + timedelta(days=30))

        PlayoffService.aggiorna_calendario(cfg.id, scheduled_date=nuova)

        assert db.session.get(PlayoffConfiguration, cfg.id).scheduled_date == nuova
        assert db.session.get(Gara, gara.id).date == nuova.date()

    def test_a_gara_avviata_non_si_cambia_piu(self, db_session):
        campionato, cfg, giocatori = _pronto(db_session)
        PlayoffService.start_playoff(campionato.id)
        for giocatore in giocatori:
            _accetta(cfg, giocatore)
        gara = PlayoffService.create_playoff_gara(cfg.id)
        gara.status = GaraStatus.PLAYING.value
        gara.current_round = 1
        db_session.commit()

        with pytest.raises(ConflictError):
            PlayoffService.aggiorna_calendario(
                cfg.id, scheduled_date=utc_now() + timedelta(days=30)
            )

    def test_una_scadenza_passata_non_si_imposta(self, db_session):
        campionato, cfg, _giocatori = _pronto(db_session)
        PlayoffService.start_playoff(campionato.id)

        with pytest.raises(ValidationError):
            PlayoffService.aggiorna_calendario(
                cfg.id, response_deadline=utc_now() - timedelta(minutes=5)
            )
