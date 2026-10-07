"""La classifica a punti dai moduli fino alle pagine (ADR-078, emendamento).

Le regole hanno i loro unit test (`tests/new/unit/test_classifica_a_punti.py`
e `test_specifiche_conformita.py::TestLaClassificaAPunti`); qui il passaggio
interfaccia↔server: che i moduli portino i tre campi, che salvarli scriva i
punti sulla gara singola e sul campionato, che la gara di un campionato li
riceva alla nascita, e che la classifica li mostri.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from werkzeug.datastructures import MultiDict

from models import Campionato, Gara, User
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def direttore(db_session):
    user = User(
        username=f"dir_{uuid.uuid4().hex[:8]}",
        email=f"dir_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.DIRECTOR.value,
        onboarding_completed=True,
    )
    user.set_password("director123")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


def _modulo_gara(nome, sistema="POINTS", **campi):
    dati = [
        ("name", nome),
        ("date", (date.today() + timedelta(days=10)).isoformat()),
        ("time", "20:00"),
        ("discipline", "9_ball"),
        ("distance", "3"),
        ("rounds_count", "3"),
        ("min_participants", "4"),
        ("max_participants", "16"),
        ("entry_fee", "0"),
        ("matchmaking_strategy", "round_robin"),
        ("first_round_policy", "random"),
        ("odd_number_policy", "bye"),
        ("withdraw_policy", "forfeit"),
        ("classification_system", sistema),
    ]
    return dati + list(campi.items())


def _campionato(db_session, direttore, **campi):
    camp = Campionato(
        name=f"Lunedì al 74 {uuid.uuid4().hex[:6]}",
        campionato_type="round_robin",
        is_active=True,
        default_classification_system="POINTS",
        default_rounds_count=3,
        **campi,
    )
    db_session.add(camp)
    db_session.flush()
    db_session.add(
        DirectorAssignment(
            entity_type="campionato",
            entity_id=camp.id,
            user_id=direttore.id,
            assigned_by_id=direttore.id,
        )
    )
    db_session.commit()
    return camp


class TestGaraSingola:
    def test_il_modulo_porta_i_punti(self, client, direttore):
        _login(client, direttore)
        pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)
        assert '<option value="POINTS">' in pagina
        for nome in ("points_win", "points_draw", "points_loss"):
            assert f'name="{nome}"' in pagina
        assert "js/campo_punti.js" in pagina

    def test_i_punti_scelti_si_salvano(self, client, direttore):
        _login(client, direttore)
        nome = f"Natale al 74 {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(
                _modulo_gara(nome, points_win="2", points_draw="1", points_loss="0")
            ),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        assert gara.classification_system == "POINTS"
        assert (gara.points_win, gara.points_draw, gara.points_loss) == (2, 1, 0)

    def test_punti_fuori_dai_limiti_non_creano_la_gara(self, client, direttore):
        _login(client, direttore)
        nome = f"Sbagliata {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(
                _modulo_gara(nome, points_win="1", points_draw="2", points_loss="0")
            ),
            follow_redirects=True,
        )
        assert Gara.query.filter_by(name=nome).first() is None

    def test_a_vittorie_i_punti_non_si_leggono(self, client, direttore):
        """Campi nascosti, magari a metà: con un altro sistema non contano."""
        _login(client, direttore)
        nome = f"Vittorie {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome, sistema="WINS", points_win="x")),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        assert gara.points_win is None

    def test_il_regolamento_dice_i_punti(self, client, db_session, direttore):
        _login(client, direttore)
        nome = f"Regolamento {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome)),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()
        regolamento = client.get(f"/gara/{gara.id}/regolamento").get_data(as_text=True)
        assert "3 punti la vittoria, 1 il pareggio, 0 la sconfitta" in regolamento
        assert "A pari punti conta la differenza triangoli" in regolamento


class TestCampionato:
    def test_la_gara_nasce_coi_punti_del_campionato(self, db_session, direttore):
        from models.competition.services import GaraService

        camp = _campionato(
            db_session,
            direttore,
            default_points_win=2,
            default_points_draw=1,
            default_points_loss=0,
        )
        gara = GaraService.create_gara(
            number=1,
            name="Lunedì 1",
            date=date.today() + timedelta(days=7),
            discipline="9_ball",
            distance=3,
            campionato_id=camp.id,
            classification_system="POINTS",
            matchmaking_strategy="round_robin",
            odd_number_policy="bye",
            first_round_policy="random",
            anti_rematch_enabled=False,
            rounds_count=3,
        )
        assert (gara.points_win, gara.points_draw, gara.points_loss) == (2, 1, 0)

    def test_la_modifica_salva_i_punti_proposti(self, client, db_session, direttore):
        camp = _campionato(db_session, direttore)
        _login(client, direttore)
        pagina = client.get(f"/admin/campionato/{camp.id}/edit").get_data(as_text=True)
        assert 'name="default_points_win"' in pagina
        client.post(
            f"/admin/campionato/{camp.id}/edit",
            data=MultiDict(
                [
                    ("name", camp.name),
                    ("campionato_type", "round_robin"),
                    ("planned_gare_count", "8"),
                    ("default_classification_system", "POINTS"),
                    ("default_rounds_count", "3"),
                    ("default_odd_policy", "bye"),
                    ("default_points_win", "2"),
                    ("default_points_draw", "1"),
                    ("default_points_loss", "0"),
                ]
            ),
        )
        camp = db_session.get(Campionato, camp.id)
        assert (
            camp.default_points_win,
            camp.default_points_draw,
            camp.default_points_loss,
        ) == (2, 1, 0)

    def test_il_modale_nuova_gara_porta_i_punti(self, client, db_session, direttore):
        camp = _campionato(db_session, direttore, default_points_win=4)
        _login(client, direttore)
        pagina = client.get(f"/admin/campionato/{camp.id}").get_data(as_text=True)
        assert 'name="points_win"' in pagina
        assert 'value="4"' in pagina

    def test_il_wizard_scrive_i_punti(self, client, db_session, direttore):
        _login(client, direttore)
        nome = f"Wizard punti {uuid.uuid4().hex[:6]}"
        passo2 = client.post(
            "/admin/campionato/wizard/step2",
            data={
                "name": nome,
                "planned_gare_count": "8",
                "campionato_type": "amalfi",
                "default_classification_system": "POINTS",
            },
        ).get_data(as_text=True)
        assert 'name="default_points_win"' in passo2
        client.post(
            "/admin/campionato/wizard/create",
            data={
                "default_rounds_count": "3",
                "default_odd_policy": "bye",
                "default_points_win": "3",
                "default_points_draw": "2",
                "default_points_loss": "0",
            },
        )
        camp = Campionato.query.filter_by(name=nome).one()
        assert camp.default_classification_system == "POINTS"
        assert camp.default_points_draw == 2


class TestLaClassificaMostraIPunti:
    def test_la_pagina_della_gara_ha_la_colonna_punti(
        self, client, db_session, direttore
    ):
        from models.classification.gara_classification import (
            RoundClassificationService,
        )

        _login(client, direttore)
        nome = f"Classifica {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome)),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        giocatori = []
        for _ in range(2):
            sigla = uuid.uuid4().hex[:8]
            u = User(username=f"g_{sigla}", email=f"g_{sigla}@t.it")
            u.set_password("x12345678")
            db_session.add(u)
            giocatori.append(u)
        db_session.flush()
        gara.status = GaraStatus.PLAYING.value
        gara.current_round = 1
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=giocatori[0].id,
                player2_id=giocatori[1].id,
                player1_score=2,
                player2_score=1,
                winner_id=giocatori[0].id,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        db_session.commit()
        RoundClassificationService.calculate_and_save_round_classification(gara.id, 1)
        db_session.commit()

        from flask import render_template

        from models.classification.models import RoundClassification

        righe = RoundClassification.ordered_for_display(gara.id, 1)
        html = render_template(
            "direttore/_classifica.html",
            classification=righe,
            round_number=1,
            gara=gara,
        )
        assert ">Punti<" in html
        assert "Ordinata per punti: 3 punti la vittoria" in html
