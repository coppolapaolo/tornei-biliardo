"""Le prove in scheda dalle pagine (ADR-072).

Tre giunti interfaccia↔server che i test di unità non percorrono:

* la composizione manda l'aggregazione insieme alla misura, e la pagina non
  propone più nessun «5»;
* la seduta registra una prova a punteggio alla volta e il server ridisegna la
  casella con l'aggregazione;
* la prova colpo per colpo chiusa dalla schermata del catalogo **col contesto
  della casella** torna nella seduta, agganciata.
"""

from __future__ import annotations

import uuid

from flask import g

from models.base import db
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.recording import RecordingMode
from models.training_sheet import (
    ScoreAggregation,
    SheetItemSpec,
    SheetMeasure,
    TrainingSheet,
    TrainingSheetService,
)
from models.training_sheet.models import TrainingEntry, TrainingSession
from models.user.models import User
from models.user.role_enum import UserRole


def _utente() -> int:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"pr_{suffix}",
        email=f"pr_{suffix}@test.local",
        role=UserRole.PLAYER.value,
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
    if hasattr(g, "_login_user"):
        delattr(g, "_login_user")


def _esercizio(nome: str, *, pass_fail=False, max_score=None, a_colpi=False) -> int:
    challenge = Challenge(
        title=f"{nome} {uuid.uuid4().hex[:5]}",
        description="istruzioni",
        image_path="x.png",
        pass_fail_only=pass_fail,
        max_score=max_score,
        is_active=True,
    )
    if a_colpi:
        challenge.recording_mode = RecordingMode.SHOTS.value
        challenge.shots_count = 2
        challenge.diagram_scene = (
            '{"v": 4, "items": [{"type": "target", "id": "t1", '
            '"x": 600, "y": 200, "step": 50}]}'
        )
    db.session.add(challenge)
    db.session.commit()
    return challenge.id


def _scheda(user_id: int, voci) -> int:
    sheet = TrainingSheet(name="Prove", owner_id=user_id)
    db.session.add(sheet)
    db.session.commit()
    TrainingSheetService.save_composition(
        sheet.id, db.session.get(User, user_id), name="Prove", items=voci
    )
    db.session.commit()
    return sheet.id


def _apri(client, sheet_id: int) -> int:
    risposta = client.post(f"/schede/{sheet_id}/seduta")
    assert risposta.status_code == 302
    return int(risposta.headers["Location"].rstrip("/").split("/")[-1])


def _voce(sheet_id: int):
    return db.session.get(TrainingSheet, sheet_id).active_items[0]


# ── comporre ────────────────────────────────────────────────────────────────
def test_la_pagina_non_propone_nessun_numero(app, client):
    user_id = _utente()
    a_punti = _esercizio("Spot shot", max_score=10)
    sheet_id = _scheda(
        user_id,
        [
            SheetItemSpec(
                challenge_id=a_punti,
                measure=SheetMeasure.SCORE,
                amount=3,
            )
        ],
    )
    _login(client, user_id)
    pagina = client.get(f"/schede/{sheet_id}/componi").get_data(as_text=True)
    assert 'name="amount" value=""' in pagina, "lo stampo delle voci nuove non ha un 5"
    assert 'name="amount" value="3"' in pagina
    assert 'data-sheet-agg="mean"' in pagina


def test_la_composizione_manda_l_aggregazione(app, client):
    user_id = _utente()
    a_punti = _esercizio("Spot shot", max_score=10)
    sheet = TrainingSheet(name="Prove", owner_id=user_id)
    db.session.add(sheet)
    db.session.commit()

    _login(client, user_id)
    risposta = client.post(
        f"/schede/{sheet.id}/componi",
        data={
            "name": "Prove",
            "challenge_id": [str(a_punti)],
            "item_id": [""],
            "measure": ["score"],
            "amount": ["3"],
            "aggregation": ["max"],
            "per_variant": ["0"],
            "section": [""],
            "day": [""],
        },
    )
    assert risposta.status_code == 302, risposta.get_data(as_text=True)[:300]
    voce = _voce(sheet.id)
    assert voce.aggregation_kind is ScoreAggregation.MAX
    assert voce.amount == 3


def test_senza_il_numero_il_server_rifiuta(app, client):
    user_id = _utente()
    netto = _esercizio("Stop shot", pass_fail=True)
    sheet = TrainingSheet(name="Prove", owner_id=user_id)
    db.session.add(sheet)
    db.session.commit()

    _login(client, user_id)
    risposta = client.post(
        f"/schede/{sheet.id}/componi",
        data={
            "name": "Prove",
            "challenge_id": [str(netto)],
            "item_id": [""],
            "measure": ["made"],
            "amount": [""],
            "aggregation": [""],
            "per_variant": ["0"],
            "section": [""],
            "day": [""],
        },
    )
    assert risposta.status_code != 302
    assert not db.session.get(TrainingSheet, sheet.id).active_items


# ── la seduta a punteggio ───────────────────────────────────────────────────
def test_una_prova_alla_volta_e_la_casella_e_la_media(app, client):
    user_id = _utente()
    a_punti = _esercizio("Spot shot", max_score=10)
    sheet_id = _scheda(
        user_id,
        [SheetItemSpec(challenge_id=a_punti, measure=SheetMeasure.SCORE, amount=2)],
    )
    _login(client, user_id)
    session_id = _apri(client, sheet_id)
    voce = _voce(sheet_id)

    pagina = client.get(f"/schede/seduta/{session_id}").get_data(as_text=True)
    assert "data-score-save" in pagina
    assert "Registra la prova 1 di 2" in pagina

    uno = client.post(
        f"/schede/seduta/{session_id}/prova",
        json={"item_id": voce.id, "score": 6, "at": 0},
    )
    assert uno.status_code == 200, uno.get_data(as_text=True)
    assert "Registra la prova 2 di 2" in uno.get_json()["dock_html"]

    due = client.post(
        f"/schede/seduta/{session_id}/prova",
        json={"item_id": voce.id, "score": 7, "at": 0},
    )
    dati = due.get_json()
    assert "Prove fatte" in dati["dock_html"]
    assert "6,5" in dati["progress_html"] or "6.5" in dati["progress_html"]

    entry = TrainingEntry.query.filter_by(item_id=voce.id).one()
    assert entry.value == 6.5
    assert (
        ChallengeAttempt.query.filter_by(user_id=user_id, challenge_id=a_punti).count()
        == 2
    )

    tolta = client.post(
        f"/schede/seduta/{session_id}/prova/annulla",
        json={"item_id": voce.id, "at": 0},
    )
    assert tolta.status_code == 200
    assert "Registra la prova 2 di 2" in tolta.get_json()["dock_html"]


# ── colpo per colpo, dalla schermata del catalogo ──────────────────────────
def test_la_prova_a_colpi_torna_nella_casella(app, client):
    user_id = _utente()
    a_colpi = _esercizio("A colpi", a_colpi=True)
    sheet_id = _scheda(
        user_id,
        [SheetItemSpec(challenge_id=a_colpi, measure=SheetMeasure.SCORE, amount=1)],
    )
    _login(client, user_id)
    session_id = _apri(client, sheet_id)
    voce = _voce(sheet_id)

    seduta = client.get(f"/schede/seduta/{session_id}").get_data(as_text=True)
    assert f"seduta={session_id}" in seduta and f"voce={voce.id}" in seduta

    pagina = client.get(
        f"/challenges/{a_colpi}/train?seduta={session_id}&voce={voce.id}"
    ).get_data(as_text=True)
    assert f'data-sheet-session="{session_id}"' in pagina
    assert f"/schede/seduta/{session_id}" in pagina, "la freccia torna alla seduta"

    for _colpo in range(2):
        colpo = client.post(f"/challenges/{a_colpi}/train/shot", json={"made": False})
        assert colpo.status_code == 200, colpo.get_data(as_text=True)

    chiusa = client.post(
        f"/challenges/{a_colpi}/train/shot/close",
        json={"sheet_session_id": session_id, "sheet_item_id": voce.id},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    dati = chiusa.get_json()
    assert dati["success"], dati
    assert dati["redirect_url"].startswith(f"/schede/seduta/{session_id}")

    entry = TrainingEntry.query.filter_by(item_id=voce.id).one()
    assert entry.value == 0 and entry.is_filled
    prova = ChallengeAttempt.query.filter_by(
        user_id=user_id, challenge_id=a_colpi
    ).one()
    assert prova.completed and prova.training_entry_id == entry.id
    assert db.session.get(TrainingSession, session_id).is_open


def test_un_contesto_di_un_altro_non_si_accetta(app, client):
    """La seduta di un altro nell'indirizzo: la pagina è quella di sempre."""
    mio = _utente()
    altro = _utente()
    a_colpi = _esercizio("A colpi", a_colpi=True)
    sheet_id = _scheda(
        altro,
        [SheetItemSpec(challenge_id=a_colpi, measure=SheetMeasure.SCORE, amount=1)],
    )
    _login(client, altro)
    session_id = _apri(client, sheet_id)
    voce = _voce(sheet_id)

    _login(client, mio)
    pagina = client.get(
        f"/challenges/{a_colpi}/train?seduta={session_id}&voce={voce.id}"
    ).get_data(as_text=True)
    assert "data-sheet-session" not in pagina
