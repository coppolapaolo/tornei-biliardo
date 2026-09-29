"""Le modifiche a una gara arrivano agli iscritti in una notifica sola (ADR-075).

La storia registra ogni salvataggio; la notifica confronta lo stato di
partenza con quello di adesso. Sala A → B → C arriva come «A → C», A → B → A
non manda niente, e i cambi che non spostano la decisione di esserci (nome,
quota che scende, mezz'ora d'orario) restano solo nella storia.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

import pytest

from models.base import db, utc_now
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService
from models.notification.models import Notification, NotificationType
from models.status_enum import GaraStatus
from models.storia.avvisi import AvvisiModifiche, SettingsNotice
from models.user.models import User

pytestmark = pytest.mark.integration


def _utente(db_session, prefisso="p", role="player"):
    s = uuid.uuid4().hex[:8]
    u = User(username=f"{prefisso}_{s}", email=f"{prefisso}_{s}@t.com", role=role)
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture
def gara(db_session):
    direttore = _utente(db_session, "dir", role="director")
    g = GaraService.create_gara(
        number=1,
        director_id=direttore.id,
        name=f"Serata {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=10),
        time=time(20, 0),
        discipline="9_ball",
        distance=5,
        location="Sala A",
        entry_fee=10,
    )
    g.status = GaraStatus.INSCRIPTION.value
    giocatori = [_utente(db_session) for _ in range(2)]
    for u in giocatori:
        db_session.add(Inscription(user_id=u.id, gara_id=g.id))
    db_session.commit()
    return g, giocatori


def _notifiche(user):
    return Notification.query.filter_by(
        user_id=user.id, notification_type=NotificationType.GARA_MODIFICATA
    ).all()


class TestAccorpate:
    def test_a_b_c_diventa_a_c(self, db_session, gara):
        g, (p1, p2) = gara
        GaraService.update_gara(g.id, location="Sala B")
        GaraService.update_gara(g.id, location="Sala C")
        assert SettingsNotice.query.filter_by(gara_id=g.id).count() == 1

        assert AvvisiModifiche.invia(g.id) == 2
        (notifica,) = _notifiche(p1)
        assert "Sala A" in notifica.message and "Sala C" in notifica.message
        assert "Sala B" not in notifica.message
        assert len(_notifiche(p2)) == 1
        assert AvvisiModifiche.in_attesa(g.id) is None

    def test_a_b_a_non_manda_niente(self, db_session, gara):
        g, (p1, _p2) = gara
        GaraService.update_gara(g.id, location="Sala B")
        GaraService.update_gara(g.id, location="Sala A")
        assert AvvisiModifiche.invia(g.id) == 0
        assert _notifiche(p1) == []
        assert AvvisiModifiche.in_attesa(g.id) is None

    @pytest.mark.parametrize(
        "campi, annunciato",
        [
            ({"name": "Altro nome"}, False),
            ({"entry_fee": 8}, False),
            ({"entry_fee": 15}, True),
            ({"time": time(20, 30)}, False),
            ({"time": time(22, 0)}, True),
            ({"distance": 7}, True),
        ],
    )
    def test_cosa_si_annuncia(self, db_session, gara, campi, annunciato):
        g, (p1, _p2) = gara
        GaraService.update_gara(g.id, **campi)
        AvvisiModifiche.invia(g.id)
        assert bool(_notifiche(p1)) is annunciato


class TestQuandoParte:
    def test_dopo_mezz_ora_dall_ultima_modifica(self, db_session, gara):
        g, (p1, _p2) = gara
        GaraService.update_gara(g.id, location="Sala B")
        adesso = utc_now()
        assert AvvisiModifiche.invia_scaduti(adesso + timedelta(minutes=10)) == 0
        assert AvvisiModifiche.invia_scaduti(adesso + timedelta(minutes=31)) == 2
        assert len(_notifiche(p1)) == 1

    def test_subito_se_la_gara_e_vicina(self, db_session, gara):
        g, (p1, _p2) = gara
        from utils.local_time import FALLBACK_TIMEZONE

        fra_un_ora = datetime.now(FALLBACK_TIMEZONE) + timedelta(hours=1)
        g.date = fra_un_ora.date()
        g.time = fra_un_ora.time().replace(second=0, microsecond=0)
        db_session.commit()
        GaraService.update_gara(g.id, location="Sala B")
        assert len(_notifiche(p1)) == 1


class TestDallaPagina:
    def test_invia_ora(self, client, db_session, gara):
        g, (p1, _p2) = gara
        admin = _utente(db_session, "admin", role="admin")
        db_session.commit()
        client.post(
            "/auth/login",
            data={"username": admin.username, "password": "test1234"},
            follow_redirects=True,
        )
        GaraService.update_gara(g.id, location="Sala B")
        pagina = client.get(f"/admin/gara/{g.id}/edit").get_data(as_text=True)
        assert "Notifica in attesa per gli iscritti" in pagina

        client.post(f"/admin/gara/{g.id}/avviso/invia")
        assert len(_notifiche(p1)) == 1
        assert db.session.get(Gara, g.id) is not None
