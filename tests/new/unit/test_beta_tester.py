"""Il beta tester vede le funzioni in prova, mai l'amministrazione.

Il ruolo (ADR-041, `RoleGrant`) non aggiunge **permessi**: aggiunge
**visibilita'**. L'allowlist di ADR-028 e' deny-by-default, quindi una
funzione nuova in produzione la vede solo l'admin finche' qualcuno non la
dichiara nella matrice; un beta tester la raggiunge prima, ma una volta
arrivato valgono gli stessi decoratori di tutti.

La riga che separa «funzione da provare» da «amministrazione» e' l'unica cosa
davvero pericolosa qui: sbagliarla significa mettere email e telefoni di tutti
gli iscritti sotto gli occhi di chi era stato invitato a provare una
schermata. Per questo la classificazione guarda **il decoratore** e non il
nome, e per questo il primo test la confronta con la realta' invece che con un
elenco scritto a mano.
"""

from __future__ import annotations

import pytest

from utils.feature_flags import (
    ENDPOINT_ROLES,
    e_amministrazione,
    is_endpoint_visible,
)


class UtenteFinto:
    """Stand-in per ``current_user`` (cfr. test_feature_flags.py)."""

    def __init__(self, beta=False, admin=False, director=False, id=1):
        self.is_authenticated = True
        self.is_admin = admin
        self.is_director = director
        self.is_player = not director
        self.is_beta_tester = beta
        self.is_examiner = False
        self.id = id


@pytest.fixture
def in_produzione(app):
    """L'allowlist e' pass-through in test: qui va accesa davvero."""
    testing, debug = app.config.get("TESTING"), app.config.get("DEBUG_MODE")
    app.config["TESTING"] = False
    app.config["DEBUG_MODE"] = False
    try:
        yield
    finally:
        app.config["TESTING"] = testing
        app.config["DEBUG_MODE"] = debug


@pytest.mark.unit
def test_ogni_endpoint_admin_required_e_amministrazione(app):
    """La regola si confronta con la realta', non con un elenco.

    Tre endpoint (`rating.manage_handicap_rules`, `rating.create_handicap_rule`,
    `rating.rating_statistics`) sono `@admin_required` e **non** seguono la
    convenzione di nome: con la sola regola sul prefisso sarebbero finiti
    sotto gli occhi dei beta tester. Da qui la classificazione per decoratore.
    """
    with app.app_context():
        sfuggiti = [
            endpoint
            for endpoint, vista in app.view_functions.items()
            if getattr(vista, "_richiede_admin", False)
            and not e_amministrazione(endpoint)
        ]
    assert not sfuggiti, f"non classificati come amministrazione: {sfuggiti}"


@pytest.mark.unit
def test_il_beta_tester_non_vede_nessuna_schermata_di_amministrazione(
    app, in_produzione
):
    """E' il modo in cui questa funzione puo' fare danni veri."""
    beta = UtenteFinto(beta=True)
    with app.test_request_context("/"):
        vietati = [
            endpoint
            for endpoint, vista in app.view_functions.items()
            if getattr(vista, "_richiede_admin", False)
            and is_endpoint_visible(endpoint, beta)
        ]
    assert not vietati, f"visibili a un beta tester: {vietati[:10]}"


@pytest.mark.unit
@pytest.mark.parametrize(
    "endpoint",
    [
        "admin.user.users_list",
        "admin.user.accessi",
        "gamification.admin_dashboard",
        "rating.rating_statistics",
    ],
)
def test_le_schermate_che_contengono_dati_altrui_restano_chiuse(
    app, in_produzione, endpoint
):
    """La lista utenti ha email e telefoni; gli accessi dicono chi c'era e quando."""
    with app.test_request_context("/"):
        assert is_endpoint_visible(endpoint, UtenteFinto(beta=True)) is False


@pytest.mark.unit
def test_il_beta_tester_vede_le_funzioni_dichiarate_chiuse_per_ora(app, in_produzione):
    """`set()` vuol dire «chiusa per ora», non «riservata all'amministrazione».

    `help.hints_index` e' il caso vivo: materiale di lavoro per l'interfaccia
    adattiva, che si aprira' ai player quando la consumeranno davvero. E'
    esattamente quello che un beta tester deve poter provare prima.
    """
    assert ENDPOINT_ROLES["help.hints_index"] == set()
    # Id diversi: la titolarita' e' memoizzata **per utente e per richiesta**,
    # e due utenti nella stessa richiesta esistono solo qui — in produzione
    # `current_user` e' uno.
    with app.test_request_context("/"):
        assert is_endpoint_visible("help.hints_index", UtenteFinto(id=1)) is False
        assert (
            is_endpoint_visible("help.hints_index", UtenteFinto(beta=True, id=2))
            is True
        )


@pytest.mark.unit
def test_chi_non_e_beta_tester_non_cambia_niente(app, in_produzione):
    """Il bypass non deve allargare la visibilita' di nessun altro."""
    normale = UtenteFinto()
    with app.test_request_context("/"):
        assert is_endpoint_visible("help.hints_index", normale) is False
        assert is_endpoint_visible("main.index", normale) is True
        assert is_endpoint_visible("admin.user.users_list", normale) is False


@pytest.mark.unit
def test_la_titolarita_si_chiede_una_volta_sola_per_richiesta(app, in_produzione):
    """Una pagina con venti link protetti non deve fare venti query."""
    letture = {"n": 0}

    class Contato(UtenteFinto):
        @property
        def is_beta_tester(self):
            letture["n"] += 1
            return False

        @is_beta_tester.setter
        def is_beta_tester(self, _valore):
            pass

    utente = Contato()
    with app.test_request_context("/"):
        for _ in range(20):
            is_endpoint_visible("help.hints_index", utente)
    assert letture["n"] == 1, f"interrogato {letture['n']} volte"


@pytest.mark.unit
def test_un_beta_tester_non_puo_nominarne_altri(app, db_session):
    """La revoca e' l'unico punto di contenimento: la catena lo scavalcherebbe."""
    from models.user.models import User
    from models.user.role_enum import GrantableRole, UserRole
    from models.user.role_grant_service import RoleGrantService

    tester = User(
        username="beta1", email="beta1@test.local", role=UserRole.PLAYER.value
    )
    tester.set_password("x")
    db_session.add(tester)
    db_session.commit()
    assert RoleGrantService.can_grant(tester, GrantableRole.BETA_TESTER) is False
    assert RoleGrantService.can_revoke(tester, GrantableRole.BETA_TESTER) is False


@pytest.mark.unit
def test_il_ruolo_non_si_puo_chiedere(app):
    """Lo si riceve perche' qualcuno ha deciso di farti provare qualcosa."""
    from models.user.role_enum import GrantableRole
    from models.user.role_grant_service import RoleGrantService

    policy = RoleGrantService.get_policy(GrantableRole.BETA_TESTER)
    assert policy.request_feature_code is None
    assert policy.self_propagating is False
