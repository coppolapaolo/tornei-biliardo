"""Il drill si disegna, non solo si fotografa.

Chi propone un drill spesso non ha una foto del tavolo preparato — e una
descrizione a parole di dove vanno le bilie viene interpretata da ognuno a modo
suo. Il builder e' l'alternativa: si disegna la scena e si salva.

Salvare vuol dire **due** cose, e il test presidia che restino appaiate:
l'immagine, che serve a mostrare il drill dappertutto (catalogo, guida,
notifiche), e la scena JSON, che serve a riaprirlo e correggerlo. Da un PNG non
si torna indietro alle bilie: perdere la scena significa che l'unico modo di
spostare una bilia e' ridisegnare tutto.
"""

import json

import pytest

from models import db, User, Challenge
from models.challenge.diagram import parse_scene
from models.exceptions import ValidationError
from models.user.role_enum import UserRole

SCENA = {
    "v": 4,
    "title": "Spot shot",
    "orient": "landscape",
    "cloth": "blu",
    "ballScale": 1,
    "items": [
        {"type": "ball", "n": 1, "x": 0.5, "y": 0.5},
        {"type": "shot", "x": 0.2, "y": 0.5, "aim": {"x": 0.5, "y": 0.5}, "force": 30},
    ],
}


@pytest.fixture
def director(app):
    with app.app_context():
        user = User(
            username="builder_director",
            email="builder_director@example.com",
            password_hash="x",
            role=UserRole.DIRECTOR.value,
        )
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def drill_disegnato(app, director):
    with app.app_context():
        challenge = Challenge(
            description="Drill disegnato col builder",
            image_path="/static/uploads/challenges/disegnato.jpg",
            created_by_id=director.id,
            is_active=True,
            pass_fail_only=False,
            diagram_scene=json.dumps(SCENA, separators=(",", ":")),
        )
        db.session.add(challenge)
        db.session.commit()
        yield challenge


@pytest.fixture
def drill_fotografato(app, director):
    with app.app_context():
        challenge = Challenge(
            description="Drill nato da una foto del tavolo",
            image_path="/static/uploads/challenges/foto.jpg",
            created_by_id=director.id,
            is_active=True,
            pass_fail_only=False,
        )
        db.session.add(challenge)
        db.session.commit()
        yield challenge


class TestLaScenaSiConserva:
    def test_immagine_e_scena_stanno_insieme(self, drill_disegnato):
        """Le due cose servono a mestieri diversi e devono esserci entrambe."""
        assert drill_disegnato.image_path
        assert drill_disegnato.diagram_scene

        scena = json.loads(drill_disegnato.diagram_scene)
        assert scena["v"] == 4
        assert len(scena["items"]) == 2

    def test_il_drill_fotografato_non_ha_scena(self, drill_fotografato):
        """``NULL`` qui non è un dato mancante: dice «non è stato disegnato».

        È ciò che distingue un drill riapribile nel builder da uno che si può
        solo ri-fotografare, e va restare distinguibile.
        """
        assert drill_fotografato.diagram_scene is None


class TestScenaDaUnClient:
    """La scena arriva dal browser, cioè da dove chiunque scrive qualunque cosa."""

    def test_scena_valida_torna_normalizzata(self):
        out = parse_scene(json.dumps(SCENA, indent=4))

        assert out is not None
        assert " " not in out.split('"title"')[0]  # compatta, senza indentazione
        assert json.loads(out) == SCENA

    def test_assente_significa_nessun_disegno(self):
        assert parse_scene(None) is None
        assert parse_scene("") is None
        assert parse_scene("   ") is None

    def test_json_rotto_rifiutato(self):
        with pytest.raises(ValidationError):
            parse_scene("{non sono json")

    def test_non_oggetto_rifiutato(self):
        with pytest.raises(ValidationError):
            parse_scene("[1, 2, 3]")

    def test_versione_sconosciuta_rifiutata(self):
        """Meglio dirlo che riaprire un disegno interpretandolo a caso."""
        futura = dict(SCENA, v=99)
        with pytest.raises(ValidationError):
            parse_scene(json.dumps(futura))

    def test_senza_elementi_rifiutata(self):
        rotta = dict(SCENA)
        rotta.pop("items")
        with pytest.raises(ValidationError):
            parse_scene(json.dumps(rotta))

    def test_scena_enorme_rifiutata(self):
        """La colonna non deve diventare un deposito."""
        gonfia = dict(SCENA, items=[{"type": "ball", "pad": "x" * 1000}] * 1000)
        with pytest.raises(ValidationError):
            parse_scene(json.dumps(gonfia))

    def test_chiavi_sconosciute_si_tengono(self):
        """Il builder cambia: scartare l'ignoto farebbe perdere pezzi in silenzio."""
        domani = dict(SCENA, nuovaChiave={"qualcosa": 1})
        out = parse_scene(json.dumps(domani))

        assert out is not None
        assert json.loads(out)["nuovaChiave"] == {"qualcosa": 1}


class TestLeRotteDelBuilder:
    """La pagina e il salvataggio, con i due gate che le stanno davanti."""

    @pytest.fixture(autouse=True)
    def sblocca(self, app, director):
        """`use_drill_builder` è un gate di progressione: qui lo si scavalca.

        Si usa `gamification_override`, che è la via prevista per il debug e i
        test (US-D1), invece di seminare metriche finte: quelle mimerebbero il
        motore ABAC in un secondo posto destinato a divergere.
        """
        with app.app_context():
            user = db.session.get(User, director.id)
            assert user is not None
            user.gamification_override = True
            db.session.commit()
        yield

    def test_la_pagina_si_apre(self, client, director):
        with client.session_transaction() as sess:
            sess["_user_id"] = director.get_id()

        response = client.get("/challenges/builder")

        assert response.status_code == 200
        assert b"drill-builder" in response.data

    def test_un_player_non_disegna(self, app, client):
        """Disegnare un drill è autorialità: lo fa chi dirige, non chi gioca."""
        with app.app_context():
            player = User(
                username="builder_player",
                email="builder_player@example.com",
                password_hash="x",
                role=UserRole.PLAYER.value,
            )
            db.session.add(player)
            db.session.commit()
            player_id = player.id

        with client.session_transaction() as sess:
            sess["_user_id"] = db.session.get(User, player_id).get_id()

        response = client.get("/challenges/builder")

        assert response.status_code in (302, 403)

    def test_modificare_un_drill_fotografato_non_si_puo(
        self, client, director, drill_fotografato
    ):
        """Non c'è un disegno da riaprire: si viene rimandati indietro."""
        with client.session_transaction() as sess:
            sess["_user_id"] = director.get_id()

        response = client.get(f"/challenges/{drill_fotografato.id}/builder")

        assert response.status_code == 302

    def test_il_disegno_salvato_torna_sul_tavolo(
        self, client, director, drill_disegnato
    ):
        """Modificare deve ripartire da com'era, non da un tavolo vuoto."""
        with client.session_transaction() as sess:
            sess["_user_id"] = director.get_id()

        response = client.get(f"/challenges/{drill_disegnato.id}/builder")

        assert response.status_code == 200
        assert b"Spot shot" in response.data

    def test_salvare_senza_disegno_non_crea_niente(self, client, director):
        """Il gesto è uno solo: senza scena non nasce nemmeno l'immagine."""
        prima = Challenge.query.count()

        with client.session_transaction() as sess:
            sess["_user_id"] = director.get_id()

        response = client.post(
            "/challenges/builder",
            data={"description": "Un drill senza disegno"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 422
        assert Challenge.query.count() == prima
