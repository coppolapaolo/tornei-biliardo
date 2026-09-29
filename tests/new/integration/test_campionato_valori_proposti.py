"""Il campionato propone, la gara decide (ADR-075, quarto passo).

I valori del campionato si copiano sulla gara quando nasce. Cambiarli non tocca
le gare già create: l'app propone a quali, non ancora avviate, applicarli. Il
campionato non si blocca più alla prima gara con gli iscritti.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from models import Campionato, Gara, User
from models.campionato.proposte import proposta
from models.campionato.tournament_service import TournamentService
from models.competition.services import GaraService
from models.exceptions import ValidationError
from models.status_enum import GaraStatus
from models.storia.service import StoriaModificheService
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def direttore(db_session):
    u = User(
        username=f"dir_{uuid.uuid4().hex[:8]}",
        email=f"dir_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.DIRECTOR.value,
        onboarding_completed=True,
    )
    u.set_password("director123")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def campionato(db_session, direttore):
    camp = Campionato(
        name=f"Camp {uuid.uuid4().hex[:6]}",
        campionato_type="amalfi",
        default_entry_fee=10,
        default_start_rule="lag",
        default_break_rule="winner_breaks",
        has_handicap=True,
    )
    db_session.add(camp)
    db_session.commit()
    db_session.add(
        DirectorAssignment(
            user_id=direttore.id,
            entity_type="campionato",
            entity_id=camp.id,
            assigned_by_id=direttore.id,
        )
    )
    db_session.commit()
    return camp


def _gara(campionato, numero, **campi):
    return GaraService.create_gara(
        number=numero,
        name=f"Gara {numero}",
        date=date.today() + timedelta(days=7 * numero),
        discipline="9_ball",
        distance=5,
        campionato_id=campionato.id,
        **campi,
    )


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


class TestLaGaraNasceCopiando:
    def test_chi_apre_chi_spacca_handicap_si_copiano(self, db_session, campionato):
        gara = _gara(campionato, 1)
        assert gara.start_rule == "lag"
        assert gara.break_rule == "winner_breaks"
        assert gara.has_handicap is True

        campionato.default_break_rule = "alternate"
        db_session.commit()
        # La gara non se ne accorge: ha il suo valore.
        assert db_session.get(Gara, gara.id).effective_break_rule.value == (
            "winner_breaks"
        )


class TestLaProposta:
    def test_spuntate_solo_quelle_col_valore_vecchio(self, db_session, campionato):
        avviata = _gara(campionato, 1, entry_fee=10)
        avviata.status = GaraStatus.PLAYING.value
        avviata.current_round = 1
        uguale = _gara(campionato, 2, entry_fee=10)
        diversa = _gara(campionato, 3, entry_fee=15)
        db_session.commit()

        righe = proposta(campionato, {"default_entry_fee": ("10", "12")})
        per_gara = {r.gara.id: r.campi for r in righe}
        assert avviata.id not in per_gara
        assert per_gara[uguale.id][0].spuntato is True
        assert per_gara[diversa.id][0].spuntato is False

    def test_dalla_pagina_si_applica_alle_scelte(
        self, client, db_session, direttore, campionato
    ):
        uguale = _gara(campionato, 1, entry_fee=10)
        diversa = _gara(campionato, 2, entry_fee=15)
        db_session.commit()

        TournamentService().update_campionato(
            campionato.id, autore=direttore, default_entry_fee=12.0
        )
        voce = StoriaModificheService.voci_del_campionato(campionato.id)[0]
        _login(client, direttore)
        pagina = client.get(
            f"/admin/campionato/{campionato.id}/proposta/{voce.id}"
        ).get_data(as_text=True)
        assert f'value="{uguale.id}:entry_fee" checked' in pagina
        assert f'value="{diversa.id}:entry_fee" checked' not in pagina

        client.post(
            f"/admin/campionato/{campionato.id}/proposta/{voce.id}",
            data={"scelta": [f"{uguale.id}:entry_fee"], "motivo": "Costo tavoli"},
        )
        assert db_session.get(Gara, uguale.id).entry_fee == 12
        assert db_session.get(Gara, diversa.id).entry_fee == 15
        voci = StoriaModificheService.voci_della_gara(uguale.id)
        assert voci[0].source == "campionato"
        assert voci[0].reason == "Costo tavoli"

    def test_la_modifica_porta_alla_proposta(
        self, client, db_session, direttore, campionato
    ):
        _gara(campionato, 1, entry_fee=10)
        db_session.commit()
        _login(client, direttore)
        risposta = client.post(
            f"/admin/campionato/{campionato.id}/edit",
            data={
                "name": campionato.name,
                "planned_gare_count": "5",
                "campionato_type": "amalfi",
                "default_classification_system": "WINS",
                "default_entry_fee": "12",
                "default_rounds_count": "3",
                "default_odd_policy": "bye",
                "default_anti_rematch": "on",
                "default_start_rule": "lag",
                "default_break_rule": "winner_breaks",
                "has_handicap": "on",
            },
        )
        assert risposta.status_code == 302
        assert "/proposta/" in risposta.headers["Location"]


class TestIlCampionatoNonSiBlocca:
    def test_si_modifica_anche_con_una_gara_in_corso(self, db_session, campionato):
        gara = _gara(campionato, 1)
        gara.status = GaraStatus.PLAYING.value
        gara.current_round = 1
        db_session.commit()

        TournamentService().update_campionato(campionato.id, name="Nome nuovo")
        assert db_session.get(Campionato, campionato.id).name == "Nome nuovo"

    def test_il_sistema_si_cambia_finche_nessuna_gara_e_avviata(
        self, db_session, direttore, campionato
    ):
        # Col sistema a triangoli la X semplice non è ammessa: lista d'attesa.
        gara = _gara(campionato, 1, odd_number_policy="no")
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()

        TournamentService().update_campionato(
            campionato.id, autore=direttore, default_classification_system="RACK"
        )
        gara = db_session.get(Gara, gara.id)
        assert gara.classification_system in ("RACK", "RACKS")
        assert StoriaModificheService.voci_della_gara(gara.id)[0].source == (
            "campionato"
        )

        gara.status = GaraStatus.PLAYING.value
        gara.current_round = 1
        db_session.commit()
        with pytest.raises(ValidationError, match="avviata"):
            TournamentService().update_campionato(
                campionato.id, default_classification_system="WINS"
            )
        db_session.rollback()


def test_la_migration_copia_i_valori_che_valgono_oggi(tmp_path):
    percorso = (
        Path(__file__).resolve().parents[3]
        / "migrations"
        / "20260929_valori_del_campionato_copiati.py"
    )
    spec = importlib.util.spec_from_file_location("valori_copiati", percorso)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    db = tmp_path / "db.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE campionato (id INTEGER PRIMARY KEY, default_start_rule VARCHAR,
            default_break_rule VARCHAR, has_handicap BOOLEAN);
        CREATE TABLE gara (id INTEGER PRIMARY KEY, campionato_id INTEGER,
            start_rule VARCHAR, break_rule VARCHAR, has_handicap BOOLEAN);
        INSERT INTO campionato VALUES (1, 'lag', NULL, 1);
        INSERT INTO gara VALUES (10, 1, NULL, NULL, NULL);
        INSERT INTO gara VALUES (11, 1, 'first_player', 'loser_breaks', 0);
        INSERT INTO gara VALUES (12, NULL, NULL, NULL, NULL);
        """)
    conn.commit()
    conn.close()

    migration.upgrade_sqlite(str(db))
    migration.upgrade_sqlite(str(db))

    conn = sqlite3.connect(db)
    righe = dict(
        (r[0], r[1:])
        for r in conn.execute(
            "SELECT id, start_rule, break_rule, has_handicap FROM gara"
        )
    )
    conn.close()
    assert righe[10] == ("lag", "alternate", 1)
    assert righe[11] == ("first_player", "loser_breaks", 0)
    assert righe[12] == (None, None, None)
