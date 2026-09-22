"""Comporre una scheda dalle pagine: elenco, modulo, salvataggio (ADR-067).

Il modulo manda **liste parallele lette per posizione**: è il punto in cui una
composizione si rompe in silenzio, quindi i test lo percorrono per intero —
due voci diverse insieme, una voce tolta, una riordinata, e un rifiuto che non
deve costare il lavoro fatto.
"""

from __future__ import annotations

import uuid

from flask import g
from werkzeug.datastructures import MultiDict

from models.base import db
from models.challenge.models import Challenge, ChallengeVariant
from models.training_sheet import TrainingSheet, TrainingSheetService
from models.user.models import User
from models.user.role_enum import UserRole


def _utente() -> int:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"s_{suffix}",
        email=f"s_{suffix}@test.local",
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
    # In questa suite `g` non è per-richiesta: senza questa pulizia Flask-Login
    # tiene l'utente di prima, e un test sui permessi passerebbe da solo.
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


def _scheda(user_id: int, nome="Tecnica di base") -> int:
    sheet = TrainingSheet(name=nome, owner_id=user_id)
    db.session.add(sheet)
    db.session.commit()
    return sheet.id


def test_la_scheda_nasce_e_porta_dritti_a_comporla(app, client):
    with app.app_context():
        player = _utente()
    _login(client, player)

    risposta = client.post("/schede/nuova", data={"name": "Prima della gara"})
    assert risposta.status_code == 302
    assert "/componi" in risposta.headers["Location"]

    with app.app_context():
        schede = TrainingSheet.query.filter_by(owner_id=player).all()
        assert [s.name for s in schede] == ["Prima della gara"]


def test_due_voci_diverse_si_salvano_insieme(app, client):
    """Una «a riusciti» con destra e sinistra, una a minuti: stessa scheda."""
    with app.app_context():
        player = _utente()
        stop = _esercizio("Stop shot", varianti=("destra", "sinistra"))
        giro = _esercizio("Giro di tavolo")
        sheet_id = _scheda(player)
    _login(client, player)

    risposta = client.post(
        f"/schede/{sheet_id}/componi",
        data=MultiDict(
            [
                ("name", "Tecnica di base"),
                ("has_threshold", "1"),
                ("threshold", "8"),
                ("threshold_streak", "2"),
                ("challenge_id", str(stop)),
                ("item_id", ""),
                ("measure", "made"),
                ("amount", "5"),
                ("per_variant", "1"),
                ("section", "Tecnica"),
                ("day", ""),
                ("challenge_id", str(giro)),
                ("item_id", ""),
                ("measure", "minutes"),
                ("amount", "10"),
                ("per_variant", "0"),
                ("section", "Riscaldamento"),
                ("day", ""),
            ]
        ),
        follow_redirects=False,
    )
    assert risposta.status_code == 302, risposta.get_data(as_text=True)

    with app.app_context():
        sheet = db.session.get(TrainingSheet, sheet_id)
        voci = sheet.active_items
        assert [v.measure for v in voci] == ["made", "minutes"]
        assert [v.position for v in voci] == [1, 2]
        assert voci[0].per_variant is True and voci[0].slots == 2
        assert voci[1].section == "Riscaldamento"
        # Solo la voce «a riusciti» fa totale, e conta due volte per i due lati.
        assert sheet.total == 10
        assert (sheet.threshold, sheet.threshold_streak) == (8, 2)


def test_una_voce_si_toglie_e_l_ordine_si_inverte(app, client):
    with app.app_context():
        player = _utente()
        uno = _esercizio("Uno")
        due = _esercizio("Due")
        tre = _esercizio("Tre")
        sheet_id = _scheda(player)
        sheet = db.session.get(TrainingSheet, sheet_id)
        from models.training_sheet import SheetItemSpec, SheetMeasure

        TrainingSheetService.save_composition(
            sheet_id,
            db.session.get(User, player),
            name="X",
            items=[
                SheetItemSpec(challenge_id=c, measure=SheetMeasure.MADE, amount=5)
                for c in (uno, due, tre)
            ],
        )
        db.session.commit()
        ids = [v.id for v in sheet.active_items]
        challenge_ids = [v.challenge_id for v in sheet.active_items]
    _login(client, player)

    # Resta il terzo, poi il primo: il secondo esce.
    dati = [("name", "X")]
    for posizione in (2, 0):
        dati += [
            ("challenge_id", str(challenge_ids[posizione])),
            ("item_id", str(ids[posizione])),
            ("measure", "made"),
            ("amount", "5"),
            ("per_variant", "0"),
            ("section", ""),
            ("day", ""),
        ]
    risposta = client.post(f"/schede/{sheet_id}/componi", data=MultiDict(dati))
    assert risposta.status_code == 302

    with app.app_context():
        sheet = db.session.get(TrainingSheet, sheet_id)
        assert [v.id for v in sheet.active_items] == [ids[2], ids[0]]
        assert sheet.total == 10


def test_un_rifiuto_non_costa_il_lavoro_fatto(app, client):
    """Soglia più alta del totale: la pagina torna con le voci mandate."""
    with app.app_context():
        player = _utente()
        stop = _esercizio("Stop shot")
        sheet_id = _scheda(player)
    _login(client, player)

    risposta = client.post(
        f"/schede/{sheet_id}/componi",
        data=MultiDict(
            [
                ("name", "Impossibile"),
                ("has_threshold", "1"),
                ("threshold", "99"),
                ("challenge_id", str(stop)),
                ("item_id", ""),
                ("measure", "made"),
                ("amount", "5"),
                ("per_variant", "0"),
                ("section", ""),
                ("day", ""),
            ]
        ),
    )
    assert risposta.status_code == 422
    pagina = risposta.get_data(as_text=True)
    assert "Impossibile" in pagina, "il nome scritto resta nel modulo"
    assert f'value="{stop}"' in pagina, "la voce mandata resta nella lista"

    with app.app_context():
        sheet = db.session.get(TrainingSheet, sheet_id)
        assert sheet.active_items == [], "niente è stato salvato a metà"


def test_la_scheda_di_un_altro_non_esiste(app, client):
    with app.app_context():
        proprietario = _utente()
        estraneo = _utente()
        sheet_id = _scheda(proprietario)
    _login(client, estraneo)

    assert client.get(f"/schede/{sheet_id}/componi").status_code == 404
    assert (
        client.post(f"/schede/{sheet_id}/componi", data={"name": "Mia"}).status_code
        == 404
    )


def test_l_elenco_mostra_solo_le_proprie(app, client):
    with app.app_context():
        player = _utente()
        altro = _utente()
        _scheda(player, "La mia")
        _scheda(altro, "Quella di un altro")
    _login(client, player)

    pagina = client.get("/schede/").get_data(as_text=True)
    assert "La mia" in pagina
    assert "Quella di un altro" not in pagina


def test_archiviare_la_toglie_dall_elenco(app, client):
    with app.app_context():
        player = _utente()
        sheet_id = _scheda(player, "Da archiviare")
    _login(client, player)

    assert client.post(f"/schede/{sheet_id}/archivia").status_code == 302
    pagina = client.get("/schede/").get_data(as_text=True)
    assert "Da archiviare" not in pagina

    with app.app_context():
        assert db.session.get(TrainingSheet, sheet_id) is not None


def test_il_registro_si_apre_dalla_card(app, client):
    """La pagina della scheda: le sedute fatte, e i comandi di chi la possiede."""
    with app.app_context():
        player = _utente()
        stop = _esercizio("Stop shot")
        sheet_id = _scheda(player)
        from models.training_sheet import SheetItemSpec, SheetMeasure

        TrainingSheetService.save_composition(
            sheet_id,
            db.session.get(User, player),
            name="Tecnica di base",
            items=[
                SheetItemSpec(challenge_id=stop, measure=SheetMeasure.MADE, amount=5)
            ],
        )
        db.session.commit()
    _login(client, player)

    elenco = client.get("/schede/").get_data(as_text=True)
    assert f"/schede/{sheet_id}" in elenco

    pagina = client.get(f"/schede/{sheet_id}").get_data(as_text=True)
    assert "Nessuna seduta" in pagina, "senza sedute il registro lo dice"
    assert "Nuova seduta" in pagina


def test_il_registro_di_un_altro_non_esiste(app, client):
    with app.app_context():
        proprietario = _utente()
        estraneo = _utente()
        sheet_id = _scheda(proprietario)
    _login(client, estraneo)
    assert client.get(f"/schede/{sheet_id}").status_code == 404
