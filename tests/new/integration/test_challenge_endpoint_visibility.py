"""Chi raggiunge i drill in produzione (ADR-028).

Il blueprint ``challenge`` non è mai comparso in ``ENDPOINT_ROLES``. Per la
regola deny-by-default questo lo rendeva **admin-only in produzione**: chi
apriva ``/challenges/`` prendeva 404, e la voce di menu non compariva nemmeno
(``base.html`` la gatta con ``feature_visible``). Non è una regressione
recente — è così da quando esiste la matrice; ora che il flusso di allenamento
è finito il catalogo si accende.

Il test tiene due cose distinte:

1. **Nessun endpoint del blueprint resta fuori dalla matrice.** L'omissione in
   generale non rompe la CI (``test_report_unclassified_endpoints`` emette solo
   un warning, ADR-028 Open Items §3): qui la si trasforma in un fallimento,
   per questo blueprint. Vale nei due sensi — un endpoint nuovo senza entry
   fallisce, e una entry per un endpoint che non esiste più pure.
2. **La ripartizione**: le superfici dell'allenamento le percorre chi si
   allena, quelle di autorialità solo chi dirige (``@director_required``).

Nota su cosa **non** verifica: questo è il layer L0 (maturità). Il gate di
progressione ``can_access('do_challenge')`` è ortogonale e resta dov'è —
accendere l'endpoint non lo aggira, e va bene così.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.user.models import User
from models.user.role_enum import UserRole
from utils.feature_flags import ENDPOINT_ROLES, is_endpoint_visible

PASSWORD = "prova123"

#: Le superfici dell'allenamento. Le percorre anche un director: dirigere una
#: gara non toglie il diritto di allenarsi.
TRAINING_ENDPOINTS = (
    "challenge.today",
    "challenge.challenge_catalog",
    "challenge.challenge_detail",
    "challenge.training_session",
    "challenge.training_undo",
    "challenge.start_attempt",
    "challenge.attempt_detail",
    "challenge.complete_attempt",
    "challenge.toggle_favorite",
    "challenge.rate_challenge",
    "challenge.create_x_replacement",
    "challenge.complete_x_replacement",
)

#: Autorialità e statistiche: portano ``@director_required``, quindi a un
#: player la matrice non deve prometterle.
AUTHORING_ENDPOINTS = (
    "challenge.create_challenge",
    "challenge.edit_challenge",
    "challenge.duplicate_challenge",
    "challenge.delete_challenge",
    "challenge.challenge_statistics",
    # Il builder: disegnare un drill è autorialità come crearlo da una foto —
    # lo eseguiranno tutti gli altri. Sopra `@director_required` c'è anche il
    # gate di progressione `use_drill_builder`, che è un'altra cosa e questo
    # test non lo tocca (vedi la nota sul layer L0 in testa al file).
    "challenge.diagram_builder",
    "challenge.edit_diagram",
)


class _FakeUser:
    """Sostituto d'utente per ``is_endpoint_visible``: nessun DB di mezzo."""

    def __init__(self, *, is_authenticated=True, is_director=False, is_admin=False):
        self.is_authenticated = is_authenticated
        self.is_director = is_director
        self.is_admin = is_admin


@pytest.fixture
def production(app, monkeypatch):
    """Contesto di richiesta col percorso produzione forzato.

    In test l'allowlist è pass-through: senza questo, ogni assert passerebbe
    verificando il nulla.
    """
    with app.test_request_context():
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)
        yield


def test_every_challenge_endpoint_is_classified(app):
    """Le due liste sopra devono coincidere col blueprint reale.

    Fallisce sia se una route nuova non è stata decisa, sia se una entry
    sopravvive a una route che non c'è più.
    """
    real = {
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith("challenge.")
    }
    declared = set(TRAINING_ENDPOINTS) | set(AUTHORING_ENDPOINTS)

    assert real == declared, (
        "il blueprint challenge e le liste di questo test divergono: "
        f"senza entry in ENDPOINT_ROLES {sorted(real - declared)}, "
        f"entry per route inesistenti {sorted(declared - real)}"
    )
    assert not (declared - set(ENDPOINT_ROLES)), (
        "endpoint del blueprint challenge assenti da ENDPOINT_ROLES → "
        f"admin-only in produzione: {sorted(declared - set(ENDPOINT_ROLES))}"
    )


@pytest.mark.parametrize("endpoint", TRAINING_ENDPOINTS)
def test_a_player_reaches_the_training_surfaces(production, endpoint):
    assert is_endpoint_visible(endpoint, _FakeUser())


@pytest.mark.parametrize("endpoint", TRAINING_ENDPOINTS)
def test_a_director_trains_too(production, endpoint):
    assert is_endpoint_visible(endpoint, _FakeUser(is_director=True))


@pytest.mark.parametrize("endpoint", AUTHORING_ENDPOINTS)
def test_a_player_does_not_author_drills(production, endpoint):
    """La matrice non deve promettere ciò che ``@director_required`` nega:
    altrimenti il pulsante compare e la POST risponde 403."""
    assert not is_endpoint_visible(endpoint, _FakeUser())


@pytest.mark.parametrize("endpoint", AUTHORING_ENDPOINTS)
def test_a_director_authors_drills(production, endpoint):
    assert is_endpoint_visible(endpoint, _FakeUser(is_director=True))


@pytest.mark.parametrize("endpoint", TRAINING_ENDPOINTS + AUTHORING_ENDPOINTS)
def test_an_anonymous_visitor_sees_nothing(production, endpoint):
    """I drill stanno dietro il login: nessuna voce è pubblica."""
    assert not is_endpoint_visible(endpoint, _FakeUser(is_authenticated=False))


class TestTheRealRequest:
    """Il percorso vero, non solo la funzione di decisione.

    ``is_endpoint_visible`` potrebbe dire la cosa giusta senza che il
    middleware la applichi: qui si bussa alla porta.
    """

    def _login(self, app, role=UserRole.PLAYER.value):
        user = User(
            username=f"u_{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            role=role,
            onboarding_completed=True,
        )
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()

        client = app.test_client()
        client.post(
            "/auth/login",
            data={"username": user.username, "password": PASSWORD},
            follow_redirects=True,
        )
        return client

    def _get(self, app, client, path):
        """GET col percorso produzione attivo, ripristinando la config dopo."""
        app.config["TESTING"] = False
        app.config["DEBUG_MODE"] = False
        try:
            return client.get(path)
        finally:
            app.config["TESTING"] = True
            app.config["DEBUG_MODE"] = True

    def test_a_player_opens_the_catalog(self, app, db_session):
        """Era 404 per tutti i non-admin: è il motivo di questa modifica."""
        client = self._login(app)
        assert self._get(app, client, "/challenges/").status_code == 200

    def test_a_player_is_not_offered_the_authoring_page(self, app, db_session):
        """Non è un 404 secco: il blueprint ha un errorhandler(404) che
        rimbalza al catalogo con un flash. Quello che conta è che la pagina
        di creazione non venga **servita**."""
        client = self._login(app)
        response = self._get(app, client, "/challenges/create")
        assert response.status_code != 200
        assert response.headers.get("Location", "").endswith("/challenges/")

    def test_a_director_opens_the_authoring_page(self, app, db_session):
        client = self._login(app, role=UserRole.DIRECTOR.value)
        assert self._get(app, client, "/challenges/create").status_code == 200
