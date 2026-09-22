"""«Chi la legge» e «I miei istruttori», le due pagine del giocatore (fase 8b).

Sono la stessa tabella guardata dai due lati, e i test difendono i confini che
la pagina promette:

* la pagina dei lettori è **della scheda**, quindi chi non la possiede prende
  404 — e non un 403, che confermerebbe l'esistenza della scheda;
* il registro di un allievo si apre davvero, **sedute comprese**: era il
  difetto che la fase 8a aveva reso raggiungibile (le righe del registro
  portavano a una pagina che rispondeva 404);
* le note della seduta non si vedono finché il proprietario non le apre.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.training_sheet import (
    SheetItemSpec,
    SheetMeasure,
    TrainingSessionService,
    TrainingSheetService,
)
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

PASSWORD = "prova123"


def _make_user(role: str = UserRole.PLAYER.value, **kwargs) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"l_{suffix}",
        email=f"{suffix}@example.com",
        role=role,
        is_verified=True,
        onboarding_completed=True,
        gamification_override=True,
        **kwargs,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _corpo(risposta) -> str:
    """La pagina senza il Quick Login di debug, che elenca tutti gli utenti."""
    return risposta.get_data(as_text=True).split('<footer class="debug-footer"')[0]


def _client_for(app, username: str):
    db.session.commit()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=True,
    )
    return client


def _scheda(owner: User, nome: str = "Tecnica di base"):
    challenge = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:6]}",
        description="istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=True,  # «riusciti» vuole un esito netto (ADR-072)
    )
    db.session.add(challenge)
    db.session.flush()
    scheda = TrainingSheetService.create_sheet(owner, nome)
    TrainingSheetService.save_composition(
        scheda.id,
        owner,
        name=nome,
        items=[
            SheetItemSpec(
                challenge_id=challenge.id, measure=SheetMeasure.MADE, amount=5
            )
        ],
    )
    return scheda


@pytest.fixture
def admin(db_session):
    user = _make_user(UserRole.ADMIN.value)
    db_session.commit()
    return user


@pytest.fixture
def allievo(db_session):
    user = _make_user()
    db_session.commit()
    return user


@pytest.fixture
def istruttore(db_session, admin):
    user = _make_user(organization="Rōnin ASD")
    RoleGrantService.grant(user.id, GrantableRole.INSTRUCTOR, admin)
    db_session.commit()
    return user


# ────────────────────────────────────────────────────────────────────────────
# «Chi la legge»
# ────────────────────────────────────────────────────────────────────────────
def test_la_pagina_dei_lettori_e_di_chi_possiede_la_scheda(
    app, db_session, allievo, istruttore
):
    scheda = _scheda(allievo)
    db_session.commit()

    client = _client_for(app, istruttore.username)
    assert client.get(f"/schede/{scheda.id}/lettori").status_code == 404


def test_si_cerca_un_istruttore_e_gli_si_apre_la_scheda(
    app, db_session, allievo, istruttore
):
    scheda = _scheda(allievo)
    db_session.commit()
    client = _client_for(app, allievo.username)

    trovati = _corpo(
        client.get(f"/schede/{scheda.id}/lettori?cerca={istruttore.username[:6]}")
    )
    assert istruttore.username in trovati

    client.post(
        f"/schede/{scheda.id}/lettori/aggiungi",
        data={"user_id": istruttore.id},
        follow_redirects=True,
    )
    assert TrainingSheetService.can_read(
        db.session.get(type(scheda), scheda.id), istruttore
    )


def test_una_ricerca_senza_testo_non_elenca_nessuno(
    app, db_session, allievo, istruttore
):
    scheda = _scheda(allievo)
    db_session.commit()
    client = _client_for(app, allievo.username)

    pagina = _corpo(client.get(f"/schede/{scheda.id}/lettori"))

    assert istruttore.username not in pagina


# ────────────────────────────────────────────────────────────────────────────
# Il registro dell'allievo
# ────────────────────────────────────────────────────────────────────────────
def test_chi_legge_apre_il_registro_e_le_sue_sedute(
    app, db_session, allievo, istruttore
):
    """Il difetto che la 8a aveva reso raggiungibile: le righe davano 404."""
    scheda = _scheda(allievo)
    seduta = TrainingSessionService.start(scheda.id, allievo)
    TrainingSessionService.record(
        seduta.id, scheda.active_items[0].id, allievo, value=4
    )
    TrainingSessionService.close(seduta.id, allievo, notes="Braccio rigido.")
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    db_session.commit()

    client = _client_for(app, istruttore.username)

    assert client.get(f"/schede/{scheda.id}").status_code == 200
    assert client.get(f"/schede/seduta/{seduta.id}/fine").status_code == 200


def test_le_note_non_si_vedono_finche_non_si_aprono(
    app, db_session, allievo, istruttore
):
    scheda = _scheda(allievo)
    seduta = TrainingSessionService.start(scheda.id, allievo)
    TrainingSessionService.close(seduta.id, allievo, notes="Braccio rigido.")
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    db_session.commit()

    client = _client_for(app, istruttore.username)
    chiusa = _corpo(client.get(f"/schede/seduta/{seduta.id}/fine"))
    assert "Braccio rigido." not in chiusa

    TrainingSheetService.set_notes_shared(scheda.id, allievo, True)
    db_session.commit()

    aperta = _corpo(client.get(f"/schede/seduta/{seduta.id}/fine"))
    assert "Braccio rigido." in aperta


def test_un_estraneo_non_apre_niente(app, db_session, allievo):
    scheda = _scheda(allievo)
    seduta = TrainingSessionService.start(scheda.id, allievo)
    estraneo = _make_user()
    db_session.commit()

    client = _client_for(app, estraneo.username)

    assert client.get(f"/schede/{scheda.id}").status_code == 404
    assert client.get(f"/schede/seduta/{seduta.id}/fine").status_code == 404


# ────────────────────────────────────────────────────────────────────────────
# «I miei istruttori»
# ────────────────────────────────────────────────────────────────────────────
def test_i_miei_istruttori_mostra_anche_le_schede_che_non_legge_nessuno(
    app, db_session, allievo, istruttore
):
    letta = _scheda(allievo, "Tecnica di base")
    _scheda(allievo, "Prima della gara")
    TrainingSheetService.add_reader(letta.id, istruttore.id, allievo)
    db_session.commit()

    pagina = _corpo(_client_for(app, allievo.username).get("/schede/istruttori"))

    assert istruttore.username in pagina
    assert "Tecnica di base" in pagina
    assert "Prima della gara" in pagina
    assert "Non le legge nessuno" in pagina


def test_l_istruttore_si_toglie_da_solo(app, db_session, allievo, istruttore):
    scheda = _scheda(allievo)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    db_session.commit()

    client = _client_for(app, istruttore.username)
    client.post(f"/schede/{scheda.id}/lettori/esci", follow_redirects=True)

    assert client.get(f"/schede/{scheda.id}").status_code == 404
