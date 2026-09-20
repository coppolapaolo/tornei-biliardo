"""Dare una scheda a tutto il corso, passando dalle route (fase 8d₃, #173).

Quattro cose che solo il giro completo può dire:

* una proposta a tutto il gruppo resta **N proposte**, una per allievo,
  ciascuna con la sua casella della lettura: il gruppo decide a chi parte
  l'invito, non chi lo accetta (ADR-069);
* chi ha già una tua proposta in attesa viene **saltato**, e la pagina lo dice
  — il servizio lo fa in silenzio, ed è la route a confrontare i due numeri;
* «è il livello dopo» promuove, per ciascuno, **la sua** copia della scheda
  del gruppo: è la mappa allievo→scheda che vive fra il `<form>` e il
  servizio, cioè in un posto che i test di unità non attraversano;
* l'allowlist di produzione (ADR-028) nomina davvero questi endpoint: senza,
  in produzione sarebbero admin-only, cioè invisibili proprio a chi servono.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.istruttore import AssegnazioneService, GruppoService
from models.istruttore.models import TrainingAssignment
from models.training_sheet import SheetItemSpec, SheetMeasure, TrainingSheetService
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService
from utils.feature_flags import ENDPOINT_ROLES

ISTRUTTORE = GrantableRole.INSTRUCTOR


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"gru_{uid}", email=f"gru_{uid}@test.local", role=role)
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.commit()
    return user


def _entra(client, user: User) -> None:
    """Login via sessione: `get_id()` e non l'id nudo (ADR-055)."""
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
        pass_fail_only=False,
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
def corso(db_session, luca):
    gruppo = GruppoService.crea(luca, "Base 1")
    db.session.commit()
    return gruppo


def _allievo_nel(corso, luca) -> User:
    """Un giocatore che apre una scheda a Luca ed entra nel corso."""
    allievo = _user()
    sua = _scheda(allievo, "La mia")
    TrainingSheetService.add_reader(sua.id, luca.id, allievo)
    GruppoService.aggiungi(corso.id, luca, allievo.id)
    db.session.commit()
    return allievo


# ── chi può aprirla ─────────────────────────────────────────────────────────


def test_chi_non_e_istruttore_non_trova_la_pagina(client, corso, luca):
    passante = _user()
    _entra(client, passante)
    assert client.get(f"/istruttore/gruppi/{corso.id}/scheda").status_code == 404


def test_il_gruppo_di_un_altro_istruttore_non_esiste(client, corso, admin):
    altro = _user()
    RoleGrantService.grant(altro.id, ISTRUTTORE, admin)
    db.session.commit()
    _entra(client, altro)
    assert client.get(f"/istruttore/gruppi/{corso.id}/scheda").status_code == 404


# ── il giro ─────────────────────────────────────────────────────────────────


def test_una_proposta_al_corso_e_una_proposta_a_testa(client, luca, corso):
    allievi = [_allievo_nel(corso, luca) for _ in range(3)]
    modello = _scheda(luca, "Tecnica di base")
    _entra(client, luca)

    risposta = client.post(
        f"/istruttore/gruppi/{corso.id}/scheda",
        data={"sheet_id": modello.id, "message": "Per l'autunno."},
        follow_redirects=True,
    )
    assert risposta.status_code == 200

    for allievo in allievi:
        proposte = AssegnazioneService.proposte_per(allievo.id)
        assert len(proposte) == 1
        assert proposte[0].group_id == corso.id
        assert proposte[0].message == "Per l'autunno."


def test_chi_ha_gia_una_proposta_in_attesa_viene_saltato_e_si_dice(client, luca, corso):
    primo = _allievo_nel(corso, luca)
    secondo = _allievo_nel(corso, luca)
    gia = _scheda(luca, "Un'altra")
    AssegnazioneService.proponi(luca, gia.id, [primo.id])
    db.session.commit()

    modello = _scheda(luca, "Tecnica di base")
    _entra(client, luca)
    risposta = client.post(
        f"/istruttore/gruppi/{corso.id}/scheda",
        data={"sheet_id": modello.id},
        follow_redirects=True,
    )

    pagina = risposta.get_data(as_text=True)
    assert "1 su 2" in pagina
    # Al primo resta la proposta di prima, e basta: non gliene sono arrivate due.
    assert [p.source_sheet_id for p in AssegnazioneService.proposte_per(primo.id)] == [
        gia.id
    ]
    assert [
        p.source_sheet_id for p in AssegnazioneService.proposte_per(secondo.id)
    ] == [modello.id]


def test_a_chi_ce_l_ha_gia_non_riparte(client, luca, corso):
    """Un doppione della stessa scheda sarebbe una seconda copia da riempire."""
    presa = _allievo_nel(corso, luca)
    nuovo = _allievo_nel(corso, luca)
    modello = _scheda(luca, "Tecnica di base")
    proposta = AssegnazioneService.proponi(
        luca, modello.id, [presa.id], group_id=corso.id
    )[0]
    AssegnazioneService.accetta(proposta.id, presa)
    db.session.commit()

    _entra(client, luca)
    client.post(
        f"/istruttore/gruppi/{corso.id}/scheda",
        data={"sheet_id": modello.id},
        follow_redirects=True,
    )

    assert AssegnazioneService.proposte_per(presa.id) == []
    assert len(AssegnazioneService.proposte_per(nuovo.id)) == 1


def test_chi_l_ha_archiviata_la_ririceve(client, luca, corso):
    """La sua copia non c'è più: rimandargliela ha senso."""
    allievo = _allievo_nel(corso, luca)
    modello = _scheda(luca, "Tecnica di base")
    proposta = AssegnazioneService.proponi(
        luca, modello.id, [allievo.id], group_id=corso.id
    )[0]
    copia = AssegnazioneService.accetta(proposta.id, allievo)
    TrainingSheetService.archive_sheet(copia.id, allievo)
    db.session.commit()

    _entra(client, luca)
    client.post(
        f"/istruttore/gruppi/{corso.id}/scheda",
        data={"sheet_id": modello.id},
        follow_redirects=True,
    )

    assert len(AssegnazioneService.proposte_per(allievo.id)) == 1


def test_senza_allievi_non_parte_niente(client, luca, corso):
    modello = _scheda(luca, "Tecnica di base")
    _entra(client, luca)

    client.post(
        f"/istruttore/gruppi/{corso.id}/scheda",
        data={"sheet_id": modello.id},
        follow_redirects=True,
    )

    assert TrainingAssignment.query.filter_by(group_id=corso.id).count() == 0


def test_il_livello_dopo_promuove_la_copia_di_ciascuno(client, luca, corso):
    """La scheda nuova è una per tutti, la scheda lasciata indietro è la sua."""
    allievi = [_allievo_nel(corso, luca) for _ in range(2)]
    primo_giro = _scheda(luca, "Livello 1")
    nate = AssegnazioneService.proponi(
        luca, primo_giro.id, [a.id for a in allievi], group_id=corso.id
    )
    copie = {
        proposta.user_id: AssegnazioneService.accetta(proposta.id, allievo).id
        for proposta, allievo in zip(nate, allievi)
    }
    db.session.commit()

    secondo_giro = _scheda(luca, "Livello 2")
    _entra(client, luca)
    client.post(
        f"/istruttore/gruppi/{corso.id}/scheda",
        data={"sheet_id": secondo_giro.id, "promuove": "1"},
        follow_redirects=True,
    )

    for allievo in allievi:
        proposta = AssegnazioneService.proposte_per(allievo.id)[0]
        assert proposta.promotes_sheet_id == copie[allievo.id]


def test_la_pagina_del_gruppo_mostra_la_scheda_comune(client, luca, corso):
    allievo = _allievo_nel(corso, luca)
    modello = _scheda(luca, "Tecnica di base")
    proposta = AssegnazioneService.proponi(
        luca, modello.id, [allievo.id], group_id=corso.id
    )[0]
    AssegnazioneService.accetta(proposta.id, allievo)
    db.session.commit()

    _entra(client, luca)
    pagina = client.get(f"/istruttore/gruppi/{corso.id}").get_data(as_text=True)

    assert "Tecnica di base" in pagina
    assert "1 su 1" in pagina


# ── la produzione ───────────────────────────────────────────────────────────


def test_gli_endpoint_nuovi_sono_nell_allowlist():
    """Senza, in produzione sarebbero admin-only: 404 proprio per l'istruttore."""
    for endpoint in ("istruttore.scheda_gruppo", "istruttore.proponi_al_gruppo"):
        assert ENDPOINT_ROLES.get(endpoint) == {"instructor"}
