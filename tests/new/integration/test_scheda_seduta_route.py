"""La seduta dalle pagine: cominciarla, segnare, chiuderla (ADR-067).

Il gesto da difendere è **un tocco per casella**: una richiesta, e la risposta
riporta i due pezzi già disegnati dal server. Qui si percorre per intero —
compresa la voce lunga, che si conta tiro per tiro — e si guarda che cosa resta
scritto a DB, perché è quello che il registro rileggerà fra sei mesi.
"""

from __future__ import annotations

import uuid

from flask import g

from models.base import db
from models.challenge.models import Challenge, ChallengeVariant
from models.training_sheet import (
    SheetItemSpec,
    SheetMeasure,
    TrainingSheet,
    TrainingSheetService,
)
from models.training_sheet.models import TrainingSession
from models.user.models import User
from models.user.role_enum import UserRole


def _utente() -> int:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"sd_{suffix}",
        email=f"sd_{suffix}@test.local",
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
    # In questa suite `g` **non è per-richiesta**: senza questa pulizia
    # Flask-Login trova in cache l'utente di prima e un secondo login non
    # cambia niente — il test passerebbe anche col controllo rimosso.
    if hasattr(g, "_login_user"):
        delattr(g, "_login_user")


def _esercizio(nome: str, *, varianti=()) -> int:
    challenge = Challenge(
        title=f"{nome} {uuid.uuid4().hex[:5]}",
        description="istruzioni",
        image_path="x.png",
        pass_fail_only=True,  # «riusciti» vuole un esito netto (ADR-072)
        is_active=True,
    )
    db.session.add(challenge)
    db.session.commit()
    for posizione, etichetta in enumerate(varianti, start=1):
        db.session.add(
            ChallengeVariant(
                challenge_id=challenge.id, label=etichetta, position=posizione
            )
        )
    db.session.commit()
    return challenge.id


def _scheda(user_id: int, voci, **opzioni) -> int:
    sheet = TrainingSheet(name="Tecnica di base", owner_id=user_id)
    db.session.add(sheet)
    db.session.commit()
    TrainingSheetService.save_composition(
        sheet.id,
        db.session.get(User, user_id),
        name="Tecnica di base",
        items=voci,
        **opzioni,
    )
    db.session.commit()
    return sheet.id


def _voci_ronin(user_id: int) -> int:
    """Due voci: una a cinque tiri con due lati, una lunga da trenta."""
    stop = _esercizio("Stop shot", varianti=("destra", "sinistra"))
    draw = _esercizio("Draw shot")
    return _scheda(
        user_id,
        [
            SheetItemSpec(
                challenge_id=stop, measure=SheetMeasure.MADE, amount=5, per_variant=True
            ),
            SheetItemSpec(challenge_id=draw, measure=SheetMeasure.MADE, amount=30),
        ],
        threshold=30,
    )


def _apri(client, sheet_id: int) -> int:
    risposta = client.post(f"/schede/{sheet_id}/seduta")
    assert risposta.status_code == 302
    return int(risposta.headers["Location"].rstrip("/").split("/")[-1])


def test_la_seduta_si_comincia_e_si_riprende(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
    _login(client, player)

    prima = _apri(client, sheet_id)
    dopo = _apri(client, sheet_id)
    assert prima == dopo, "ricominciare riprende quella aperta"

    pagina = client.get(f"/schede/seduta/{prima}").get_data(as_text=True)
    assert "Stop shot" in pagina
    # Cinque tiri per lato: i tasti vanno da 0 a 5, due volte.
    assert pagina.count('data-value="5"') == 2


def test_un_tocco_segna_la_casella_e_il_server_ridisegna(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
        sheet = db.session.get(TrainingSheet, sheet_id)
        voce = sheet.active_items[0]
        item_id, destra = voce.id, voce.variants[0].id
    _login(client, player)
    session_id = _apri(client, sheet_id)

    risposta = client.post(
        f"/schede/seduta/{session_id}/segna",
        json={"item_id": item_id, "variant_id": destra, "value": 4},
    )
    assert risposta.status_code == 200, risposta.get_data(as_text=True)
    corpo = risposta.get_json()
    assert corpo["success"] and corpo["total"] == 4
    # I due pezzi tornano già disegnati: il browser non ne tiene una copia.
    assert "data-cell" in corpo["dock_html"]
    assert "Stop shot" in corpo["progress_html"]

    with app.app_context():
        seduta = db.session.get(TrainingSession, session_id)
        (casella,) = seduta.entries
        # La casella si porta dietro misura e «su quanto» di stasera.
        assert (casella.value, casella.measure, casella.target_amount) == (4, "made", 5)


def test_le_due_varianti_sono_due_caselle(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
        sheet = db.session.get(TrainingSheet, sheet_id)
        voce = sheet.active_items[0]
        item_id = voce.id
        destra, sinistra = [v.id for v in voce.variants]
    _login(client, player)
    session_id = _apri(client, sheet_id)

    for variante, valore in ((destra, 5), (sinistra, 2)):
        client.post(
            f"/schede/seduta/{session_id}/segna",
            json={"item_id": item_id, "variant_id": variante, "value": valore},
        )

    with app.app_context():
        seduta = db.session.get(TrainingSession, session_id)
        assert seduta.total == 7
        assert len(seduta.entries) == 2


def test_la_voce_lunga_si_conta_tiro_per_tiro(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
        sheet = db.session.get(TrainingSheet, sheet_id)
        item_id = sheet.active_items[1].id
    _login(client, player)
    session_id = _apri(client, sheet_id)

    for esito in (True, False, True):
        risposta = client.post(
            f"/schede/seduta/{session_id}/tiro",
            json={"item_id": item_id, "made": esito},
        )
        assert risposta.status_code == 200

    with app.app_context():
        seduta = db.session.get(TrainingSession, session_id)
        (casella,) = seduta.entries
        assert (casella.marks, casella.value) == ("101", 2)

    client.post(f"/schede/seduta/{session_id}/annulla", json={"item_id": item_id})
    with app.app_context():
        seduta = db.session.get(TrainingSession, session_id)
        (casella,) = seduta.entries
        assert (casella.marks, casella.value) == ("10", 1)


def test_scrivere_il_totale_cancella_la_striscia(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
        sheet = db.session.get(TrainingSheet, sheet_id)
        item_id = sheet.active_items[1].id
    _login(client, player)
    session_id = _apri(client, sheet_id)

    client.post(
        f"/schede/seduta/{session_id}/tiro", json={"item_id": item_id, "made": True}
    )
    client.post(
        f"/schede/seduta/{session_id}/segna", json={"item_id": item_id, "value": 22}
    )

    with app.app_context():
        seduta = db.session.get(TrainingSession, session_id)
        (casella,) = seduta.entries
        assert (casella.value, casella.marks) == (22, None)


def test_svuotare_una_casella_non_e_segnare_zero(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
        sheet = db.session.get(TrainingSheet, sheet_id)
        item_id = sheet.active_items[1].id
    _login(client, player)
    session_id = _apri(client, sheet_id)

    client.post(
        f"/schede/seduta/{session_id}/segna", json={"item_id": item_id, "value": 0}
    )
    client.post(
        f"/schede/seduta/{session_id}/annulla",
        json={"item_id": item_id, "clear": True},
    )

    with app.app_context():
        assert db.session.get(TrainingSession, session_id).entries == []


def test_il_numero_impossibile_lo_rifiuta_il_server(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
        sheet = db.session.get(TrainingSheet, sheet_id)
        voce = sheet.active_items[0]
        item_id, destra = voce.id, voce.variants[0].id
    _login(client, player)
    session_id = _apri(client, sheet_id)

    risposta = client.post(
        f"/schede/seduta/{session_id}/segna",
        json={"item_id": item_id, "variant_id": destra, "value": 9},
    )
    assert risposta.status_code == 422
    assert risposta.get_json()["success"] is False


def test_chiudere_porta_al_riepilogo_che_confronta_col_prima(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
        sheet = db.session.get(TrainingSheet, sheet_id)
        lunga = sheet.active_items[1].id
    _login(client, player)

    prima = _apri(client, sheet_id)
    client.post(f"/schede/seduta/{prima}/segna", json={"item_id": lunga, "value": 18})
    client.post(f"/schede/seduta/{prima}/chiudi")

    seconda = _apri(client, sheet_id)
    client.post(f"/schede/seduta/{seconda}/segna", json={"item_id": lunga, "value": 24})
    risposta = client.post(f"/schede/seduta/{seconda}/chiudi")
    assert risposta.status_code == 302
    assert f"/schede/seduta/{seconda}/fine" in risposta.headers["Location"]

    pagina = client.get(f"/schede/seduta/{seconda}/fine").get_data(as_text=True)
    assert "24" in pagina
    assert "prima 18" in pagina, "il confronto è con la seduta precedente"


def test_una_seduta_senza_niente_segnato_si_butta(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
    _login(client, player)

    session_id = _apri(client, sheet_id)
    risposta = client.post(f"/schede/seduta/{session_id}/chiudi")
    assert risposta.status_code == 302
    assert "/schede/" in risposta.headers["Location"]

    with app.app_context():
        assert db.session.get(TrainingSession, session_id) is None


def test_una_seduta_chiusa_manda_al_riepilogo(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
        sheet = db.session.get(TrainingSheet, sheet_id)
        lunga = sheet.active_items[1].id
    _login(client, player)

    session_id = _apri(client, sheet_id)
    client.post(
        f"/schede/seduta/{session_id}/segna", json={"item_id": lunga, "value": 9}
    )
    client.post(f"/schede/seduta/{session_id}/chiudi")

    risposta = client.get(f"/schede/seduta/{session_id}")
    assert risposta.status_code == 302
    assert "/fine" in risposta.headers["Location"]


def test_la_seduta_di_un_altro_non_esiste(app, client):
    with app.app_context():
        player = _utente()
        estraneo = _utente()
        sheet_id = _voci_ronin(player)
    _login(client, player)
    session_id = _apri(client, sheet_id)
    _login(client, estraneo)

    assert client.get(f"/schede/seduta/{session_id}").status_code == 404
    assert (
        client.post(
            f"/schede/seduta/{session_id}/segna", json={"item_id": 1, "value": 1}
        ).status_code
        == 404
    )


def test_la_seduta_aperta_sale_in_cima_a_oggi(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _voci_ronin(player)
    _login(client, player)
    session_id = _apri(client, sheet_id)

    pagina = client.get("/challenges/").get_data(as_text=True)
    assert "Seduta cominciata" in pagina
    assert f"/schede/seduta/{session_id}" in pagina
