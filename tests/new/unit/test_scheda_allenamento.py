"""La scheda di allenamento: una forma sola per schede molto diverse (ADR-067).

Il piano della fase 6 chiede una verifica esplicita, e questo file è quella:
**due schede che non si somigliano in niente si compongono con lo stesso
oggetto**. Se un giorno qualcuno aggiungesse un «tipo di scheda» per far stare
la seconda, uno di questi test lo direbbe.

* la prima è il foglio di carta di Rōnin ASD (lv.3, v0.6): sei esercizi tutti
  «riusciti su cinque tiri», quattro dei quali a destra e a sinistra: dieci
  colonne, un totale di 50 e la soglia «40/50» per passare al livello dopo;
* la seconda non ha totale né soglia: tiri, partite e minuti distribuiti su tre
  giorni A · B · C, per sei settimane.

Il resto del file difende le tre regole che rendono leggibile un registro fra
sei mesi: la casella si porta dietro la misura e il «su quanto» di quella sera,
una voce con delle registrazioni si ritira invece di sparire, e la versione
della scheda cresce quando cambia ciò che i numeri vogliono dire.
"""

from __future__ import annotations

import uuid

import pytest

from models.challenge.models import Challenge, ChallengeVariant
from models.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ValidationError,
)
from models.training_sheet import (
    SheetItemSpec,
    SheetMeasure,
    TrainingSessionService,
    TrainingSheetService,
)
from models.user.models import User
from models.user.role_enum import UserRole

# ── allestimento ────────────────────────────────────────────────────────────


def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"sch_{uid}", email=f"sch_{uid}@test.local", role=UserRole.PLAYER.value
    )
    user.set_password("p")
    db_session.add(user)
    db_session.flush()
    return user


def _challenge(db_session, titolo: str, *, varianti=(), max_score=None) -> Challenge:
    challenge = Challenge(
        title=titolo,
        description=f"{titolo}: istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=False,
        max_score=max_score,
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


def _scheda_ronin(db_session, owner):
    """Il foglio vero: sei esercizi, quattro con destra e sinistra, soglia 40/50."""
    secchi = [_challenge(db_session, n) for n in ("Linea tangente", "Ghost ball")]
    lati = [
        _challenge(db_session, n, varianti=("destra", "sinistra"))
        for n in ("Stop shot", "Follow shot", "Draw shot", "Angolo naturale")
    ]
    sheet = TrainingSheetService.create_sheet(owner, "Tecnica di base")
    voci = [
        SheetItemSpec(challenge_id=c.id, measure=SheetMeasure.MADE, amount=5)
        for c in secchi
    ] + [
        SheetItemSpec(
            challenge_id=c.id, measure=SheetMeasure.MADE, amount=5, per_variant=True
        )
        for c in lati
    ]
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="Tecnica di base",
        items=voci,
        level=3,
        threshold=40,
    )
    return sheet


# ── la verifica di generalità ───────────────────────────────────────────────


def test_il_foglio_di_carta_diventa_una_scheda(db_session):
    """Sei voci «riusciti su 5», quattro sdoppiate: dieci colonne, 50 tiri."""
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)

    assert len(sheet.active_items) == 6
    # Due colonne da 5 più quattro sdoppiate: le dieci caselle del foglio,
    # e la soglia per il livello dopo è «40/50 tiri».
    assert sheet.total == 50
    assert sheet.threshold == 40
    assert sheet.level == 3
    # Il foglio non ha giorni: una seduta fa tutta la scheda.
    assert sheet.days == []
    assert [item.slots for item in sheet.active_items] == [1, 1, 2, 2, 2, 2]


def test_la_scheda_a_giorni_non_ha_totale_e_mescola_le_unita(db_session):
    """Tiri, partite e minuti su tre giorni: stessa scheda, nessun totale."""
    owner = _user(db_session)
    tiri = _challenge(db_session, "Rastrello")
    partite = _challenge(db_session, "Contro il ghost")
    respiro = _challenge(db_session, "Giro di tavolo")

    sheet = TrainingSheetService.create_sheet(owner, "Tre giorni a settimana")
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="Tre giorni a settimana",
        uses_days=True,
        weeks=6,
        items=[
            SheetItemSpec(
                challenge_id=respiro.id,
                measure=SheetMeasure.MINUTES,
                amount=10,
                section="Riscaldamento",
                day="A",
            ),
            SheetItemSpec(
                challenge_id=tiri.id,
                measure=SheetMeasure.DONE,
                amount=10,
                day="A",
            ),
            SheetItemSpec(
                challenge_id=partite.id,
                measure=SheetMeasure.WINS,
                amount=5,
                section="Gioco",
                day="B",
            ),
            SheetItemSpec(challenge_id=tiri.id, measure=SheetMeasure.SCORE, day="C"),
        ],
    )

    assert sheet.days == ["A", "B", "C"]
    assert sheet.weeks == 6
    # Nessuna voce «a riusciti»: il totale è zero, e va bene così.
    assert sheet.total == 0
    assert sheet.has_threshold is False
    assert len(sheet.items_for_day("A")) == 2
    assert len(sheet.items_for_day("B")) == 1
    # Col punteggio il «quanto farne» non c'è: il massimo lo dice l'esercizio.
    punteggio = [i for i in sheet.active_items if i.measure == "score"][0]
    assert punteggio.amount is None


def test_lo_stesso_esercizio_puo_comparire_in_due_voci(db_session):
    """Il rastrello di riscaldamento e quello di fine seduta sono due righe."""
    owner = _user(db_session)
    rastrello = _challenge(db_session, "Rastrello")
    sheet = TrainingSheetService.create_sheet(owner, "Due volte")
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="Due volte",
        items=[
            SheetItemSpec(
                challenge_id=rastrello.id,
                measure=SheetMeasure.DONE,
                section="Riscaldamento",
            ),
            SheetItemSpec(
                challenge_id=rastrello.id,
                measure=SheetMeasure.MADE,
                amount=20,
                section="Chiusura",
            ),
        ],
    )
    assert len(sheet.active_items) == 2
    assert sheet.total == 20


# ── le regole del «quanto farne» ────────────────────────────────────────────


def test_riusciti_senza_quanti_si_rifiuta(db_session):
    owner = _user(db_session)
    challenge = _challenge(db_session, "Stop shot")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    with pytest.raises(ValidationError):
        TrainingSheetService.save_composition(
            sheet.id,
            owner,
            name="X",
            items=[SheetItemSpec(challenge_id=challenge.id, measure=SheetMeasure.MADE)],
        )


def test_la_soglia_non_supera_il_totale(db_session):
    owner = _user(db_session)
    challenge = _challenge(db_session, "Stop shot")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    with pytest.raises(ValidationError):
        TrainingSheetService.save_composition(
            sheet.id,
            owner,
            name="X",
            threshold=30,
            items=[
                SheetItemSpec(
                    challenge_id=challenge.id, measure=SheetMeasure.MADE, amount=10
                )
            ],
        )


def test_la_soglia_vuole_almeno_una_voce_a_riusciti(db_session):
    """Partite e minuti non fanno totale (D17): senza «riusciti» niente soglia."""
    owner = _user(db_session)
    challenge = _challenge(db_session, "Contro il ghost")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    with pytest.raises(ValidationError):
        TrainingSheetService.save_composition(
            sheet.id,
            owner,
            name="X",
            threshold=3,
            items=[
                SheetItemSpec(
                    challenge_id=challenge.id, measure=SheetMeasure.WINS, amount=5
                )
            ],
        )


def test_le_varianti_si_chiedono_solo_dove_ci_sono(db_session):
    """`per_variant` su un esercizio senza varianti resta spento, senza errori."""
    owner = _user(db_session)
    challenge = _challenge(db_session, "Ghost ball")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(
                challenge_id=challenge.id,
                measure=SheetMeasure.MADE,
                amount=5,
                per_variant=True,
            )
        ],
    )
    assert sheet.active_items[0].per_variant is False
    assert sheet.total == 5


# ── la versione, e le voci che si ritirano ──────────────────────────────────


def test_la_versione_sale_solo_quando_cambiano_i_numeri(db_session):
    owner = _user(db_session)
    challenge = _challenge(db_session, "Stop shot")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    voce = SheetItemSpec(challenge_id=challenge.id, measure=SheetMeasure.MADE, amount=5)
    TrainingSheetService.save_composition(sheet.id, owner, name="X", items=[voce])
    prima = sheet.version

    item_id = sheet.active_items[0].id
    tenuta = SheetItemSpec(
        challenge_id=challenge.id,
        measure=SheetMeasure.MADE,
        amount=5,
        item_id=item_id,
    )
    TrainingSheetService.save_composition(
        sheet.id, owner, name="Nome nuovo", items=[tenuta]
    )
    assert sheet.version == prima, "rinominare non è una versione nuova"

    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="Nome nuovo",
        items=[
            SheetItemSpec(
                challenge_id=challenge.id,
                measure=SheetMeasure.MADE,
                amount=10,
                item_id=item_id,
            )
        ],
    )
    assert sheet.version == prima + 1, "da cinque tiri a dieci cambia i numeri"


def test_una_voce_con_registrazioni_si_ritira_e_il_registro_resta(db_session):
    owner = _user(db_session)
    uno = _challenge(db_session, "Stop shot")
    due = _challenge(db_session, "Draw shot")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(challenge_id=uno.id, measure=SheetMeasure.MADE, amount=5),
            SheetItemSpec(challenge_id=due.id, measure=SheetMeasure.MADE, amount=5),
        ],
    )
    prima, seconda = sheet.active_items
    id_seconda = seconda.id

    session = TrainingSessionService.start(sheet.id, owner)
    TrainingSessionService.record(session.id, id_seconda, owner, value=4)
    TrainingSessionService.close(session.id, owner)

    # La seconda voce esce dalla composizione: ha una casella, quindi si ritira.
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(
                challenge_id=uno.id,
                measure=SheetMeasure.MADE,
                amount=5,
                item_id=prima.id,
            )
        ],
    )
    ritirata = [item for item in sheet.items if item.id == id_seconda][0]
    assert ritirata.is_active is False
    assert len(sheet.active_items) == 1
    assert session.total == 4, "la seduta di ieri vale quello che valeva"


def test_una_voce_mai_usata_si_cancella(db_session):
    owner = _user(db_session)
    uno = _challenge(db_session, "Stop shot")
    due = _challenge(db_session, "Draw shot")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(challenge_id=uno.id, measure=SheetMeasure.MADE, amount=5),
            SheetItemSpec(challenge_id=due.id, measure=SheetMeasure.MADE, amount=5),
        ],
    )
    tenuta = sheet.active_items[0]
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(
                challenge_id=uno.id,
                measure=SheetMeasure.MADE,
                amount=5,
                item_id=tenuta.id,
            )
        ],
    )
    assert len(sheet.items) == 1


def test_le_voci_si_scambiano_di_posto(db_session):
    """Il riordino non collide con l'unicità della posizione fra le attive."""
    owner = _user(db_session)
    uno = _challenge(db_session, "Uno")
    due = _challenge(db_session, "Due")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(challenge_id=uno.id, measure=SheetMeasure.MADE, amount=5),
            SheetItemSpec(challenge_id=due.id, measure=SheetMeasure.MADE, amount=5),
        ],
    )
    primo, secondo = sheet.active_items
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(
                challenge_id=due.id,
                measure=SheetMeasure.MADE,
                amount=5,
                item_id=secondo.id,
            ),
            SheetItemSpec(
                challenge_id=uno.id,
                measure=SheetMeasure.MADE,
                amount=5,
                item_id=primo.id,
            ),
        ],
    )
    assert [item.id for item in sheet.active_items] == [secondo.id, primo.id]


# ── la seduta ───────────────────────────────────────────────────────────────


def test_una_seduta_alla_volta_e_si_riprende(db_session):
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)
    prima = TrainingSessionService.start(sheet.id, owner)
    dopo = TrainingSessionService.start(sheet.id, owner)
    assert prima.id == dopo.id, "ricominciare riprende la seduta lasciata aperta"


def test_la_casella_si_porta_dietro_la_misura_e_il_su_quanto(db_session):
    """Il cuore dell'ADR: cambiare la voce non riscrive la casella di ieri."""
    owner = _user(db_session)
    challenge = _challenge(db_session, "Stop shot")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(
                challenge_id=challenge.id, measure=SheetMeasure.MADE, amount=5
            )
        ],
    )
    item = sheet.active_items[0]

    session = TrainingSessionService.start(sheet.id, owner)
    entry = TrainingSessionService.record(session.id, item.id, owner, value=4)
    TrainingSessionService.close(session.id, owner)
    assert (entry.value, entry.target_amount, entry.measure) == (4, 5, "made")

    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(
                challenge_id=challenge.id,
                measure=SheetMeasure.MADE,
                amount=10,
                item_id=item.id,
            )
        ],
    )
    assert entry.target_amount == 5, "il 4 di ieri era su cinque tiri"
    assert session.max_total == 5
    assert sheet.total == 10


def test_le_varianti_sono_due_caselle(db_session):
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)
    voce = [item for item in sheet.active_items if item.per_variant][0]
    destra, sinistra = voce.variants

    session = TrainingSessionService.start(sheet.id, owner)
    TrainingSessionService.record(
        session.id, voce.id, owner, variant_id=destra.id, value=5
    )
    TrainingSessionService.record(
        session.id, voce.id, owner, variant_id=sinistra.id, value=2
    )
    assert session.total == 7
    assert len(session.entries) == 2

    with pytest.raises(ValidationError):
        TrainingSessionService.record(session.id, voce.id, owner, value=3)


def test_il_numero_non_supera_il_quanto_farne(db_session):
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)
    voce = sheet.active_items[0]
    session = TrainingSessionService.start(sheet.id, owner)
    with pytest.raises(ValidationError):
        TrainingSessionService.record(session.id, voce.id, owner, value=6)


def test_riscrivere_la_casella_corregge(db_session):
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)
    voce = sheet.active_items[0]
    session = TrainingSessionService.start(sheet.id, owner)
    TrainingSessionService.record(session.id, voce.id, owner, value=2)
    TrainingSessionService.record(session.id, voce.id, owner, value=5)
    assert len(session.entries) == 1
    assert session.total == 5


def test_tiro_per_tiro_conta_e_si_annulla(db_session):
    """La voce lunga: trenta tiri non si contano a mente."""
    owner = _user(db_session)
    challenge = _challenge(db_session, "Draw shot")
    sheet = TrainingSheetService.create_sheet(owner, "X")
    TrainingSheetService.save_composition(
        sheet.id,
        owner,
        name="X",
        items=[
            SheetItemSpec(
                challenge_id=challenge.id, measure=SheetMeasure.MADE, amount=3
            )
        ],
    )
    voce = sheet.active_items[0]
    session = TrainingSessionService.start(sheet.id, owner)

    TrainingSessionService.mark(session.id, voce.id, owner, made=True)
    TrainingSessionService.mark(session.id, voce.id, owner, made=False)
    entry = TrainingSessionService.mark(session.id, voce.id, owner, made=True)
    assert (entry.value, entry.marks, entry.shots_done) == (2, "101", 3)

    with pytest.raises(ConflictError):
        TrainingSessionService.mark(session.id, voce.id, owner, made=True)

    TrainingSessionService.undo_mark(session.id, voce.id, owner)
    assert entry.value == 1 and entry.marks == "10"


def test_scrivere_il_totale_cancella_la_striscia(db_session):
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)
    voce = sheet.active_items[0]
    session = TrainingSessionService.start(sheet.id, owner)
    TrainingSessionService.mark(session.id, voce.id, owner, made=True)
    entry = TrainingSessionService.record(session.id, voce.id, owner, value=4)
    assert entry.marks is None and entry.value == 4


def test_svuotare_una_casella_non_e_segnare_zero(db_session):
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)
    voce = sheet.active_items[0]
    session = TrainingSessionService.start(sheet.id, owner)

    TrainingSessionService.record(session.id, voce.id, owner, value=0)
    assert len(session.entries) == 1 and session.entries[0].is_filled

    TrainingSessionService.clear(session.id, voce.id, owner)
    assert session.entries == []


def test_una_seduta_chiusa_non_si_scrive_piu(db_session):
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)
    voce = sheet.active_items[0]
    session = TrainingSessionService.start(sheet.id, owner)
    TrainingSessionService.close(session.id, owner, notes="Tavolo 4")
    assert session.notes == "Tavolo 4"
    with pytest.raises(ConflictError):
        TrainingSessionService.record(session.id, voce.id, owner, value=3)


def test_una_seduta_con_qualcosa_segnato_non_si_butta(db_session):
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)
    voce = sheet.active_items[0]
    session = TrainingSessionService.start(sheet.id, owner)
    TrainingSessionService.discard(session.id, owner)

    altra = TrainingSessionService.start(sheet.id, owner)
    TrainingSessionService.record(altra.id, voce.id, owner, value=1)
    with pytest.raises(ConflictError):
        TrainingSessionService.discard(altra.id, owner)


def test_le_sedute_di_fila_sopra_la_soglia(db_session):
    owner = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)
    voci = sheet.active_items

    def seduta(quanti_pieni: int):
        session = TrainingSessionService.start(sheet.id, owner)
        for indice, voce in enumerate(voci):
            valore = 5 if indice < quanti_pieni else 0
            if voce.per_variant:
                for variante in voce.variants:
                    TrainingSessionService.record(
                        session.id, voce.id, owner, variant_id=variante.id, value=valore
                    )
            else:
                TrainingSessionService.record(session.id, voce.id, owner, value=valore)
        TrainingSessionService.close(session.id, owner)
        return session

    sotto = seduta(2)
    assert sotto.total == 10
    assert TrainingSessionService.above_threshold_streak(sheet, owner.id) == 0

    piena = seduta(6)
    assert piena.total == 50
    assert TrainingSessionService.above_threshold_streak(sheet, owner.id) == 1


# ── di chi è la scheda ──────────────────────────────────────────────────────


def test_la_scheda_di_un_altro_non_si_tocca(db_session):
    owner = _user(db_session)
    altro = _user(db_session)
    sheet = _scheda_ronin(db_session, owner)

    with pytest.raises(PermissionDeniedError):
        TrainingSheetService.save_composition(sheet.id, altro, name="Mia", items=[])
    with pytest.raises(PermissionDeniedError):
        TrainingSessionService.start(sheet.id, altro)
    assert TrainingSheetService.can_read(sheet, altro) is False


def test_un_lettore_legge_e_non_scrive(db_session):
    """Il legame è allievo–scheda–istruttore, e vale subito (D11, D18).

    Il grant serve dall'ADR-069: una scheda si apre a un **istruttore**, e il
    controllo sta nel servizio. Quando questo test è nato il ruolo non esisteva
    ancora, e chiunque poteva essere aggiunto come lettore.
    """
    from models.user.role_enum import GrantableRole
    from models.user.role_grant_service import RoleGrantService

    owner = _user(db_session)
    istruttore = _user(db_session)
    admin = _user(db_session)
    admin.role = UserRole.ADMIN.value
    db_session.flush()
    RoleGrantService.grant(istruttore.id, GrantableRole.INSTRUCTOR, admin)
    sheet = _scheda_ronin(db_session, owner)

    TrainingSheetService.add_reader(sheet.id, istruttore.id, owner)
    assert TrainingSheetService.can_read(sheet, istruttore) is True
    assert TrainingSheetService.can_edit(sheet, istruttore) is False

    TrainingSheetService.remove_reader(sheet.id, istruttore.id, owner)
    assert TrainingSheetService.can_read(sheet, istruttore) is False
    assert len(sheet.readers) == 1, "la riga resta: dice da quando a quando"
