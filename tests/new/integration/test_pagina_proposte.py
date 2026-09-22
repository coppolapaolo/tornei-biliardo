"""Proporre una scheda e prenderla, passando dalle route (fase 8d, #173).

Quattro cose che solo il giro completo può dire:

* la casella della lettura **arriva dal modulo**: spuntata apre la scheda, e
  lasciata spenta la scheda nasce lo stesso e non legge nessuno. È la
  decisione dell'utente del 2026-09-20, e vive fra il `<form>` e il servizio —
  cioè in un posto che i test di unità non attraversano;
* una proposta indirizzata a un altro **non esiste**, nemmeno indovinandone il
  numero, né per guardarla né per prenderla;
* chi non ha il ruolo non trova la pagina da cui si propone;
* l'allowlist di produzione (ADR-028) nomina davvero questi endpoint: senza,
  in produzione sarebbero admin-only — cioè invisibili proprio a chi servono.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.istruttore import AssegnazioneService
from models.training_sheet import SheetItemSpec, SheetMeasure, TrainingSheetService
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService
from utils.feature_flags import ENDPOINT_ROLES

ISTRUTTORE = GrantableRole.INSTRUCTOR


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"pro_{uid}", email=f"pro_{uid}@test.local", role=role)
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.commit()
    return user


def _entra(client, user: User) -> None:
    """Login via sessione: `get_id()` e non l'id nudo (ADR-055).

    `g` non è per-richiesta in questa suite: senza ripulirlo, l'utente anonimo
    resta in cache e ogni richiesta risponde 302 verso il login.
    """
    from flask import g

    g.pop("_login_user", None)
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True


def _scheda(proprietario: User, nome: str):
    challenge = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:6]}",
        description="istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=True,  # «riusciti» vuole un esito netto (ADR-072)
    )
    db.session.add(challenge)
    db.session.flush()

    scheda = TrainingSheetService.create_sheet(proprietario, nome)
    TrainingSheetService.save_composition(
        scheda.id,
        proprietario,
        name=nome,
        items=[
            SheetItemSpec(
                challenge_id=challenge.id, measure=SheetMeasure.MADE, amount=5
            )
        ],
    )
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
def paolo(db_session, luca):
    """Un allievo: ha già aperto una sua scheda a Luca."""
    allievo = _user()
    sua = _scheda(allievo, "La mia")
    TrainingSheetService.add_reader(sua.id, luca.id, allievo)
    db.session.commit()
    return allievo


def _proposta(luca: User, paolo: User, nome: str = "Tecnica di base"):
    modello = _scheda(luca, nome)
    proposta = AssegnazioneService.proponi(luca, modello.id, [paolo.id])[0]
    db.session.commit()
    return proposta


# ── il lato dell'istruttore ─────────────────────────────────────────────────


def test_chi_non_e_istruttore_non_trova_la_pagina(client, paolo, luca):
    _entra(client, paolo)
    assert client.get(f"/istruttore/allievi/{luca.id}/scheda").status_code == 404


def test_un_estraneo_non_ha_una_pagina_intestata_a_lui(client, luca):
    passante = _user()
    _entra(client, luca)
    assert client.get(f"/istruttore/allievi/{passante.id}/scheda").status_code == 404


def test_l_istruttore_propone_dalla_pagina(client, luca, paolo):
    modello = _scheda(luca, "Tecnica di base")
    _entra(client, luca)

    risposta = client.post(
        f"/istruttore/allievi/{paolo.id}/scheda",
        data={"sheet_id": modello.id, "message": "Per l'autunno."},
        follow_redirects=True,
    )

    assert risposta.status_code == 200
    proposte = AssegnazioneService.proposte_per(paolo.id)
    assert len(proposte) == 1
    assert proposte[0].message == "Per l'autunno."


def test_ritirare_toglie_la_proposta(client, luca, paolo):
    proposta = _proposta(luca, paolo)
    _entra(client, luca)

    client.post(f"/istruttore/proposte/{proposta.id}/ritira", follow_redirects=True)

    assert AssegnazioneService.proposte_per(paolo.id) == []


# ── il lato dell'allievo ────────────────────────────────────────────────────


def test_la_proposta_compare_fra_le_sue_schede(client, luca, paolo):
    _proposta(luca, paolo)
    _entra(client, paolo)

    pagina = client.get("/schede/").get_data(as_text=True)
    corpo = pagina.split('<footer class="debug-footer"')[0]

    assert "ti propone una scheda" in corpo
    assert "Tecnica di base" in corpo


def test_la_proposta_di_un_altro_non_esiste(client, luca, paolo):
    proposta = _proposta(luca, paolo)
    _entra(client, _user())

    assert client.get(f"/schede/proposte/{proposta.id}").status_code == 404
    assert client.post(f"/schede/proposte/{proposta.id}/prendi").status_code == 404


def test_la_casella_spuntata_apre_la_scheda_a_chi_l_ha_data(client, luca, paolo):
    proposta = _proposta(luca, paolo)
    _entra(client, paolo)

    client.post(
        f"/schede/proposte/{proposta.id}/prendi",
        data={"apri_lettura": "1"},
        follow_redirects=True,
    )

    nata = next(
        s
        for s in TrainingSheetService.sheets_of(paolo.id)
        if s.name == "Tecnica di base"
    )
    assert nata.owner_id == paolo.id
    assert TrainingSheetService.can_read(nata, luca)


def test_senza_la_casella_la_scheda_nasce_lo_stesso_e_non_legge_nessuno(
    client, luca, paolo
):
    """Il campo assente è la casella tolta: nel POST un checkbox spento non c'è."""
    proposta = _proposta(luca, paolo)
    _entra(client, paolo)

    client.post(
        f"/schede/proposte/{proposta.id}/prendi", data={}, follow_redirects=True
    )

    nata = next(
        s
        for s in TrainingSheetService.sheets_of(paolo.id)
        if s.name == "Tecnica di base"
    )
    assert nata.owner_id == paolo.id
    assert not TrainingSheetService.can_read(nata, luca)


def test_rifiutare_non_fa_nascere_niente(client, luca, paolo):
    proposta = _proposta(luca, paolo)
    quante = len(TrainingSheetService.sheets_of(paolo.id))
    _entra(client, paolo)

    client.post(f"/schede/proposte/{proposta.id}/rifiuta", follow_redirects=True)

    assert len(TrainingSheetService.sheets_of(paolo.id)) == quante
    assert AssegnazioneService.proposte_per(paolo.id) == []


def test_una_proposta_gia_chiusa_porta_alla_scheda_nata(client, luca, paolo):
    """Chi arriva dalla notifica di ieri sera non trova un 404."""
    proposta = _proposta(luca, paolo)
    _entra(client, paolo)
    client.post(f"/schede/proposte/{proposta.id}/prendi", follow_redirects=True)

    risposta = client.get(f"/schede/proposte/{proposta.id}")

    assert risposta.status_code == 302
    assert "/schede/" in risposta.headers["Location"]


# ── l'allowlist di produzione ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "endpoint,ruolo",
    [
        ("istruttore.dai_scheda", "instructor"),
        ("istruttore.proponi_scheda", "instructor"),
        ("istruttore.ritira_proposta", "instructor"),
        ("sheet.proposta", "player"),
        ("sheet.accetta_proposta", "player"),
        ("sheet.rifiuta_proposta", "player"),
    ],
)
def test_gli_endpoint_sono_nell_allowlist(endpoint, ruolo):
    assert ruolo in ENDPOINT_ROLES.get(endpoint, set()), endpoint
