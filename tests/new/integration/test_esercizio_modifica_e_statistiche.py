"""Due pagine degli esercizi che esistevano solo come route (2026-09-19).

* ``challenge.edit_challenge`` rendeva il modulo di **creazione** passandogli
  ``edit_mode=True``, che il template non leggeva: campi vuoti, foto
  obbligatoria, titolo «Nuovo esercizio», pulsante «Crea». Nessun link la
  raggiungeva, quindi nessuno se n'è accorto.
* ``challenge.challenge_statistics`` rendeva ``challenge/statistics.html``,
  che non è mai esistito. Il ``TemplateNotFound`` finiva nell'``except
  Exception`` della route e diventava «Non è stato possibile caricare le
  statistiche» più un redirect: un guasto permanente travestito da errore
  passeggero.
"""

from __future__ import annotations

import uuid

from models.base import db
from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.user.models import User
from models.user.role_enum import UserRole


def _make_director() -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"dir_{suffix}",
        email=f"dir_{suffix}@test.local",
        role=UserRole.DIRECTOR.value,
        is_verified=True,
    )
    user.set_password("test1234")
    db.session.add(user)
    db.session.flush()
    return user


def _login(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = db.session.get(User, user_id).get_id()
        session["_fresh"] = True


def _setup(app) -> tuple[int, int]:
    with app.app_context():
        director = _make_director()
        challenge = ChallengeService.create_challenge(
            title="Progressione lungo sponda",
            description="Imbuca in sequenza partendo dalla corta",
            image_path="x.png",
            created_by_id=director.id,
        )
        db.session.commit()
        return director.id, challenge.id


def test_il_modulo_di_modifica_arriva_compilato(app, client):
    director_id, challenge_id = _setup(app)
    _login(client, director_id)

    response = client.get(f"/challenges/{challenge_id}/edit")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'value="Progressione lungo sponda"' in html
    assert "Imbuca in sequenza partendo dalla corta</textarea>" in html
    assert "Modifica esercizio" in html
    assert "Salva le modifiche" in html
    # La foto c'è già: pretenderne un'altra impedirebbe di correggere un refuso.
    assert 'name="image" accept="image/*" required' not in html
    # Il tipo di punteggio non si cambia da qui: la route non lo legge, e con
    # delle prove già registrate è una decisione a parte (#252).
    # (Lo script nomina `scoring_type` in un selettore: si guarda il markup.)
    assert 'id="maxScoreRow"' not in html


def test_salvare_il_modulo_di_modifica_cambia_l_esercizio(app, client):
    director_id, challenge_id = _setup(app)
    _login(client, director_id)

    response = client.post(
        f"/challenges/{challenge_id}/edit",
        data={"title": "Lungo sponda", "description": "Dalla corta, in ordine"},
    )

    assert response.status_code == 302
    with app.app_context():
        challenge = db.session.get(Challenge, challenge_id)
        assert challenge.title == "Lungo sponda"
        assert challenge.description == "Dalla corta, in ordine"
        assert challenge.is_active is True


def test_chi_ha_creato_l_esercizio_trova_i_due_comandi_nel_dettaglio(app, client):
    director_id, challenge_id = _setup(app)
    _login(client, director_id)

    html = client.get(f"/challenges/{challenge_id}").get_data(as_text=True)

    assert f"/challenges/{challenge_id}/edit" in html
    assert f"/challenges/{challenge_id}/statistics" in html


def test_la_pagina_delle_statistiche_esiste(app, client):
    director_id, challenge_id = _setup(app)
    _login(client, director_id)

    response = client.get(f"/challenges/{challenge_id}/statistics")

    assert response.status_code == 200
    assert "Progressione lungo sponda" in response.get_data(as_text=True)
