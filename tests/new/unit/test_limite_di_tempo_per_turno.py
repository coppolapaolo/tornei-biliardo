"""Il limite di tempo di un singolo turno (ADR-027, ADR-077).

`RoundConfiguration.time_limit_minutes` ha **tre** stati, come il campo della
gara, e non due come gli altri override:

* NULL — nessun override: il turno segue la gara;
* 0 — «senza limite» per questo turno, anche se la gara ne ha uno;
* N — N minuti per le partite di questo turno.

La partita lo riceve quando nasce: `fissa_regole` legge il turno prima della
gara. Dalla route, `null` toglie l'override e un numero fuori da 0–600 si
rifiuta.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest

from models.base import db
from models.competition.models import Gara
from models.competition.round_configuration import RoundConfiguration
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _gara(**overrides):
    base = dict(
        number=1,
        name=f"Gara {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=2),
        time=time(20, 0),
        discipline="8_ball",
        distance=3,
        rounds_count=3,
        current_round=0,
        min_participants=2,
        matchmaking_strategy="amalfi",
        status=GaraStatus.SETUP.value,
        time_limit_minutes=30,
    )
    base.update(overrides)
    gara = Gara(**base)
    db.session.add(gara)
    db.session.commit()
    return gara


def _partita(gara, turno):
    match = Match(
        gara_id=gara.id,
        round_number=turno,
        status=MatchStatus.PLAYING.value,
        match_distance=gara.distance,
    )
    db.session.add(match)
    db.session.commit()
    return match


@pytest.mark.unit
class TestIlTurnoPrimaDellaGara:
    def test_senza_override_il_turno_segue_la_gara(self, db_session):
        gara = _gara()
        assert _partita(gara, 1).time_limit_minutes == 30

    def test_un_turno_con_un_limite_suo(self, db_session):
        gara = _gara()
        RoundConfiguration.create_or_update(gara.id, 2, time_limit_minutes=45)
        db.session.commit()
        assert _partita(gara, 1).time_limit_minutes == 30
        assert _partita(gara, 2).time_limit_minutes == 45

    def test_un_turno_senza_limite_in_una_gara_che_lo_ha(self, db_session):
        gara = _gara()
        RoundConfiguration.create_or_update(gara.id, 3, time_limit_minutes=0)
        db.session.commit()
        match = _partita(gara, 3)
        assert match.time_limit_minutes is None
        assert match.has_time_limit is False

    def test_un_turno_con_limite_in_una_gara_senza(self, db_session):
        gara = _gara(time_limit_minutes=0)
        RoundConfiguration.create_or_update(gara.id, 3, time_limit_minutes=20)
        db.session.commit()
        assert _partita(gara, 3).time_limit_minutes == 20

    def test_il_limite_e_un_override_del_turno(self, db_session):
        gara = _gara()
        config = RoundConfiguration.create_or_update(gara.id, 2, time_limit_minutes=0)
        assert config.has_overrides()
        assert config.get_effective_time_limit_minutes(gara) is None

    def test_si_toglie_l_override_senza_toccare_il_resto(self, db_session):
        gara = _gara()
        RoundConfiguration.create_or_update(
            gara.id, 2, distance=5, time_limit_minutes=45
        )
        # Per il limite, None passato esplicitamente toglie l'override: per
        # gli altri campi vuol dire «non toccare», qui servono tutti e tre.
        config = RoundConfiguration.create_or_update(
            gara.id, 2, time_limit_minutes=None
        )
        assert config.time_limit_minutes is None
        assert config.distance == 5


@pytest.fixture
def direttore_client(app, db_session):
    nome = f"dir_{uuid.uuid4().hex[:6]}"
    utente = User(username=nome, email=f"{nome}@test.com", role=UserRole.ADMIN.value)
    utente.set_password("pwd")
    db.session.add(utente)
    db.session.commit()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": nome, "password": "pwd"},
        follow_redirects=True,
    )
    return client


@pytest.mark.unit
class TestLaRouteDelTurno:
    def test_salva_legge_e_toglie(self, direttore_client, db_session):
        gara = _gara()
        url = f"/admin/gara/{gara.id}/round-config/2"

        risposta = direttore_client.post(url, json={"time_limit_minutes": 45})
        assert risposta.status_code == 200, risposta.data
        assert risposta.get_json()["config"]["time_limit_minutes"] == 45

        elenco = direttore_client.get(f"/admin/gara/{gara.id}/round-config")
        assert elenco.get_json()["defaults"]["time_limit_minutes"] == 30

        risposta = direttore_client.post(url, json={"time_limit_minutes": 0})
        assert RoundConfiguration.get_for_gara_round(gara.id, 2).time_limit_minutes == 0

        risposta = direttore_client.post(url, json={"time_limit_minutes": None})
        assert risposta.status_code == 200
        config = RoundConfiguration.get_for_gara_round(gara.id, 2)
        assert config is None or config.time_limit_minutes is None

    def test_un_altro_campo_non_tocca_il_limite(self, direttore_client, db_session):
        gara = _gara()
        url = f"/admin/gara/{gara.id}/round-config/2"
        direttore_client.post(url, json={"time_limit_minutes": 45})
        direttore_client.post(url, json={"distance": 4})
        assert (
            RoundConfiguration.get_for_gara_round(gara.id, 2).time_limit_minutes == 45
        )

    @pytest.mark.parametrize("valore", [-1, 601, "mezz'ora"])
    def test_fuori_scala_si_rifiuta(self, direttore_client, db_session, valore):
        gara = _gara()
        risposta = direttore_client.post(
            f"/admin/gara/{gara.id}/round-config/2", json={"time_limit_minutes": valore}
        )
        assert risposta.status_code == 400
        assert RoundConfiguration.get_for_gara_round(gara.id, 2) is None

    def test_la_storia_lo_scrive_come_regola_del_turno(
        self, direttore_client, db_session
    ):
        from models.storia.service import StoriaModificheService

        gara = _gara()
        direttore_client.post(
            f"/admin/gara/{gara.id}/round-config/2", json={"time_limit_minutes": 0}
        )
        campi = {
            r.field
            for v in StoriaModificheService.voci_della_gara(gara.id)
            for r in v.fields
        }
        assert "turno_2.time_limit_minutes" in campi


@pytest.mark.unit
def test_la_storia_dice_il_limite_del_turno(app):
    from models.storia.etichette import valore

    with app.test_request_context():
        assert valore("turno_2.time_limit_minutes", "") == "come la gara"
        assert valore("turno_2.time_limit_minutes", "0") == "senza limite"
        assert valore("turno_2.time_limit_minutes", "45") == "45 minuti"


@pytest.mark.unit
@pytest.mark.parametrize("valore", [45.9, True, 1e308, "4.5"])
def test_solo_interi_dalla_route(direttore_client, db_session, valore):
    """45.9 non diventa 45, true non diventa 1 (revisione della PR #619)."""
    gara = _gara()
    risposta = direttore_client.post(
        f"/admin/gara/{gara.id}/round-config/2", json={"time_limit_minutes": valore}
    )
    assert risposta.status_code == 400
    assert RoundConfiguration.get_for_gara_round(gara.id, 2) is None


@pytest.mark.unit
def test_una_query_sola_per_tutte_le_partite_del_turno(db_session):
    """`fissa_regole` legge il turno dalla relazione della gara: nessuna query
    per partita (revisione della PR #619)."""
    from sqlalchemy import event

    gara = _gara()
    RoundConfiguration.create_or_update(gara.id, 2, time_limit_minutes=45)
    db.session.commit()
    gara = db.session.get(Gara, gara.id)
    _ = list(gara.round_configurations)
    query = []

    def conta(_conn, _cur, statement, *_a):
        if "round_configuration" in statement:
            query.append(statement)

    motore = db.engine
    event.listen(motore, "before_cursor_execute", conta)
    try:
        for _i in range(4):
            db.session.add(
                Match(gara_id=gara.id, round_number=2, status=MatchStatus.PLAYING.value)
            )
        db.session.flush()
    finally:
        event.remove(motore, "before_cursor_execute", conta)
    assert query == []
    assert {
        m.time_limit_minutes
        for m in Match.query.filter_by(gara_id=gara.id, round_number=2).all()
    } == {45}
