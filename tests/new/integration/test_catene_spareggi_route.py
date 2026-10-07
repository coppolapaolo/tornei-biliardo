"""Le catene degli spareggi dai moduli fino alle pagine (ADR-078).

Le regole hanno i loro unit test (`tests/new/unit/test_catene_configurabili.py`);
qui si verifica il passaggio interfaccia↔server: che i moduli di gara singola e
di campionato portino l'editor, che salvarlo scriva la catena giusta (anche
quella vuota), che il campionato la proponga alle gare non avviate, e che la
frase arrivi al regolamento e alla pagina pubblica.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import pytest
from werkzeug.datastructures import MultiDict

from models import Campionato, Gara, User
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


def _modulo_gara(nome, **catene):
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
        ("classification_system", "WINS"),
    ]
    return dati + list(catene.items())


class TestGaraSingola:
    def test_il_modulo_porta_i_due_editor(self, client, direttore):
        _login(client, direttore)
        pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)
        assert 'name="catena_turno"' in pagina
        assert 'name="catena_gara"' in pagina
        assert "js/catena_spareggi.js" in pagina
        # Le due caselle dello spareggio non ci sono più.
        assert 'name="tiebreaker_enabled"' not in pagina

    def test_la_catena_scelta_si_salva_e_arriva_al_regolamento(
        self, client, db_session, direttore
    ):
        _login(client, direttore)
        nome = f"Natale al 74 {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(
                _modulo_gara(
                    nome,
                    catena_turno="scontri_diretti,sorteggio",
                    catena_gara="scontri_diretti,differenza_rack,ssr:2",
                )
            ),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        assert json.loads(gara.catena_turno) == ["scontri_diretti", "sorteggio"]
        assert json.loads(gara.catena_gara) == [
            "scontri_diretti",
            "differenza_rack",
            "ssr:2",
        ]

        gara.status = GaraStatus.INSCRIPTION.value
        db_session.commit()
        regolamento = client.get(f"/gara/{gara.id}/regolamento").get_data(as_text=True)
        assert (
            "A pari vittorie conta lo scontro diretto, poi la differenza "
            "triangoli, poi lo spareggio SSR fino al 2° posto." in regolamento
        )
        pubblica = client.get(f"/gara/{gara.id}", follow_redirects=True).get_data(
            as_text=True
        )
        assert "A pari vittorie conta lo scontro diretto, poi il sorteggio." in (
            pubblica
        )

    def test_la_catena_vuota_resta_vuota(self, client, db_session, direttore):
        """Togliere tutti i criteri della classifica finale è una scelta:
        i pari merito restano tali, e lo spareggio non scatta."""
        from models.competition.spareggio_service import SpareggioService

        _login(client, direttore)
        nome = f"Senza spareggio {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome, catena_gara="")),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        assert gara.catena_gara == "[]"
        assert SpareggioService.tiebreakers_apply_to(gara) is False

    def test_salvare_senza_toccare_non_cambia_niente(
        self, client, db_session, direttore
    ):
        _login(client, direttore)
        nome = f"Intatta {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome)),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        valori = GaraFormParser.valori_attuali(gara)
        # L'editor manda le voci separate da virgole: è la stessa catena.
        modulo = _modulo_gara(
            nome,
            catena_turno=",".join(json.loads(valori["catena_turno"])),
            catena_gara=",".join(json.loads(valori["catena_gara"])),
        ) + [
            ("stato_iniziale", json.dumps(valori)),
            ("location", ""),
            ("available_tables", ""),
        ]
        risposta = client.post(
            f"/admin/gara/{gara.id}/edit", data=MultiDict(modulo), follow_redirects=True
        )
        assert "Nessuna modifica da salvare" in risposta.get_data(as_text=True)

    def test_cambiare_la_catena_resta_nella_storia(self, client, db_session, direttore):
        _login(client, direttore)
        nome = f"Storia {uuid.uuid4().hex[:6]}"
        client.post(
            "/admin/gara/create_standalone",
            data=MultiDict(_modulo_gara(nome)),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(name=nome).one()
        valori = GaraFormParser.valori_attuali(gara)
        modulo = _modulo_gara(nome, catena_gara="scontri_diretti") + [
            ("stato_iniziale", json.dumps(valori)),
            ("location", ""),
            ("available_tables", ""),
        ]
        client.post(f"/admin/gara/{gara.id}/edit", data=MultiDict(modulo))
        assert json.loads(db_session.get(Gara, gara.id).catena_gara) == [
            "scontri_diretti"
        ]
        campi = StoriaModificheService.campi(
            StoriaModificheService.voci_della_gara(gara.id)
        )
        assert "catena_gara" in campi
        storia = client.get(f"/admin/gara/{gara.id}/edit").get_data(as_text=True)
        assert "Scontri diretti" in storia


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

    def _modulo(self, camp, **catene):
        return MultiDict(
            [
                ("name", camp.name),
                ("campionato_type", "round_robin"),
                ("planned_gare_count", "8"),
                ("default_classification_system", "WINS"),
                ("default_rounds_count", "3"),
                ("default_odd_policy", "bye"),
            ]
            + list(catene.items())
        )

    def test_il_modulo_porta_i_tre_editor(self, client, db_session, direttore):
        camp = self._campionato(db_session, direttore)
        _login(client, direttore)
        pagina = client.get(f"/admin/campionato/{camp.id}/edit").get_data(as_text=True)
        for nome in ("default_catena_turno", "default_catena_gara", "catena_generale"):
            assert f'name="{nome}"' in pagina
        # La frase fissa di prima è sparita: la frase la compone l'editor.
        assert "Vittorie → Differenza triangoli → Ordine precedente" not in pagina

    def test_la_proposta_arriva_alle_gare_da_avviare(
        self, client, db_session, direttore
    ):
        camp = self._campionato(db_session, direttore)
        serata = Gara(
            campionato_id=camp.id,
            number=1,
            name="Lunedì 1",
            date=date.today() + timedelta(days=7),
            discipline="9_ball",
            distance=3,
            rounds_count=3,
            matchmaking_strategy="round_robin",
            status=GaraStatus.INSCRIPTION.value,
            catena_gara='["differenza_rack", "ssr:3"]',
        )
        db_session.add(serata)
        db_session.commit()
        _login(client, direttore)
        risposta = client.post(
            f"/admin/campionato/{camp.id}/edit",
            data=self._modulo(
                camp,
                default_catena_gara="scontri_diretti,ssr:3",
                catena_generale="scontri_diretti",
            ),
        )
        # Il valore proposto è cambiato: si chiede a quali gare applicarlo.
        assert "/proposta" in risposta.headers.get("Location", "")
        camp = db_session.get(Campionato, camp.id)
        assert json.loads(camp.default_catena_gara) == ["scontri_diretti", "ssr:3"]
        assert json.loads(camp.catena_generale) == ["scontri_diretti", "sorteggio"]
        campi = StoriaModificheService.campi(
            StoriaModificheService.voci_del_campionato(camp.id)
        )
        assert {"default_catena_gara", "catena_generale"} <= set(campi)

    def test_il_modale_nuova_gara_parte_dalla_proposta(
        self, client, db_session, direttore
    ):
        camp = self._campionato(db_session, direttore)
        camp.default_catena_turno = '["scontri_diretti", "sorteggio"]'
        db_session.commit()
        _login(client, direttore)
        pagina = client.get(f"/admin/campionato/{camp.id}").get_data(as_text=True)
        assert 'name="catena_turno" value="scontri_diretti,sorteggio"' in pagina
