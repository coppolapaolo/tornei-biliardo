"""Le pagine dell'istruttore: «I miei allievi» e i gruppi (fase 8c, #173).

Quattro cose che solo il giro completo può dire, e che i test di unità non
vedono:

* chi non ha il ruolo prende **404**, non una pagina che gli spiega che
  mestiere non fa;
* il gruppo di un altro istruttore non esiste, nemmeno indovinandone il numero;
* «metti in un gruppo» è un gesto solo per aggiungere, spostare e togliere, e
  passa dalle route vere col token CSRF che i test non controllano;
* l'allowlist di produzione (ADR-028) nomina davvero questi endpoint: senza,
  in produzione sarebbero admin-only — cioè invisibili proprio all'istruttore.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.istruttore import GruppoService
from models.training_sheet import SheetItemSpec, SheetMeasure, TrainingSheetService
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService
from utils.feature_flags import ENDPOINT_ROLES

ISTRUTTORE = GrantableRole.INSTRUCTOR


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"pag_{uid}", email=f"pag_{uid}@test.local", role=role)
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.commit()
    return user


def _entra(client, user: User) -> None:
    """Login via sessione: `get_id()` e non l'id nudo (ADR-055).

    La riga su `g` non è superflua. In questa suite il contesto applicativo è
    uno solo per tutta la sessione, quindi `g` **non** è per-richiesta: basta
    che qualcosa abbia letto `current_user` durante l'allestimento — e
    `RoleGrantService.grant` lo fa — perché l'utente anonimo resti in cache e
    ogni richiesta successiva risponda 302 verso il login, senza dire perché.
    """
    from flask import g

    g.pop("_login_user", None)
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True


def _scheda_aperta_a(allievo: User, istruttore: User, nome: str = "Tecnica"):
    challenge = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:6]}",
        description="istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=False,
    )
    db.session.add(challenge)
    db.session.flush()

    scheda = TrainingSheetService.create_sheet(allievo, nome)
    TrainingSheetService.save_composition(
        scheda.id,
        allievo,
        name=nome,
        items=[
            SheetItemSpec(
                challenge_id=challenge.id, measure=SheetMeasure.MADE, amount=5
            )
        ],
    )
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    db.session.commit()
    return scheda


@pytest.fixture
def admin(db_session):
    return _user(UserRole.ADMIN.value)


@pytest.fixture
def luca(db_session, admin):
    istruttore = _user()
    RoleGrantService.grant(istruttore.id, ISTRUTTORE, admin)
    db.session.commit()
    return istruttore


@pytest.fixture
def paolo(db_session):
    return _user()


# ── chi entra e chi no ──────────────────────────────────────────────────────


def test_chi_non_e_istruttore_non_trova_la_pagina(client, paolo):
    _entra(client, paolo)
    assert client.get("/istruttore/allievi").status_code == 404


def test_l_istruttore_la_apre(client, luca):
    _entra(client, luca)
    risposta = client.get("/istruttore/allievi")
    assert risposta.status_code == 200
    assert "Nessun allievo" in risposta.get_data(as_text=True)


def test_l_allievo_compare_appena_apre_una_scheda(client, luca, paolo):
    _scheda_aperta_a(paolo, luca)
    _entra(client, luca)

    pagina = client.get("/istruttore/allievi").get_data(as_text=True)
    # Il Quick Login di debug elenca tutti gli utenti: si guarda solo il corpo.
    corpo = pagina.split('<footer class="debug-footer"')[0]

    assert paolo.username in corpo
    assert "Ti hanno appena aperto una scheda" in corpo


# ── i gruppi ────────────────────────────────────────────────────────────────


def test_si_crea_un_gruppo_e_si_finisce_dentro(client, luca):
    _entra(client, luca)

    risposta = client.post(
        "/istruttore/gruppi/nuovo",
        data={"name": "Base 1 · autunno", "started_on": "2026-09-15"},
    )

    assert risposta.status_code == 302
    gruppo = GruppoService.gruppi_di(luca.id)[0]
    assert risposta.headers["Location"].endswith(f"/istruttore/gruppi/{gruppo.id}")
    assert gruppo.name == "Base 1 · autunno"


def test_un_gruppo_senza_nome_non_nasce(client, luca):
    _entra(client, luca)
    risposta = client.post("/istruttore/gruppi/nuovo", data={"name": "  "})
    assert risposta.status_code == 302
    assert GruppoService.gruppi_di(luca.id) == []


def test_il_gruppo_di_un_altro_istruttore_non_esiste(client, admin, luca):
    altro = _user()
    RoleGrantService.grant(altro.id, ISTRUTTORE, admin)
    gruppo = GruppoService.crea(altro, "Suo")
    db.session.commit()

    _entra(client, luca)
    assert client.get(f"/istruttore/gruppi/{gruppo.id}").status_code == 404


def test_mettere_spostare_e_togliere_sono_lo_stesso_gesto(client, luca, paolo):
    _scheda_aperta_a(paolo, luca)
    base = GruppoService.crea(luca, "Base 1")
    intermedio = GruppoService.crea(luca, "Intermedio 1")
    db.session.commit()
    _entra(client, luca)

    client.post(
        f"/istruttore/allievi/{paolo.id}/gruppo", data={"group_id": str(base.id)}
    )
    assert [m.user_id for m in base.active_members] == [paolo.id]

    client.post(
        f"/istruttore/allievi/{paolo.id}/gruppo", data={"group_id": str(intermedio.id)}
    )
    assert base.active_members == []
    assert [m.user_id for m in intermedio.active_members] == [paolo.id]

    client.post(f"/istruttore/allievi/{paolo.id}/gruppo", data={"group_id": ""})
    assert intermedio.active_members == []


def test_non_si_mette_in_un_gruppo_chi_non_ti_ha_aperto_niente(client, luca, paolo):
    gruppo = GruppoService.crea(luca, "Base 1")
    db.session.commit()
    _entra(client, luca)

    client.post(
        f"/istruttore/allievi/{paolo.id}/gruppo", data={"group_id": str(gruppo.id)}
    )

    assert gruppo.active_members == []


def test_chiudere_il_corso_lo_lascia_nello_storico(client, luca, paolo):
    _scheda_aperta_a(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)
    db.session.commit()
    _entra(client, luca)

    client.post(f"/istruttore/gruppi/{gruppo.id}/chiudi")

    assert not gruppo.is_open
    assert gruppo.active_members == []
    pagina = client.get("/istruttore/gruppi").get_data(as_text=True)
    assert "Lo storico dei tuoi gruppi" in pagina


def test_il_filtro_per_gruppo_restringe_l_elenco(client, luca, paolo):
    fuori = _user()
    _scheda_aperta_a(paolo, luca)
    _scheda_aperta_a(fuori, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)
    db.session.commit()
    _entra(client, luca)

    corpo = (
        client.get(f"/istruttore/allievi?gruppo={gruppo.id}")
        .get_data(as_text=True)
        .split('<footer class="debug-footer"')[0]
    )

    assert paolo.username in corpo
    assert fuori.username not in corpo


# ── produzione ──────────────────────────────────────────────────────────────


def test_gli_endpoint_sono_nell_allowlist(app):
    """Senza, in produzione sarebbero admin-only: invisibili all'istruttore."""
    nostri = [
        regola.endpoint
        for regola in app.url_map.iter_rules()
        if regola.endpoint.startswith("istruttore.")
    ]
    assert nostri, "il blueprint non è registrato"
    for endpoint in nostri:
        assert endpoint in ENDPOINT_ROLES, endpoint
        assert "instructor" in ENDPOINT_ROLES[endpoint], endpoint
