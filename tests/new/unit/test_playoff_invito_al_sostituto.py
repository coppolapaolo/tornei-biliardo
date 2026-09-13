"""Il primo degli esclusi riceve l'invito ai playoff, con una scadenza vera.

`SPECIFICHE.md`, sezione «Playoff»: «se un giocatore rifiuta, la notifica
passa al primo degli esclusi e così via». Fino al 2026-09-13 il rifiuto
creava la qualificazione del sostituto ma non gli mandava niente, e l'invito
non aveva scadenza: `decline_qualification` passava da un
`notify_qualified_players` che si limitava a segnare la data d'invito.

Qui si verifica quale scadenza riceve il sostituto e che la strada della
scadenza — l'altra che chiama un sostituto — si comporti allo stesso modo. Il
caso base, rifiuto del giocatore e rifiuto detto al direttore, sta in
`test_specifiche_conformita.py`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from models.base import utc_now
from models.notification.models import Notification, NotificationType
from models.playoff.models import PlayoffQualification, QualificationStatus
from models.playoff.services import PlayoffService
from tests.new.unit.test_avvio_playoff import (
    _make_campionato,
    _make_classification,
    _make_config,
    _make_gara,
    _make_inscription,
    _make_user,
)


def _playoff(db_session, *, posti: int = 2, classificati: int = 4):
    campionato = _make_campionato(db_session, terminated=True)
    cfg = _make_config(db_session, campionato, pos_to=posti, max_p=posti)
    gara = _make_gara(db_session, campionato)
    giocatori = []
    for posizione in range(1, classificati + 1):
        giocatore = _make_user(db_session)
        _make_classification(db_session, campionato, giocatore, posizione)
        _make_inscription(db_session, giocatore, gara)
        giocatori.append(giocatore)
    db_session.commit()
    PlayoffService.start_playoff(campionato.id)
    db_session.commit()
    return cfg, giocatori


def _invito(cfg, giocatore) -> PlayoffQualification:
    return PlayoffQualification.query.filter_by(
        configuration_id=cfg.id, user_id=giocatore.id
    ).one()


def _inviti_ricevuti(giocatore) -> list[Notification]:
    return Notification.query.filter_by(
        user_id=giocatore.id,
        notification_type=NotificationType.PLAYOFF_INVITATION,
    ).all()


@pytest.mark.unit
class TestScadenzaDelSostituto:
    def test_con_la_scadenza_ancora_davanti_vale_quella_di_tutti(self, db_session):
        cfg, giocatori = _playoff(db_session)
        rinuncia = _invito(cfg, giocatori[0])

        PlayoffService.decline_qualification(rinuncia.id, giocatori[0].id)
        db_session.commit()

        sostituto = _invito(cfg, giocatori[2])
        assert sostituto.invited_at is not None
        assert sostituto.expires_at == cfg.response_deadline

    def test_a_scadenza_passata_il_sostituto_ha_sette_giorni(self, db_session):
        """Una scadenza già alle spalle darebbe un invito nato scaduto.

        Il sostituto riceve allora gli stessi sette giorni che `start_playoff`
        dà quando la configurazione non ne fissa una, e il job delle scadenze
        rispetta la sua: altrimenti lo chiuderebbe alla prima pagina aperta.
        """
        cfg, giocatori = _playoff(db_session)
        cfg.response_deadline = utc_now() - timedelta(days=1)
        db_session.commit()
        rinuncia = _invito(cfg, giocatori[0])

        prima = utc_now()
        PlayoffService.decline_qualification(rinuncia.id, giocatori[0].id)
        db_session.commit()

        sostituto = _invito(cfg, giocatori[2])
        assert sostituto.expires_at is not None
        assert sostituto.expires_at >= prima + timedelta(days=7)
        assert sostituto.expires_at <= utc_now() + timedelta(days=7)
        assert len(_inviti_ricevuti(giocatori[2])) == 1

        PlayoffService.expire_old_qualifications()
        db_session.commit()

        assert (
            db_session.get(PlayoffQualification, sostituto.id).status
            == QualificationStatus.PENDING
        ), "il job delle scadenze ha chiuso un invito che scade fra sette giorni"


@pytest.mark.unit
class TestLaScadenzaChiamaIlSostitutoAlloStessoModo:
    def test_chi_subentra_a_un_invito_scaduto_riceve_l_invito(self, db_session):
        cfg, giocatori = _playoff(db_session)
        cfg.response_deadline = utc_now() - timedelta(hours=1)
        for giocatore in giocatori[:2]:
            _invito(cfg, giocatore).expires_at = cfg.response_deadline
        db_session.commit()

        PlayoffService.expire_old_qualifications()
        db_session.commit()

        for giocatore in giocatori[2:]:
            sostituto = _invito(cfg, giocatore)
            assert sostituto.status == QualificationStatus.PENDING
            assert sostituto.invited_at is not None
            assert sostituto.expires_at is not None
            assert sostituto.expires_at > utc_now(), "invito nato già scaduto"
            notifiche = _inviti_ricevuti(giocatore)
            assert len(notifiche) == 1
            assert (
                notifiche[0].action_url == f"/player/playoff/invitation/{sostituto.id}"
            )
