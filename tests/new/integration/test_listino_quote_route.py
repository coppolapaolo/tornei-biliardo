"""Il listino delle quote dai moduli fino alle pagine (ADR-079).

Il servizio ha i suoi unit test (`tests/new/unit/test_listino_quote.py`); qui
si verifica il passaggio interfaccia↔server: che i moduli di gara singola e di
campionato portino il listino, che salvarlo crei le categorie del proprietario
giusto, e che le pagine lo mostrino al posto della quota unica.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import pytest
from werkzeug.datastructures import MultiDict

from models import Campionato, Categoria, Gara, User
from models.categoria.listino import ListinoService, VoceListino
from models.status_enum import GaraStatus
from models.storia.service import StoriaModificheService
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole
from routes.admin.competition.form_parser import GaraFormParser

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


def _listino(*coppie):
    dati = [("listino_presente", "1")]
    for nome, quota in coppie:
        dati += [("listino_id", ""), ("listino_nome", nome), ("listino_quota", quota)]
    return dati


def _modulo_gara(nome):
    return [
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
    ]


LOCANDINA = (("Serie A", "30"), ("Serie B", "20"), ("Serie C", "20"), ("Amatori", "15"))


class TestGaraSingola:
    def test_il_modulo_di_creazione_porta_l_editor(self, client, direttore):
        _login(client, direttore)
        pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)
        assert 'name="listino_presente"' in pagina
        assert 'name="listino_nome"' in pagina

    def test_creare_la_gara_col_listino_crea_le_sue_categorie(
        self, client, db_session, direttore
    ):
        _login(client, direttore)
        nome = f"Natale al 74 {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome) + _listino(*LOCANDINA)),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        categorie = {
            c.name: c.entry_fee for c in Categoria.query.filter_by(gara_id=gara.id)
        }
        assert categorie == {"Serie A": 30, "Serie B": 20, "Serie C": 20, "Amatori": 15}

        # La pagina pubblica mostra il listino, non «Gratuita».
        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()
        client.post("/auth/logout", follow_redirects=True)
        pagina = client.get(f"/gara/{gara.id}", follow_redirects=True).get_data(
            as_text=True
        )
        assert "Serie B, Serie C" in pagina
        assert "€30.00" in pagina

    def test_senza_listino_resta_la_quota_unica(self, client, db_session, direttore):
        _login(client, direttore)
        nome = f"Senza listino {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome) + _listino(("", ""))),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        assert Categoria.query.filter_by(gara_id=gara.id).count() == 0
        assert gara.usa_categorie is False

    def test_modificare_la_quota_resta_nella_storia(
        self, client, db_session, direttore
    ):
        _login(client, direttore)
        nome = f"Modifica listino {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome) + _listino(("Serie A", "30"))),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        a = Categoria.query.filter_by(gara_id=gara.id).one()

        pagina = client.get(f"/admin/gara/{gara.id}/edit").get_data(as_text=True)
        assert f'name="listino_id" value="{a.id}"' in pagina

        modulo = [
            ("stato_iniziale", json.dumps(GaraFormParser.valori_attuali(gara))),
            ("location", ""),
            ("available_tables", ""),
        ] + _modulo_gara(nome)
        modulo += [
            ("listino_presente", "1"),
            ("listino_id", str(a.id)),
            ("listino_nome", "Serie A"),
            ("listino_quota", "25"),
        ]
        risposta = client.post(
            f"/admin/gara/{gara.id}/edit", data=MultiDict(modulo), follow_redirects=True
        )
        assert "Nessuna modifica da salvare" not in risposta.get_data(as_text=True)
        assert db_session.get(Categoria, a.id).entry_fee == 25
        campi = StoriaModificheService.campi(
            StoriaModificheService.voci_della_gara(gara.id)
        )
        assert "listino" in campi

    def test_col_listino_le_categorie_si_assegnano_anche_senza_handicap(
        self, client, db_session, direttore
    ):
        """Il combo della categoria accanto agli iscritti compare col listino."""
        _login(client, direttore)
        nome = f"Combo {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome)),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        assert gara.effective_has_handicap is False
        pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert 'id="categorieModal"' not in pagina

        ListinoService.salva(gara_id=gara.id, voci=[VoceListino("Serie A", 30)])
        pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert 'id="categorieModal"' in pagina
        assert "non cambiano l’Elo" in pagina

    def test_la_quota_si_cambia_anche_dal_foglio_delle_categorie(
        self, client, db_session, direttore
    ):
        _login(client, direttore)
        nome = f"Foglio {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome) + _listino(("Serie A", "30"))),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        a = Categoria.query.filter_by(gara_id=gara.id).one()
        client.post(
            f"/admin/gara/{gara.id}/categorie/{a.id}/rename",
            data={"name": "Serie A", "entry_fee": "35"},
        )
        assert db_session.get(Categoria, a.id).entry_fee == 35


class TestCampionato:
    def _campionato(self, db_session, direttore):
        camp = Campionato(
            name=f"Lunedì al 74 {uuid.uuid4().hex[:6]}",
            campionato_type="round_robin",
            is_active=True,
            default_classification_system="WINS",
            default_rounds_count=3,
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

    def test_il_listino_del_campionato_vale_per_le_sue_serate(
        self, client, db_session, direttore
    ):
        camp = self._campionato(db_session, direttore)
        _login(client, direttore)
        assert 'name="listino_presente"' in client.get(
            f"/admin/campionato/{camp.id}/edit"
        ).get_data(as_text=True)

        client.post(
            f"/admin/campionato/{camp.id}/edit",
            data=MultiDict(
                [
                    ("name", camp.name),
                    ("campionato_type", "round_robin"),
                    ("planned_gare_count", "8"),
                    ("default_classification_system", "WINS"),
                    ("default_rounds_count", "3"),
                    ("default_odd_policy", "bye"),
                ]
                + _listino(*LOCANDINA)
            ),
        )
        assert Categoria.query.filter_by(campionato_id=camp.id).count() == 4
        campi = StoriaModificheService.campi(
            StoriaModificheService.voci_del_campionato(camp.id)
        )
        assert "listino" in campi

        serata = Gara(
            campionato_id=camp.id,
            number=1,
            name="Lunedì 1",
            date=date.today() + timedelta(days=7),
            discipline="9_ball",
            distance=3,
            rounds_count=3,
            matchmaking_strategy="round_robin",
            director_id=direttore.id,
        )
        db_session.add(serata)
        db_session.commit()
        assert serata.usa_categorie is True
        # Nella modifica della serata il listino si legge, non si cambia.
        pagina = client.get(f"/admin/gara/{serata.id}/edit").get_data(as_text=True)
        assert "Il listino è del campionato" in pagina
        assert 'name="listino_presente"' not in pagina
