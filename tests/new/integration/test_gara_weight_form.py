"""Il peso della prova esiste in una schermata e arriva al database (issue #64).

Il parser ha i suoi unit test (`tests/new/unit/test_gara_weight_form.py`); qui
si verifica il passaggio che quelli non vedono — che il campo **stia davvero in
un modulo** e che un salvataggio completo lo porti fino alla colonna. È la
stessa distinzione per cui esiste `test_bracket_options_form.py`: il peso era
leggibile e pesato dall'aggregatore da mesi (ADR-053), ma l'unica schermata che
sapesse impostarlo era quella del playoff, quindi per ogni altra gara la
funzione non esisteva.

Un caso qui è di regressione e non di funzione: `create_gara` chiamava
`parser.parse()` **fuori** dal proprio `try`, quindi un modulo malformato
diventava un 500 invece di un messaggio. Non l'ha introdotto il peso — la riga
`int(request.form["distance"])` fa lo stesso da sempre — ma il peso è il primo
campo che solleva *di proposito*, quindi il difetto passava da latente a
raggiungibile con un valore che un direttore può digitare davvero.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, User
from models.campionato.services import TournamentService
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def director(db_session):
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


@pytest.fixture
def campionato(db_session, director):
    camp = TournamentService().create_campionato_with_director(
        name=f"Camp_{uuid.uuid4().hex[:6]}",
        creator_user_id=director.id,
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=3,
    )
    db_session.commit()
    return camp


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


def _form(campionato_id, **overrides):
    campi = {
        "campionato_id": str(campionato_id),
        "number": "1",
        "name": f"Prova {uuid.uuid4().hex[:6]}",
        "date": (date.today() + timedelta(days=10)).isoformat(),
        "time": "20:00",
        "discipline": "9_ball",
        "distance": "5",
        "rounds_count": "3",
        "min_participants": "4",
        "max_participants": "16",
        "entry_fee": "0",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "withdraw_policy": "forfeit",
    }
    campi.update(overrides)
    return campi


class TestIlCampoEsisteNelleSchermate:
    def test_il_modulo_di_creazione_ha_il_campo(self, client, director, campionato):
        _login(client, director)
        pagina = client.get(f"/admin/campionato/{campionato.id}").get_data(as_text=True)

        assert 'name="weight"' in pagina

    def test_il_modulo_di_modifica_ha_il_campo(
        self, client, db_session, director, campionato
    ):
        _login(client, director)
        client.post(
            "/admin/gara/create", data=_form(campionato.id), follow_redirects=True
        )
        gara = Gara.query.filter_by(campionato_id=campionato.id).one()

        pagina = client.get(f"/admin/gara/{gara.id}/edit").get_data(as_text=True)

        assert 'name="weight"' in pagina


class TestIlPesoArrivaAlDatabase:
    def test_salva_il_peso_scelto(self, client, db_session, director, campionato):
        _login(client, director)
        dati = _form(campionato.id, weight="3")

        client.post("/admin/gara/create", data=dati, follow_redirects=True)

        gara = Gara.query.filter_by(name=dati["name"]).one()
        assert gara.weight == 3
        assert gara.classification_weight == 3

    def test_senza_il_campo_la_gara_nasce_a_uno(
        self, client, db_session, director, campionato
    ):
        """Il comportamento storico resta il default."""
        _login(client, director)
        dati = _form(campionato.id)

        client.post("/admin/gara/create", data=dati, follow_redirects=True)

        gara = Gara.query.filter_by(name=dati["name"]).one()
        assert gara.weight == 1

    def test_la_modifica_aggiorna_il_peso(
        self, client, db_session, director, campionato
    ):
        _login(client, director)
        client.post(
            "/admin/gara/create",
            data=_form(campionato.id, weight="2"),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(campionato_id=campionato.id).one()

        modifica = _form(campionato.id, weight="4")
        modifica.pop("campionato_id")
        modifica.pop("number")
        modifica["name"] = gara.name
        client.post(f"/admin/gara/{gara.id}/edit", data=modifica, follow_redirects=True)

        assert db_session.get(Gara, gara.id).weight == 4


class TestUnPesoNonValidoNonRompeLaPagina:
    def test_la_creazione_risponde_con_un_messaggio_non_con_un_500(
        self, client, db_session, director, campionato
    ):
        """`parse()` solleva: la route deve accorgersene, non esplodere."""
        _login(client, director)
        dati = _form(campionato.id, weight="0")

        risposta = client.post("/admin/gara/create", data=dati, follow_redirects=True)

        assert risposta.status_code == 200
        assert Gara.query.filter_by(name=dati["name"]).first() is None

    def test_la_modifica_risponde_con_un_messaggio_non_con_un_500(
        self, client, db_session, director, campionato
    ):
        _login(client, director)
        client.post(
            "/admin/gara/create",
            data=_form(campionato.id, weight="2"),
            follow_redirects=True,
        )
        gara = Gara.query.filter_by(campionato_id=campionato.id).one()

        modifica = _form(campionato.id, weight="-1")
        modifica.pop("campionato_id")
        modifica.pop("number")
        risposta = client.post(
            f"/admin/gara/{gara.id}/edit", data=modifica, follow_redirects=True
        )

        assert risposta.status_code == 200
        # Il peso valido di prima resta: un modulo rifiutato non scrive nulla.
        assert db_session.get(Gara, gara.id).weight == 2


class TestIlPesoSiVede:
    """Un peso che nessuno può leggere è mezza funzione.

    Il contrassegno compare **solo** quando il peso non è 1: una prova normale
    non porta decorazioni, così il segno resta ad alto segnale nel momento in
    cui c'è qualcosa da segnalare. È lo stesso criterio per cui l'elenco non
    mostra un badge «gratuita» accanto a ogni quota diversa da zero.
    """

    def test_una_prova_pesata_lo_dichiara_nell_elenco(
        self, client, db_session, director, campionato
    ):
        _login(client, director)
        client.post(
            "/admin/gara/create",
            data=_form(campionato.id, weight="3"),
            follow_redirects=True,
        )

        pagina = client.get(f"/admin/campionato/{campionato.id}").get_data(as_text=True)

        assert "&times;3" in pagina

    def test_una_prova_normale_non_porta_contrassegni(
        self, client, db_session, director, campionato
    ):
        _login(client, director)
        client.post(
            "/admin/gara/create", data=_form(campionato.id), follow_redirects=True
        )

        pagina = client.get(f"/admin/campionato/{campionato.id}").get_data(as_text=True)

        assert "&times;1" not in pagina
