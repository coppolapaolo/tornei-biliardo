"""«Oggi», il catalogo che si filtra e la scheda, dalle route (fase 4c).

I filtri sono collegamenti: qui si verifica che l'indirizzo filtri davvero, che
la pillola accesa porti a spegnersi, e che la variante scelta nell'allenamento
arrivi sulla prova.
"""

from __future__ import annotations

import uuid

from models.base import db
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.profile_service import ChallengeProfileService
from models.user.models import User
from models.user.role_enum import UserRole


def _utente(ruolo=UserRole.PLAYER.value) -> int:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"u_{suffix}",
        email=f"u_{suffix}@test.local",
        role=ruolo,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.commit()
    return user.id


def _login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = db.session.get(User, user_id).get_id()
        session["_fresh"] = True


def _esercizio(titolo: str, **profilo) -> int:
    c = Challenge(
        title=titolo,
        description="Istruzioni",
        image_path="x.png",
        pass_fail_only=False,
        max_score=10,
        is_active=True,
    )
    db.session.add(c)
    db.session.commit()
    if profilo:
        ChallengeProfileService.set_profile(c.id, **profilo)
        db.session.commit()
    return c.id


def test_oggi_senza_storia_invita_a_cominciare(app, client):
    with app.app_context():
        _esercizio(f"Uno {uuid.uuid4().hex[:5]}")
        player = _utente()
    _login(client, player)
    pagina = client.get("/challenges/").get_data(as_text=True)
    assert "Per cominciare" in pagina
    assert "Apri il catalogo" in pagina
    assert "/challenges/catalog" in pagina


def test_l_indirizzo_filtra_il_catalogo(app, client):
    sigla = uuid.uuid4().hex[:6]
    with app.app_context():
        _esercizio(f"ColDraw {sigla}", abilita=["posizione"], gesti=["draw"])
        _esercizio(f"ColoStop {sigla}", abilita=["posizione"], gesti=["stop"])
        player = _utente()
    _login(client, player)

    tutto = client.get("/challenges/catalog").get_data(as_text=True)
    assert f"ColDraw {sigla}" in tutto and f"ColoStop {sigla}" in tutto

    draw = client.get("/challenges/catalog?gesto=draw").get_data(as_text=True)
    assert f"ColDraw {sigla}" in draw
    assert f"ColoStop {sigla}" not in draw
    # la pillola accesa porta a spegnersi, le altre sommano il filtro
    assert 'href="/challenges/catalog"\n   aria-current="true">draw' in draw
    assert "/challenges/catalog?abilita=posizione&amp;gesto=draw" in draw


def test_un_filtro_sconosciuto_non_rompe_la_pagina(app, client):
    with app.app_context():
        player = _utente()
    _login(client, player)
    risposta = client.get("/challenges/catalog?gesto=boh&livello=99&ordine=x")
    assert risposta.status_code == 200


def test_la_scheda_mostra_etichette_e_chi_l_ha_provato(app, client):
    with app.app_context():
        cid = _esercizio(
            f"Scheda {uuid.uuid4().hex[:5]}",
            abilita=["tiro"],
            gesti=["stop"],
            declared_level=2,
            family="stop shot",
            family_step=1,
            cue_ball_reset=True,
        )
        player = _utente()
    _login(client, player)
    pagina = client.get(f"/challenges/{cid}").get_data(as_text=True)
    assert "Liv. 2" in pagina and "Tiro" in pagina and ">stop<" in pagina
    assert "stop shot · passo 1" in pagina
    assert "la bianca si rimette a ogni tiro" in pagina
    assert (
        "ancora nessuno l&#39;ha provato" in pagina
        or "ancora nessuno l'ha provato" in pagina
    )


def test_la_variante_scelta_arriva_sulla_prova(app, client):
    with app.app_context():
        cid = _esercizio(
            f"Lati {uuid.uuid4().hex[:5]}",
            variants=[{"label": "destra"}, {"label": "sinistra"}],
        )
        sinistra = db.session.get(Challenge, cid).variants[1].id
        player = _utente()
    _login(client, player)

    pagina = client.get(f"/challenges/{cid}/train").get_data(as_text=True)
    assert "Da che parte" in pagina and f'value="{sinistra}"' in pagina

    risposta = client.post(
        f"/challenges/{cid}/train",
        json={"score": 7, "variant_id": str(sinistra)},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    assert risposta.get_json()["attempt"]["variant"] == "sinistra"
    with app.app_context():
        prova = ChallengeAttempt.query.filter_by(challenge_id=cid).one()
        assert prova.variant_id == sinistra

    scheda = client.get(f"/challenges/{cid}").get_data(as_text=True)
    assert "mai provata" in scheda  # la destra
    assert "70%" in scheda  # la sinistra: 7 su 10


def test_la_variante_di_un_altro_esercizio_si_rifiuta(app, client):
    with app.app_context():
        altro = _esercizio(
            f"Altro {uuid.uuid4().hex[:5]}", variants=[{"label": "A"}, {"label": "B"}]
        )
        variante = db.session.get(Challenge, altro).variants[0].id
        cid = _esercizio(f"Questo {uuid.uuid4().hex[:5]}")
        player = _utente()
    _login(client, player)
    risposta = client.post(
        f"/challenges/{cid}/train",
        json={"score": 7, "variant_id": variante},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert risposta.status_code == 422
    with app.app_context():
        assert ChallengeAttempt.query.filter_by(challenge_id=cid).count() == 0
