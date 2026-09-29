"""A gara avviata si corregge ancora, campo per campo (ADR-075, terzo passo).

La logistica cambia subito, le regole di gioco valgono dal turno successivo,
la struttura si cambia solo annullando l'avvio. Con la strategia casuale le
regole restano quelle dell'avvio: tutti i turni esistono già.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Match, User
from models.base import utc_now
from models.competition.campi_modificabili import campi_bloccati
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.exceptions import ConflictError
from models.status_enum import GaraStatus
from models.storia.service import StoriaModificheService
from models.user.role_enum import UserRole
from routes.admin.competition.form_parser import GaraFormParser

pytestmark = pytest.mark.integration


def _utente(db_session, ruolo=UserRole.PLAYER.value) -> User:
    u = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@test.com",
        role=ruolo,
        onboarding_completed=True,
    )
    u.set_password("director123")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def direttore(db_session):
    return _utente(db_session, UserRole.DIRECTOR.value)


def _gara_avviata(db_session, direttore, strategia="amalfi", n=6):
    gara = Gara(
        number=1,
        name=f"Serata {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=2),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        location="Sala Vecchia",
        rounds_count=3,
        min_participants=2,
        max_participants=16,
        matchmaking_strategy=strategia,
        first_round_policy="random",
        odd_number_policy="bye",
        director_id=direttore.id,
    )
    db_session.add(gara)
    db_session.commit()
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for _ in range(n):
        InscriptionService.inscribe_user(_utente(db_session).id, gara.id)
    db_session.commit()
    RoundService.start_first_round(gara.id)
    db_session.commit()
    return db_session.get(Gara, gara.id)


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


class TestLaPagina:
    def test_a_gara_avviata_si_apre_la_pagina_ridotta(
        self, client, db_session, direttore
    ):
        gara = _gara_avviata(db_session, direttore)
        _login(client, direttore)
        pagina = client.get(f"/admin/gara/{gara.id}/edit").get_data(as_text=True)
        assert "Gara avviata" in pagina
        assert "Valgono dal turno 2" in pagina
        assert 'name="matchmaking_strategy"' not in pagina
        assert "annullando l" in pagina  # la struttura, col suo motivo

    def test_sala_e_distanza_in_due_voci(self, client, db_session, direttore):
        gara = _gara_avviata(db_session, direttore)
        partita = Match.query.filter_by(gara_id=gara.id, is_bye=False).first()
        _login(client, direttore)
        client.post(
            f"/admin/gara/{gara.id}/edit",
            data={
                "stato_iniziale": json.dumps(GaraFormParser.valori_attuali(gara)),
                "name": gara.name,
                "date": gara.date.isoformat(),
                "time": "20:00",
                "location": "Sala Nuova",
                "entry_fee": "",
                "description": "",
                "distance": "7",
                "discipline": "9_ball",
                "start_rule": "",
                "break_rule": "",
                "has_handicap": "false",
                "odd_number_policy": "bye",
                "x_challenge_id": "",
                "withdraw_policy": gara.withdraw_policy,
                "tiebreaker_enabled": "on" if gara.tiebreaker_enabled else "",
                "tiebreaker_until_position": str(gara.tiebreaker_until_position or 3),
                "motivo": "Si fa tardi",
            },
        )

        gara = db_session.get(Gara, gara.id)
        assert gara.location == "Sala Nuova"
        assert gara.distance == 7
        # La partita già nata resta al 5.
        assert db_session.get(Match, partita.id).effective_distance == 5

        voci = StoriaModificheService.voci_della_gara(gara.id)
        per_turno = {v.from_round: {r.field for r in v.fields} for v in voci}
        assert "distance" in per_turno[2]
        assert "location" in per_turno[None]
        assert "distance" not in per_turno[None]
        assert all(v.reason == "Si fa tardi" for v in voci)


class TestIlServizio:
    def test_la_struttura_non_si_cambia(self, db_session, direttore):
        gara = _gara_avviata(db_session, direttore)
        with pytest.raises(ConflictError, match="annullando l'avvio"):
            GaraService.update_gara(gara.id, rounds_count=5)
        db_session.rollback()

    def test_un_campo_bloccato_col_suo_valore_passa(self, db_session, direttore):
        gara = _gara_avviata(db_session, direttore)
        GaraService.update_gara(
            gara.id, rounds_count=gara.rounds_count, name="Stesso formato"
        )
        assert db_session.get(Gara, gara.id).name == "Stesso formato"

    def test_con_la_casuale_le_regole_restano(self, db_session, direttore):
        gara = _gara_avviata(db_session, direttore, strategia="random")
        assert "distance" in campi_bloccati(gara)
        with pytest.raises(ConflictError, match="casuale"):
            GaraService.update_gara(gara.id, distance=9)
        db_session.rollback()
        # La sala sì.
        GaraService.update_gara(gara.id, location="Altrove")
        assert db_session.get(Gara, gara.id).location == "Altrove"

    def test_lo_spareggio_cominciato_si_blocca(self, db_session, direttore):
        gara = _gara_avviata(db_session, direttore)
        assert "tiebreaker_enabled" not in campi_bloccati(gara)
        gara.status = GaraStatus.AWAITING_SSR.value
        db_session.commit()
        assert "tiebreaker_enabled" in campi_bloccati(gara)

    def test_a_gara_chiusa_non_si_apre_niente(self, client, db_session, direttore):
        gara = _gara_avviata(db_session, direttore)
        gara.status = GaraStatus.COMPLETED.value
        db_session.commit()
        assert gara.can_be_modified() is False
        _login(client, direttore)
        risposta = client.get(f"/admin/gara/{gara.id}/edit")
        assert risposta.status_code == 302


class TestIlTurno:
    def test_un_turno_gia_avviato_non_si_tocca(self, client, db_session, direttore):
        gara = _gara_avviata(db_session, direttore)
        _login(client, direttore)
        risposta = client.post(
            f"/admin/gara/{gara.id}/round-config/1", json={"distance": 9}
        )
        assert risposta.status_code == 409

    def test_un_turno_futuro_si_cambia_e_resta_scritto(
        self, client, db_session, direttore
    ):
        gara = _gara_avviata(db_session, direttore)
        _login(client, direttore)
        risposta = client.post(
            f"/admin/gara/{gara.id}/round-config/3", json={"distance": 9}
        )
        assert risposta.status_code == 200, risposta.get_data(as_text=True)
        voci = StoriaModificheService.voci_della_gara(gara.id)
        assert voci[0].from_round == 3
        assert voci[0].fields[0].field == "turno_3.distance"

    def test_con_la_casuale_nessun_turno(self, client, db_session, direttore):
        gara = _gara_avviata(db_session, direttore, strategia="random")
        _login(client, direttore)
        risposta = client.post(
            f"/admin/gara/{gara.id}/round-config/3", json={"distance": 9}
        )
        assert risposta.status_code == 409

    def test_a_iscrizioni_aperte_si_configura(self, client, db_session, direttore):
        """Fino al 2026-09-29 si configurava solo in preparazione."""
        gara = Gara(
            number=1,
            name="Aperta",
            date=date.today() + timedelta(days=2),
            discipline="9_ball",
            distance=5,
            rounds_count=3,
            matchmaking_strategy="amalfi",
            status=GaraStatus.INSCRIPTION.value,
            director_id=direttore.id,
        )
        db_session.add(gara)
        db_session.commit()
        _login(client, direttore)
        risposta = client.post(
            f"/admin/gara/{gara.id}/round-config/2", json={"distance": 7}
        )
        assert risposta.status_code == 200
