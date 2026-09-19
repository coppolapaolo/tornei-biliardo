"""Integration tests for ADR-028 endpoint allowlist coverage.

Two assertions:
1. Every name in ENDPOINT_ROLES must correspond to a real Flask endpoint
   (catches typos when adding entries).
2. Every name in INFRASTRUCTURE_ALLOWLIST must also correspond to a real
   endpoint.

Endpoints registered in Flask but absent from both sets are treated as
"admin-only by design" (the matrix is intentionally a starting subset);
they are reported via warning, not asserted.
"""

from __future__ import annotations

import warnings

from utils.feature_flags import (
    ENDPOINT_ROLES,
    INFRASTRUCTURE_ALLOWLIST,
    is_endpoint_visible,
)


def _flask_endpoints(app) -> set[str]:
    return {rule.endpoint for rule in app.url_map.iter_rules()}


class _FakeUser:
    """Minimal user stand-in for is_endpoint_visible (no DB needed)."""

    def __init__(self, *, is_authenticated=True, is_director=False, is_admin=False):
        self.is_authenticated = is_authenticated
        self.is_director = is_director
        self.is_admin = is_admin


def test_endpoint_roles_names_are_real(app):
    """Every entry in ENDPOINT_ROLES must be a registered Flask endpoint —
    typos here would silently never match in production."""
    declared = set(ENDPOINT_ROLES.keys())
    real = _flask_endpoints(app)
    bogus = declared - real
    assert not bogus, (
        f"ENDPOINT_ROLES contains names that are NOT registered Flask "
        f"endpoints (typos?): {sorted(bogus)}"
    )


def test_infrastructure_allowlist_names_are_real(app):
    """Every entry in INFRASTRUCTURE_ALLOWLIST must be a registered endpoint."""
    real = _flask_endpoints(app)
    bogus = INFRASTRUCTURE_ALLOWLIST - real
    assert not bogus, (
        f"INFRASTRUCTURE_ALLOWLIST contains names that are NOT registered "
        f"Flask endpoints: {sorted(bogus)}"
    )


def test_request_director_visible_to_player_in_production(app, monkeypatch):
    """Regression: il POST player.request_director deve essere raggiungibile
    dai player in produzione. Senza la entry in ENDPOINT_ROLES era admin-only
    by default → 404 per il player che invia la richiesta (ADR-028)."""
    with app.test_request_context():
        # Forza il path "produzione" (in test l'allowlist è pass-through).
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)

        player = _FakeUser()
        director = _FakeUser(is_director=True)

        # Il player vede l'endpoint (può inviare la richiesta)...
        assert is_endpoint_visible("player.request_director", player)
        # ...mentre un director no: ha senso solo per chi non è ancora director,
        # coerente con la condizione del template (role == 'player').
        assert not is_endpoint_visible("player.request_director", director)


def test_nearby_gare_api_visible_to_player_in_production(app, monkeypatch):
    """Regression: l'API dietro il riquadro "Gare vicine a te" deve essere
    raggiungibile da chi vede il riquadro.

    `_nearby_gare.html` è incluso senza condizioni in
    `_player_dashboard_content.html`, e `player.dashboard` è visibile a
    player/director. L'API che alimenta quel riquadro era però assente dalla
    matrice, quindi admin-only in produzione: la fetch prendeva 404, il
    `.catch` nel template spegneva il "Caricamento…" e la sezione — che parte
    con `display: none` — non compariva mai. Nessun errore a schermo e una
    funzione morta in silenzio (ADR-028, stesso sintomo dell'issue #59)."""
    with app.test_request_context():
        # Forza il path "produzione" (in test l'allowlist è pass-through).
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)

        player = _FakeUser()
        director = _FakeUser(is_director=True)

        # Chi vede la dashboard che include il riquadro deve vederne l'API.
        assert is_endpoint_visible("player.dashboard", player)
        assert is_endpoint_visible("player.api_nearby_gare", player)
        assert is_endpoint_visible("player.api_nearby_gare", director)


def test_venues_directory_visible_to_player_in_production(app, monkeypatch):
    """Regression: l'elenco delle sale biliardo è una directory pubblica, non
    amministrazione.

    `admin.venue.venues_list` e `venue_detail` stanno nel blueprint `admin.venue`
    per ragioni storiche, ma il loro decoratore è `@login_required` e la route
    sceglie la vista in base al ruolo (`player/venues.html` a chi gioca).
    Nessuna delle due era classificata, quindi per deny-by-default erano
    admin-only **da sempre**: la voce «Sale Biliardo» spariva dal menu e chi
    arrivava per URL prendeva 404 (ADR-028, stessa dinamica di #114 e #129).

    Il flusso «chiedi di gestire questa sala» parte dalla stessa pagina e
    condivideva il destino, quindi entra nella stessa verifica.
    """
    with app.test_request_context():
        # Forza il path "produzione" (in test l'allowlist è pass-through).
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)

        player = _FakeUser()
        director = _FakeUser(is_director=True)

        for endpoint in (
            "admin.venue.venues_list",
            "admin.venue.venue_detail",
            "player.request_venue_manager",
            "player.my_venue_requests",
        ):
            assert is_endpoint_visible(endpoint, player), endpoint
            assert is_endpoint_visible(endpoint, director), endpoint


def test_venue_manager_can_edit_own_venue_in_production(app, monkeypatch):
    """Regression: un gestore di sala è quasi sempre un player.

    `edit_venue` è `@venue_manager_required`, che non implica `role=director`
    né admin. Fuori dalla matrice, il pulsante «Gestisci» sulla scheda della
    sala portava a 404 proprio a chi quella sala la gestisce. L'autorizzazione
    vera resta nel decoratore: la matrice dice solo che l'endpoint esiste.
    """
    with app.test_request_context():
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)

        player = _FakeUser()
        for endpoint in (
            "admin.venue.edit_venue",
            "admin.venue.update_table_numbers",
            "admin.venue.upload_photo",
        ):
            assert is_endpoint_visible(endpoint, player), endpoint

        # La coda delle richieste resta amministrazione: fuori dalla matrice.
        assert not is_endpoint_visible("admin.venue.venue_manager_requests", player)
        assert not is_endpoint_visible("admin.venue.create_venue", player)


def test_report_unclassified_endpoints(app):
    """Lists endpoints registered in Flask but not in any allowlist.

    Unclassified endpoints are admin-only in production by default. This
    is intentional during MVP rollout; the test only emits a warning so
    we can see the gap shrink as features are promoted.

    TODO(ADR-028 Open Items §3): when the matrix is stable (~120+ explicit
    entries) convert this warning to a hard `assert not unclassified`. At
    that point every Flask endpoint must be classified explicitly — even
    admin-only ones with `set()` — to prevent silent admin-only-by-inertia.
    """
    real = _flask_endpoints(app)
    classified = set(ENDPOINT_ROLES.keys()) | INFRASTRUCTURE_ALLOWLIST
    unclassified = real - classified
    if unclassified:
        warnings.warn(
            f"{len(unclassified)} endpoint(s) are admin-only by default "
            f"(not in ENDPOINT_ROLES nor INFRASTRUCTURE_ALLOWLIST). "
            f"Sample: {sorted(unclassified)[:10]}",
            stacklevel=2,
        )


def test_esercizi_di_gara_visibili_al_giocatore_in_produzione(app, monkeypatch):
    """Regression: gli esercizi «fra i turni» di una gara si aprono e si
    registrano da due route del blueprint ``player``, linkate dalla dashboard
    (``_player_challenges_dashboard.html``) e dalla pagina partita
    (``_match_challenge_input.html``). Senza la entry in ENDPOINT_ROLES erano
    admin-only by default → 404 proprio per i giocatori a cui il link è
    rivolto (ADR-028). Il blueprint ``challenge`` aveva avuto lo stesso
    difetto: queste due erano rimaste fuori perché stanno sotto ``player.``."""
    with app.test_request_context():
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)

        player = _FakeUser()
        director = _FakeUser(is_director=True)

        for endpoint in (
            "player.challenge_detail",
            "player.record_challenge_attempt",
        ):
            assert is_endpoint_visible(endpoint, player), endpoint
            # Il direttore che gioca la propria gara registra come gli altri.
            assert is_endpoint_visible(endpoint, director), endpoint
