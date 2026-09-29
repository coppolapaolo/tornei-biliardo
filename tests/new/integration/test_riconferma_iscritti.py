"""«Ci sei ancora?»: la riconferma degli iscritti (ADR-075, punto 7).

Scatta solo per ciò che può cambiare la decisione di esserci: data, orario
spostato di più di un'ora, sala, quota che sale. Si calcola dalle condizioni
accettate, quindi più modifiche danno una richiesta sola e tornare ai valori
accettati la fa sparire. Chi non risponde resta iscritto.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import uuid
from datetime import date, time, timedelta
from pathlib import Path

import pytest

from models.base import db
from models.competition.models import Inscription
from models.competition.riconferma import riconferma
from models.competition.services import GaraService
from models.notification.models import Notification, NotificationType
from models.status_enum import GaraStatus
from models.storia.avvisi import AvvisiModifiche
from models.storia.service import StoriaModificheService
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
def iscritto(db_session):
    direttore = _utente(db_session, "dir", role="director")
    gara = GaraService.create_gara(
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
    gara.status = GaraStatus.INSCRIPTION.value
    giocatore = _utente(db_session)
    iscrizione = Inscription(user_id=giocatore.id, gara_id=gara.id)
    db_session.add(iscrizione)
    db_session.commit()
    return gara, giocatore, iscrizione, direttore


def _da_riconfermare(iscrizione_id):
    return db.session.get(Inscription, iscrizione_id).campi_da_riconfermare


class TestQuandoSiChiede:
    def test_l_iscrizione_ricorda_le_condizioni(self, iscritto):
        _g, _p, iscrizione, _d = iscritto
        accettate = json.loads(iscrizione.accepted_terms)
        assert accettate == {
            "date": (date.today() + timedelta(days=10)).isoformat(),
            "time": "20:00",
            "location": "Sala A",
            "entry_fee": "10",
        }
        assert _da_riconfermare(iscrizione.id) == []

    @pytest.mark.parametrize(
        "campi, attesi",
        [
            ({"location": "Sala B"}, ["location"]),
            ({"time": time(20, 45)}, []),
            ({"time": time(22, 0)}, ["time"]),
            ({"entry_fee": 8}, []),
            ({"entry_fee": 15}, ["entry_fee"]),
            ({"name": "Altro nome"}, []),
            ({"distance": 7}, []),
        ],
    )
    def test_solo_cio_che_cambia_la_decisione(self, iscritto, campi, attesi):
        gara, _p, iscrizione, _d = iscritto
        GaraService.update_gara(gara.id, **campi)
        assert _da_riconfermare(iscrizione.id) == attesi

    def test_tornare_indietro_cancella_la_richiesta(self, iscritto):
        gara, _p, iscrizione, _d = iscritto
        GaraService.update_gara(gara.id, location="Sala B")
        GaraService.update_gara(gara.id, location="Sala A")
        assert _da_riconfermare(iscrizione.id) == []


class TestChiRiconferma:
    def test_il_giocatore(self, iscritto):
        gara, giocatore, iscrizione, _d = iscritto
        GaraService.update_gara(gara.id, location="Sala B")
        riconferma(iscrizione.id, autore=giocatore)
        assert _da_riconfermare(iscrizione.id) == []
        assert StoriaModificheService.voci_della_gara(gara.id)[0].action != (
            "riconferma"
        )

    def test_il_direttore_per_lui_resta_scritto(self, iscritto):
        gara, giocatore, iscrizione, direttore = iscritto
        GaraService.update_gara(gara.id, location="Sala B")
        riconferma(iscrizione.id, autore=direttore)
        voce = StoriaModificheService.voci_della_gara(gara.id)[0]
        assert voce.action == "riconferma"
        assert {r.field for r in voce.fields} == {"giocatore", "location"}

    def test_la_notifica_lo_chiede(self, iscritto):
        gara, giocatore, _i, _d = iscritto
        GaraService.update_gara(gara.id, location="Sala B")
        AvvisiModifiche.invia(gara.id)
        notifica = Notification.query.filter_by(
            user_id=giocatore.id, notification_type=NotificationType.GARA_MODIFICATA
        ).one()
        assert "Ci sei ancora" in notifica.message


class TestDallaPagina:
    def test_il_giocatore_vede_e_risponde(self, client, iscritto):
        gara, giocatore, iscrizione, _d = iscritto
        GaraService.update_gara(gara.id, location="Sala B")
        client.post(
            "/auth/login",
            data={"username": giocatore.username, "password": "test1234"},
            follow_redirects=True,
        )
        pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert "ci sei ancora?" in pagina
        client.post(f"/player/gara/{gara.id}/riconferma")
        assert _da_riconfermare(iscrizione.id) == []


class TestPlayoff:
    def test_l_invito_accettato_si_riconferma(self, db_session):
        from models.base import utc_now
        from models.campionato.models import Campionato
        from models.competition.riconferma import riconferma_invito
        from models.playoff.models import (
            PlayoffConfiguration,
            PlayoffQualification,
            PlayoffType,
        )
        from models.playoff.services import PlayoffService

        camp = Campionato(name=f"C {uuid.uuid4().hex[:6]}", campionato_type="amalfi")
        db_session.add(camp)
        db_session.flush()
        cfg = PlayoffConfiguration(
            campionato_id=camp.id,
            name="Finale",
            playoff_type=PlayoffType.TOP_N,
            max_participants=4,
            positions_from=1,
            positions_to=4,
            is_active=True,
            scheduled_date=utc_now() + timedelta(days=20),
            location="Sala A",
        )
        db_session.add(cfg)
        db_session.flush()
        giocatore = _utente(db_session)
        qual = PlayoffQualification(
            configuration_id=cfg.id,
            user_id=giocatore.id,
            qualifying_position=1,
            qualification_reason="Posizione 1",
            invited_at=utc_now(),
        )
        db_session.add(qual)
        db_session.commit()
        qual.confirm_participation()
        db_session.commit()
        assert qual.campi_da_riconfermare == []

        PlayoffService.aggiorna_calendario(
            cfg.id, scheduled_date=cfg.scheduled_date + timedelta(days=2)
        )
        assert qual.campi_da_riconfermare == ["date"]
        riconferma_invito(qual.id, autore=giocatore)
        assert db_session.get(PlayoffQualification, qual.id).campi_da_riconfermare == []


def test_la_migration_riempie_le_condizioni_di_oggi(tmp_path):
    percorso = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "20260929_riconferma_iscritti.py"
    )
    spec = importlib.util.spec_from_file_location("riconferma_mig", percorso)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    db_file = tmp_path / "db.sqlite"
    conn = sqlite3.connect(db_file)
    conn.executescript("""
        CREATE TABLE gara (id INTEGER PRIMARY KEY, date DATE, time TIME,
            location VARCHAR, entry_fee FLOAT);
        CREATE TABLE inscription (id INTEGER PRIMARY KEY, gara_id INTEGER);
        CREATE TABLE playoff_configuration (id INTEGER PRIMARY KEY,
            scheduled_date DATETIME, location VARCHAR, entry_fee FLOAT);
        CREATE TABLE playoff_qualification (id INTEGER PRIMARY KEY,
            configuration_id INTEGER, status VARCHAR);
        INSERT INTO gara VALUES (1, '2026-10-10', '20:00:00.000000', 'Sala A', 10.0);
        INSERT INTO inscription VALUES (7, 1);
        INSERT INTO playoff_configuration VALUES
            (3, '2026-11-01 21:00:00.000000', NULL, NULL);
        INSERT INTO playoff_qualification VALUES (8, 3, 'CONFIRMED');
        INSERT INTO playoff_qualification VALUES (9, 3, 'PENDING');
        """)
    conn.commit()
    conn.close()

    migration.upgrade_sqlite(str(db_file))
    migration.upgrade_sqlite(str(db_file))

    conn = sqlite3.connect(db_file)
    (iscr,) = conn.execute("SELECT accepted_terms FROM inscription").fetchone()
    quals = dict(conn.execute("SELECT id, accepted_terms FROM playoff_qualification"))
    conn.close()
    assert json.loads(iscr) == {
        "date": "2026-10-10",
        "time": "20:00",
        "location": "Sala A",
        "entry_fee": "10",
    }
    assert json.loads(quals[8])["date"] == "2026-11-01"
    assert json.loads(quals[8])["time"] == "21:00"
    assert quals[9] is None
