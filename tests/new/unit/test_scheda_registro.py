"""Il registro di una scheda: cosa dice, e quando tace (ADR-067).

Le frasi che accompagnano una voce sono osservazioni, non diagnosi. Questo file
difende soprattutto i **silenzi**, che sono la parte che si perde per prima:
sotto tre sedute non si dice se una voce sale, e una differenza fra i due lati
si nomina solo quando è più grande del rumore.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from models.base import utc_now
from models.challenge.models import Challenge, ChallengeVariant
from models.training_sheet import SheetItemSpec, SheetMeasure, TrainingSheetService
from models.training_sheet.models import TrainingEntry, TrainingSession
from models.training_sheet.register_view import build_register
from models.user.models import User
from models.user.role_enum import UserRole


def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"reg_{uid}", email=f"reg_{uid}@test.local", role=UserRole.PLAYER.value
    )
    user.set_password("p")
    db_session.add(user)
    db_session.flush()
    return user


def _challenge(db_session, titolo: str, *, varianti=()) -> Challenge:
    challenge = Challenge(
        title=titolo,
        description="istruzioni",
        image_path="x.png",
        pass_fail_only=False,
    )
    db_session.add(challenge)
    db_session.flush()
    for posizione, etichetta in enumerate(varianti, start=1):
        db_session.add(
            ChallengeVariant(
                challenge_id=challenge.id, label=etichetta, position=posizione
            )
        )
    db_session.flush()
    return challenge


def _scheda(db_session, owner, voci, **opzioni):
    sheet = TrainingSheetService.create_sheet(owner, "Tecnica di base")
    TrainingSheetService.save_composition(
        sheet.id, owner, name="Tecnica di base", items=voci, **opzioni
    )
    return sheet


def _seduta(db_session, sheet, owner, valori, *, giorni_fa: int = 0):
    """Una seduta chiusa: `valori` è {(item_id, variant_id): numero}."""
    quando = utc_now() - timedelta(days=giorni_fa)
    session = TrainingSession(
        sheet_id=sheet.id,
        user_id=owner.id,
        sheet_version=sheet.version,
        started_at=quando,
        ended_at=quando + timedelta(minutes=40),
    )
    db_session.add(session)
    db_session.flush()
    for (item_id, variant_id), valore in valori.items():
        voce = next(v for v in sheet.items if v.id == item_id)
        db_session.add(
            TrainingEntry(
                session_id=session.id,
                item_id=item_id,
                variant_id=variant_id,
                value=valore,
                measure=voce.measure,
                target_amount=voce.amount,
            )
        )
    db_session.flush()
    return session


def test_i_tre_numeri_in_cima(db_session):
    owner = _user(db_session)
    esercizio = _challenge(db_session, "Stop shot")
    sheet = _scheda(
        db_session,
        owner,
        [
            SheetItemSpec(
                challenge_id=esercizio.id, measure=SheetMeasure.MADE, amount=10
            )
        ],
        threshold=8,
    )
    voce = sheet.active_items[0]

    for giorni, valore in ((4, 6), (2, 9), (0, 8)):
        _seduta(db_session, sheet, owner, {(voce.id, None): valore}, giorni_fa=giorni)

    registro = build_register(sheet, owner.id)
    assert registro.last_total == 8, "l'ultima è la più recente"
    # (8 + 9 + 6) / 3
    assert registro.average_label == "7,7"
    assert registro.above_count == 2, "due sedute sopra la soglia di 8"


def test_una_voce_in_crescita_lo_dice_dalla_terza_seduta(db_session):
    owner = _user(db_session)
    esercizio = _challenge(db_session, "Draw shot")
    sheet = _scheda(
        db_session,
        owner,
        [
            SheetItemSpec(
                challenge_id=esercizio.id, measure=SheetMeasure.MADE, amount=30
            )
        ],
    )
    voce = sheet.active_items[0]

    _seduta(db_session, sheet, owner, {(voce.id, None): 19}, giorni_fa=4)
    _seduta(db_session, sheet, owner, {(voce.id, None): 22}, giorni_fa=2)
    assert (
        build_register(sheet, owner.id).items[0].note == ""
    ), "due punti non sono una tendenza"

    _seduta(db_session, sheet, owner, {(voce.id, None): 24}, giorni_fa=0)
    riga = build_register(sheet, owner.id).items[0]
    assert riga.note == "in crescita"
    assert riga.tone == "ok"
    assert riga.recent_label == "19 · 22 · 24", "dalla più vecchia alla più recente"


def test_il_lato_debole_viene_prima_della_tendenza(db_session):
    """È la ragione per cui il foglio di carta ha due colonne."""
    owner = _user(db_session)
    esercizio = _challenge(db_session, "Follow shot", varianti=("destra", "sinistra"))
    sheet = _scheda(
        db_session,
        owner,
        [
            SheetItemSpec(
                challenge_id=esercizio.id,
                measure=SheetMeasure.MADE,
                amount=5,
                per_variant=True,
            )
        ],
    )
    voce = sheet.active_items[0]
    destra, sinistra = [v.id for v in voce.variants]

    for giorni, (a_destra, a_sinistra) in ((4, (4, 2)), (2, (5, 3)), (0, (4, 3))):
        _seduta(
            db_session,
            sheet,
            owner,
            {(voce.id, destra): a_destra, (voce.id, sinistra): a_sinistra},
            giorni_fa=giorni,
        )

    riga = build_register(sheet, owner.id).items[0]
    # Media destra 4,3 · sinistra 2,7: più di un tiro di scarto, si dice.
    assert "sinistra" in riga.note and "destra" in riga.note
    assert riga.tone == "err"
    # I due lati si sommano nella colonna della voce.
    assert riga.recent_label == "6 · 8 · 7"


def test_due_lati_vicini_non_si_commentano(db_session):
    """Un tiro di differenza lo fa il caso: dirlo sarebbe una correzione a caso."""
    owner = _user(db_session)
    esercizio = _challenge(db_session, "Stop shot", varianti=("destra", "sinistra"))
    sheet = _scheda(
        db_session,
        owner,
        [
            SheetItemSpec(
                challenge_id=esercizio.id,
                measure=SheetMeasure.MADE,
                amount=5,
                per_variant=True,
            )
        ],
    )
    voce = sheet.active_items[0]
    destra, sinistra = [v.id for v in voce.variants]
    _seduta(
        db_session,
        sheet,
        owner,
        {(voce.id, destra): 4, (voce.id, sinistra): 4},
        giorni_fa=1,
    )
    assert build_register(sheet, owner.id).items[0].note == ""


def test_una_voce_non_segnata_in_una_seduta_non_e_uno_zero(db_session):
    owner = _user(db_session)
    uno = _challenge(db_session, "Uno")
    due = _challenge(db_session, "Due")
    sheet = _scheda(
        db_session,
        owner,
        [
            SheetItemSpec(challenge_id=uno.id, measure=SheetMeasure.MADE, amount=5),
            SheetItemSpec(challenge_id=due.id, measure=SheetMeasure.MADE, amount=5),
        ],
    )
    prima, seconda = sheet.active_items
    _seduta(db_session, sheet, owner, {(prima.id, None): 3}, giorni_fa=0)

    registro = build_register(sheet, owner.id)
    saltata = [
        r for r in registro.items if r.label == seconda.challenge.get_display_name()
    ][0]
    assert saltata.values == [None]
    assert saltata.recent_label == "–"


def test_una_voce_ritirata_esce_dal_registro_ma_non_dalle_sedute(db_session):
    owner = _user(db_session)
    uno = _challenge(db_session, "Uno")
    due = _challenge(db_session, "Due")
    sheet = _scheda(
        db_session,
        owner,
        [
            SheetItemSpec(challenge_id=uno.id, measure=SheetMeasure.MADE, amount=5),
            SheetItemSpec(challenge_id=due.id, measure=SheetMeasure.MADE, amount=5),
        ],
    )
    prima, seconda = sheet.active_items
    _seduta(
        db_session,
        sheet,
        owner,
        {(prima.id, None): 3, (seconda.id, None): 4},
        giorni_fa=0,
    )

    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="Tecnica di base",
        items=[
            SheetItemSpec(
                challenge_id=uno.id,
                measure=SheetMeasure.MADE,
                amount=5,
                item_id=prima.id,
            )
        ],
    )

    registro = build_register(sheet, owner.id)
    assert len(registro.items) == 1, "il registro racconta la scheda di oggi"
    assert registro.sessions[0].total == 7, "la seduta di allora vale quello che valeva"


def test_senza_sedute_il_registro_e_vuoto(db_session):
    owner = _user(db_session)
    esercizio = _challenge(db_session, "Stop shot")
    sheet = _scheda(
        db_session,
        owner,
        [SheetItemSpec(challenge_id=esercizio.id, measure=SheetMeasure.MADE, amount=5)],
    )
    registro = build_register(sheet, owner.id)
    assert registro.is_empty
    assert registro.average is None and registro.last_total is None
