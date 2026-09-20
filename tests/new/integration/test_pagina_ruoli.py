"""La pagina «I tuoi ruoli» (ADR-069, fase 8a).

È il posto da cui si diventa istruttore, con lo stesso percorso di «Diventa
esaminatore». Tre cose che si possono rompere qui e solo qui:

* un ruolo che **non si chiede** — il beta tester — non deve comparire a chi
  non ce l'ha: sarebbe una porta mostrata per dire che è murata;
* la scuola compare solo a chi insegna o sta chiedendo di farlo, e si salva;
* la richiesta si offre solo a chi ha superato la soglia, e altrimenti la
  pagina lo dice invece di tacere.
"""

from __future__ import annotations

import json
import uuid

import pytest

from models.base import db
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

PASSWORD = "prova123"


def _make_user(role: str = UserRole.PLAYER.value, **kwargs) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"r_{suffix}",
        email=f"{suffix}@example.com",
        role=role,
        is_verified=True,
        onboarding_completed=True,
        **kwargs,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _client_for(app, username: str):
    db.session.commit()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=True,
    )
    return client


@pytest.fixture
def giocatore(db_session):
    # `gamification_override` apre i gate di progressione: qui si prova la
    # pagina, non la soglia — quella ha il suo test più sotto.
    user = _make_user(gamification_override=True)
    db_session.commit()
    return user


def test_la_pagina_elenca_il_ruolo_primario_e_quelli_da_chiedere(app, giocatore):
    client = _client_for(app, giocatore.username)
    pagina = client.get("/player/ruoli").get_data(as_text=True)

    assert "Giocatore" in pagina
    assert "Istruttore" in pagina
    assert "Esaminatore" in pagina


def test_il_beta_tester_non_compare_a_chi_non_ce_l_ha(app, giocatore):
    """Non si chiede: elencarlo sarebbe mostrare una porta murata."""
    client = _client_for(app, giocatore.username)
    pagina = client.get("/player/ruoli").get_data(as_text=True)

    assert "Beta tester" not in pagina


def test_il_beta_tester_compare_a_chi_ce_l_ha(app, db_session, giocatore):
    admin = _make_user(UserRole.ADMIN.value)
    RoleGrantService.grant(giocatore.id, GrantableRole.BETA_TESTER, admin)
    db_session.commit()

    client = _client_for(app, giocatore.username)
    assert "Beta tester" in client.get("/player/ruoli").get_data(as_text=True)


def test_senza_la_soglia_la_pagina_dice_che_si_apre_piu_avanti(app, db_session):
    """Un vicolo cieco muto è peggio di un «non ancora».

    Il gate va **acceso a mano**: nella suite `feature_config` è vuota, e
    `UnlockEngine` risponde «aperto» a una feature che non trova. È la stessa
    ragione per cui la soglia di produzione si prova sulla migration
    (`test_istruttore_migration.py`) e non da qui.
    """
    from models.gamification.feature_models import FeatureConfig

    db.session.add(
        FeatureConfig(
            code="request_instructor",
            name="Chiedi di diventare istruttore",
            rules=json.dumps(
                [
                    {
                        "conditions": [
                            {
                                "type": "METRIC",
                                "metric": "challenges_completed",
                                "operator": "gte",
                                "value": 5,
                            }
                        ]
                    }
                ]
            ),
            is_active=True,
        )
    )
    novellino = _make_user()
    db_session.commit()

    client = _client_for(app, novellino.username)
    pagina = client.get("/player/ruoli").get_data(as_text=True)

    assert "continuando ad allenarti" in pagina
    assert "/roles/request/instructor" not in pagina


def test_la_scuola_non_si_chiede_a_chi_non_insegna(app, giocatore):
    client = _client_for(app, giocatore.username)
    assert "Scuola o associazione" not in client.get("/player/ruoli").get_data(
        as_text=True
    )


def test_chi_insegna_vede_la_scuola_e_la_salva(app, db_session, giocatore):
    admin = _make_user(UserRole.ADMIN.value)
    RoleGrantService.grant(giocatore.id, GrantableRole.INSTRUCTOR, admin)
    db_session.commit()

    client = _client_for(app, giocatore.username)
    assert "Scuola o associazione" in client.get("/player/ruoli").get_data(as_text=True)

    client.post(
        "/player/ruoli/scuola",
        data={"organization": "Rōnin ASD"},
        follow_redirects=True,
    )
    assert db.session.get(User, giocatore.id).organization == "Rōnin ASD"


def test_la_scuola_si_puo_cancellare(app, db_session, giocatore):
    admin = _make_user(UserRole.ADMIN.value)
    RoleGrantService.grant(giocatore.id, GrantableRole.INSTRUCTOR, admin)
    giocatore.organization = "Vecchia scuola"
    db_session.commit()

    client = _client_for(app, giocatore.username)
    client.post(
        "/player/ruoli/scuola", data={"organization": "  "}, follow_redirects=True
    )

    assert db.session.get(User, giocatore.id).organization is None
