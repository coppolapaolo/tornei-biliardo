"""Le prove fatte in scheda sono prove del catalogo (ADR-072).

Tre cose decise il 22/09/2026, ognuna col suo gruppo di test:

* la **misura discende dall'esercizio**: riusciti su uno a esito netto,
  punteggio su uno a punteggio, e il contrario si rifiuta; il numero di prove
  non ha un default;
* un esercizio a punteggio si fa **N volte** e la casella è la somma, la media,
  la mediana o il massimo — copiata sulla casella, come misura e «su quanto»;
* ogni prova in scheda è un ``ChallengeAttempt``: chi ha provato, chi può
  votare, lo storico e l'andamento la vedono senza che nessun lettore cambi. E
  l'XP non lo paga la prova, lo paga la seduta.
"""

from __future__ import annotations

import uuid

import pytest

from models.andamento import Periodo, build_andamento
from models.challenge.events import ChallengeAttemptCompletedEvent, DrillOrigin
from models.challenge.models import Challenge, ChallengeAttempt, ChallengeVariant
from models.challenge.popularity import has_tried, popularity_for
from models.challenge.profile_service import ChallengeProfileService
from models.challenge.recording import RecordingMode
from models.challenge.shot_service import ShotRunService
from models.challenge.training_service import TrainingHistoryService
from models.challenge.vocabulary import Abilita
from models.events.base import EventBus
from models.exceptions import ConflictError, ValidationError
from models.training_sheet import (
    SheetItemSpec,
    SheetMeasure,
    TrainingSessionService,
    TrainingSheet,
    TrainingSheetService,
)
from models.training_sheet.measure import ScoreAggregation
from models.user.models import User
from models.user.role_enum import UserRole

# ── allestimento ────────────────────────────────────────────────────────────


def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"pis_{uid}", email=f"pis_{uid}@test.local", role=UserRole.PLAYER.value
    )
    user.set_password("p")
    db_session.add(user)
    db_session.flush()
    return user


def _challenge(
    db_session,
    titolo: str,
    *,
    pass_fail=False,
    max_score=None,
    varianti=(),
    recording_mode=None,
) -> Challenge:
    challenge = Challenge(
        title=titolo,
        description=f"{titolo}: istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=pass_fail,
        max_score=max_score,
    )
    if recording_mode is not None:
        challenge.recording_mode = recording_mode.value
        challenge.shots_count = 2
        challenge.diagram_scene = _SCENA_CON_BERSAGLIO
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


#: Un bersaglio in scena: serve alla prova colpo per colpo, che senza non
#: accetta un colpo imbucato.
_SCENA_CON_BERSAGLIO = (
    '{"v": 4, "items": [{"type": "target", "id": "t1", '
    '"x": 600, "y": 200, "step": 50}]}'
)


def _scheda(db_session, user, voci, **opzioni) -> TrainingSheet:
    sheet = TrainingSheet(name="Scheda", owner_id=user.id)
    db_session.add(sheet)
    db_session.flush()
    TrainingSheetService.save_composition(
        sheet.id, user, name="Scheda", items=voci, **opzioni
    )
    db_session.flush()
    return sheet


def _voce(sheet, posizione=1):
    return sheet.active_items[posizione - 1]


def _seduta(db_session, sheet, user):
    session = TrainingSessionService.start(sheet.id, user)
    db_session.flush()
    return session


def _prove_di(entry):
    return sorted(entry.attempts, key=lambda a: (a.attempted_at, a.id))


# ── 1 · la misura discende dall'esercizio ──────────────────────────────────
def test_la_misura_la_dice_l_esercizio(db_session):
    netto = _challenge(db_session, "Netto", pass_fail=True)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    assert SheetMeasure.for_challenge(netto) is SheetMeasure.MADE
    assert SheetMeasure.for_challenge(a_punti) is SheetMeasure.SCORE


def test_le_misure_ammesse_escludono_quella_dell_altro_tipo(db_session):
    netto = _challenge(db_session, "Netto", pass_fail=True)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    assert SheetMeasure.SCORE not in SheetMeasure.allowed_for(netto)
    assert SheetMeasure.MADE in SheetMeasure.allowed_for(netto)
    assert SheetMeasure.MADE not in SheetMeasure.allowed_for(a_punti)
    assert SheetMeasure.SCORE in SheetMeasure.allowed_for(a_punti)
    # Fatto, vinte e minuti restano per le voci che non sono prove.
    for misura in (SheetMeasure.DONE, SheetMeasure.WINS, SheetMeasure.MINUTES):
        assert misura in SheetMeasure.allowed_for(netto)
        assert misura in SheetMeasure.allowed_for(a_punti)


def test_riusciti_su_un_esercizio_a_punteggio_si_rifiuta(db_session):
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    with pytest.raises(ValidationError):
        _scheda(
            db_session,
            user,
            [
                SheetItemSpec(
                    challenge_id=a_punti.id, measure=SheetMeasure.MADE, amount=5
                )
            ],
        )


def test_punteggio_su_un_esercizio_a_esito_netto_si_rifiuta(db_session):
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    with pytest.raises(ValidationError):
        _scheda(
            db_session,
            user,
            [
                SheetItemSpec(
                    challenge_id=netto.id, measure=SheetMeasure.SCORE, amount=3
                )
            ],
        )


def test_il_punteggio_vuole_quante_prove(db_session):
    """Il «quanto farne» col punteggio è il numero di prove, e non ha default."""
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    with pytest.raises(ValidationError):
        _scheda(
            db_session,
            user,
            [SheetItemSpec(challenge_id=a_punti.id, measure=SheetMeasure.SCORE)],
        )
    assert SheetMeasure.SCORE.wants_amount


def test_l_aggregazione_si_salva_sulla_voce_e_vale_media_se_non_detta(db_session):
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda(
        db_session,
        user,
        [
            SheetItemSpec(
                challenge_id=a_punti.id, measure=SheetMeasure.SCORE, amount=3
            ),
            SheetItemSpec(
                challenge_id=a_punti.id,
                measure=SheetMeasure.SCORE,
                amount=2,
                aggregation=ScoreAggregation.MAX,
            ),
        ],
    )
    assert _voce(sheet, 1).aggregation_kind is ScoreAggregation.MEAN
    assert _voce(sheet, 2).aggregation_kind is ScoreAggregation.MAX


def test_cambiare_l_aggregazione_alza_la_versione(db_session):
    """Cambia ciò che i numeri vogliono dire (ADR-067 §4)."""
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda(
        db_session,
        user,
        [SheetItemSpec(challenge_id=a_punti.id, measure=SheetMeasure.SCORE, amount=3)],
    )
    prima = sheet.version
    voce = _voce(sheet)
    TrainingSheetService.save_composition(
        sheet.id,
        user,
        name="Scheda",
        items=[
            SheetItemSpec(
                challenge_id=a_punti.id,
                measure=SheetMeasure.SCORE,
                amount=3,
                aggregation=ScoreAggregation.SUM,
                item_id=voce.id,
            )
        ],
    )
    assert sheet.version == prima + 1


@pytest.mark.parametrize(
    "kind, atteso",
    [
        (ScoreAggregation.SUM, 21),
        (ScoreAggregation.MEAN, 7),
        (ScoreAggregation.MEDIAN, 8),
        (ScoreAggregation.MAX, 9),
    ],
)
def test_le_quattro_aggregazioni(kind, atteso):
    assert kind.apply([4, 8, 9]) == atteso


def test_la_mediana_di_un_numero_pari_di_prove_sta_in_mezzo():
    assert ScoreAggregation.MEDIAN.apply([4, 8]) == 6
    assert ScoreAggregation.MEAN.apply([4, 5]) == 4.5


# ── 2 · riusciti su N: N prove a esito netto ───────────────────────────────
def test_quattro_su_cinque_sono_cinque_prove(db_session):
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    sheet = _scheda(
        db_session,
        user,
        [SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.MADE, amount=5)],
    )
    session = _seduta(db_session, sheet, user)
    entry = TrainingSessionService.record(session.id, _voce(sheet).id, user, value=4)

    prove = _prove_di(entry)
    assert len(prove) == 5
    assert sum(1 for p in prove if p.passed) == 4
    assert all(p.completed and p.training_entry_id == entry.id for p in prove)
    assert all(p.challenge_id == netto.id and p.user_id == user.id for p in prove)
    assert entry.value == 4


def test_riscrivere_la_casella_rifa_le_prove(db_session):
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    sheet = _scheda(
        db_session,
        user,
        [SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.MADE, amount=5)],
    )
    session = _seduta(db_session, sheet, user)
    voce = _voce(sheet)
    TrainingSessionService.record(session.id, voce.id, user, value=4)
    entry = TrainingSessionService.record(session.id, voce.id, user, value=2)

    prove = _prove_di(entry)
    assert len(prove) == 5
    assert sum(1 for p in prove if p.passed) == 2
    assert (
        ChallengeAttempt.query.filter_by(user_id=user.id, challenge_id=netto.id).count()
        == 5
    )


def test_tiro_per_tiro_una_prova_alla_volta_e_si_annulla(db_session):
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    sheet = _scheda(
        db_session,
        user,
        [SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.MADE, amount=3)],
    )
    session = _seduta(db_session, sheet, user)
    voce = _voce(sheet)
    TrainingSessionService.mark(session.id, voce.id, user, made=True)
    entry = TrainingSessionService.mark(session.id, voce.id, user, made=False)
    assert [p.passed for p in _prove_di(entry)] == [True, False]
    assert entry.value == 1

    TrainingSessionService.undo_mark(session.id, voce.id, user)
    assert [p.passed for p in _prove_di(entry)] == [True]
    assert entry.value == 1


def test_svuotare_la_casella_porta_via_le_prove(db_session):
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    sheet = _scheda(
        db_session,
        user,
        [SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.MADE, amount=5)],
    )
    session = _seduta(db_session, sheet, user)
    voce = _voce(sheet)
    TrainingSessionService.record(session.id, voce.id, user, value=4)
    TrainingSessionService.clear(session.id, voce.id, user)
    db_session.flush()
    assert (
        ChallengeAttempt.query.filter_by(user_id=user.id, challenge_id=netto.id).count()
        == 0
    )


def test_la_prova_porta_la_variante_della_casella(db_session):
    user = _user(db_session)
    netto = _challenge(
        db_session, "Netto", pass_fail=True, varianti=("destra", "sinistra")
    )
    sheet = _scheda(
        db_session,
        user,
        [
            SheetItemSpec(
                challenge_id=netto.id,
                measure=SheetMeasure.MADE,
                amount=2,
                per_variant=True,
            )
        ],
    )
    session = _seduta(db_session, sheet, user)
    voce = _voce(sheet)
    sinistra = voce.variants[1]
    entry = TrainingSessionService.record(
        session.id, voce.id, user, variant_id=sinistra.id, value=2
    )
    assert {p.variant_id for p in entry.attempts} == {sinistra.id}


def test_fatto_vinte_e_minuti_non_fanno_prove(db_session):
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    sheet = _scheda(
        db_session,
        user,
        [
            SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.DONE),
            SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.WINS, amount=3),
            SheetItemSpec(
                challenge_id=netto.id, measure=SheetMeasure.MINUTES, amount=10
            ),
        ],
    )
    session = _seduta(db_session, sheet, user)
    TrainingSessionService.record(session.id, _voce(sheet, 1).id, user, done=True)
    TrainingSessionService.record(session.id, _voce(sheet, 2).id, user, value=2)
    TrainingSessionService.record(session.id, _voce(sheet, 3).id, user, value=12)
    assert ChallengeAttempt.query.filter_by(user_id=user.id).count() == 0


# ── 3 · N prove a punteggio ────────────────────────────────────────────────
def _scheda_a_punteggio(db_session, user, challenge, quante=3, kind=None):
    return _scheda(
        db_session,
        user,
        [
            SheetItemSpec(
                challenge_id=challenge.id,
                measure=SheetMeasure.SCORE,
                amount=quante,
                aggregation=kind,
            )
        ],
    )


def test_ogni_prova_a_punteggio_e_una_prova_e_la_casella_e_la_media(db_session):
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda_a_punteggio(db_session, user, a_punti)
    session = _seduta(db_session, sheet, user)
    voce = _voce(sheet)

    TrainingSessionService.record_score(session.id, voce.id, user, score=6)
    entry = TrainingSessionService.record_score(session.id, voce.id, user, score=7)

    assert [p.score for p in _prove_di(entry)] == [6, 7]
    assert entry.value == 6.5
    assert entry.aggregation == ScoreAggregation.MEAN.value
    assert entry.target_amount == 3


def test_il_massimo_e_la_somma_si_leggono_dalla_casella(db_session):
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda(
        db_session,
        user,
        [
            SheetItemSpec(
                challenge_id=a_punti.id,
                measure=SheetMeasure.SCORE,
                amount=2,
                aggregation=ScoreAggregation.MAX,
            ),
            SheetItemSpec(
                challenge_id=a_punti.id,
                measure=SheetMeasure.SCORE,
                amount=2,
                aggregation=ScoreAggregation.SUM,
            ),
        ],
    )
    session = _seduta(db_session, sheet, user)
    for voce in sheet.active_items:
        TrainingSessionService.record_score(session.id, voce.id, user, score=3)
        TrainingSessionService.record_score(session.id, voce.id, user, score=8)
    valori = [e.value for e in sorted(session.entries, key=lambda e: e.item.position)]
    assert valori == [8, 11]


def test_l_aggregazione_copiata_sulla_casella_non_si_rilegge_dalla_voce(db_session):
    """Cambiare «media» in «massimo» domani non riscrive il registro (ADR-067 §3)."""
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda_a_punteggio(db_session, user, a_punti, quante=2)
    session = _seduta(db_session, sheet, user)
    voce = _voce(sheet)
    TrainingSessionService.record_score(session.id, voce.id, user, score=2)
    entry = TrainingSessionService.record_score(session.id, voce.id, user, score=8)
    TrainingSessionService.close(session.id, user)

    voce.aggregation = ScoreAggregation.MAX.value
    db_session.flush()
    assert entry.aggregation == ScoreAggregation.MEAN.value
    assert entry.value == 5


def test_non_piu_prove_di_quante_ne_dice_la_voce(db_session):
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda_a_punteggio(db_session, user, a_punti, quante=1)
    session = _seduta(db_session, sheet, user)
    voce = _voce(sheet)
    TrainingSessionService.record_score(session.id, voce.id, user, score=6)
    with pytest.raises(ConflictError):
        TrainingSessionService.record_score(session.id, voce.id, user, score=6)


def test_il_punteggio_non_supera_il_massimo_dell_esercizio(db_session):
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda_a_punteggio(db_session, user, a_punti)
    session = _seduta(db_session, sheet, user)
    with pytest.raises(ValidationError):
        TrainingSessionService.record_score(session.id, _voce(sheet).id, user, score=11)


def test_annullare_l_ultima_prova_a_punteggio(db_session):
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda_a_punteggio(db_session, user, a_punti)
    session = _seduta(db_session, sheet, user)
    voce = _voce(sheet)
    TrainingSessionService.record_score(session.id, voce.id, user, score=6)
    TrainingSessionService.record_score(session.id, voce.id, user, score=8)
    entry = TrainingSessionService.undo_score(session.id, voce.id, user)
    assert entry is not None and entry.value == 6
    assert TrainingSessionService.undo_score(session.id, voce.id, user) is None
    assert not any(e.item_id == voce.id for e in session.entries)


def test_una_voce_a_punteggio_non_si_scrive_col_totale(db_session):
    """Il numero discende dalle prove: un totale a mano lo contraddirebbe."""
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda_a_punteggio(db_session, user, a_punti)
    session = _seduta(db_session, sheet, user)
    with pytest.raises(ValidationError):
        TrainingSessionService.record(session.id, _voce(sheet).id, user, value=7)


def test_il_totale_della_seduta_ignora_il_punteggio_anche_con_la_somma(db_session):
    """D17 non cambia: la soglia somma tiri riusciti, non punti."""
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda(
        db_session,
        user,
        [
            SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.MADE, amount=5),
            SheetItemSpec(
                challenge_id=a_punti.id,
                measure=SheetMeasure.SCORE,
                amount=1,
                aggregation=ScoreAggregation.SUM,
            ),
        ],
    )
    assert sheet.total == 5
    session = _seduta(db_session, sheet, user)
    TrainingSessionService.record(session.id, _voce(sheet, 1).id, user, value=3)
    TrainingSessionService.record_score(session.id, _voce(sheet, 2).id, user, score=9)
    assert session.total == 3
    assert session.max_total == 5


# ── 4 · colpo per colpo: la stessa schermata, e la prova torna nella casella ─
def _colpo_per_colpo(db_session):
    return _challenge(
        db_session, "A colpi", max_score=None, recording_mode=RecordingMode.SHOTS
    )


def test_la_prova_a_colpi_si_aggancia_alla_casella(db_session):
    user = _user(db_session)
    a_colpi = _colpo_per_colpo(db_session)
    sheet = _scheda_a_punteggio(db_session, user, a_colpi, quante=2)
    session = _seduta(db_session, sheet, user)
    voce = _voce(sheet)

    run = ShotRunService.record_shot(user.id, a_colpi.id, made=False)
    entry = TrainingSessionService.attach_attempt(
        session.id, voce.id, user, attempt_id=run.attempt.id
    )
    assert entry.value is None, "una prova aperta non fa ancora numero"

    ShotRunService.record_shot(user.id, a_colpi.id, made=False)
    chiusa = ShotRunService.close(user.id, a_colpi.id)
    entry = TrainingSessionService.refresh_from_attempts(session.id, voce.id, user)
    assert chiusa.training_entry_id == entry.id
    assert entry.value == chiusa.score
    assert entry.is_filled


def test_la_prova_di_un_altro_esercizio_non_si_aggancia(db_session):
    user = _user(db_session)
    a_colpi = _colpo_per_colpo(db_session)
    altro = _colpo_per_colpo(db_session)
    sheet = _scheda_a_punteggio(db_session, user, a_colpi, quante=2)
    session = _seduta(db_session, sheet, user)
    run = ShotRunService.record_shot(user.id, altro.id, made=False)
    with pytest.raises(ValidationError):
        TrainingSessionService.attach_attempt(
            session.id, _voce(sheet).id, user, attempt_id=run.attempt.id
        )


# ── 5 · le statistiche dell'esercizio vedono la scheda ─────────────────────
def test_chi_si_allena_in_scheda_ha_provato_l_esercizio(db_session):
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    sheet = _scheda(
        db_session,
        user,
        [SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.MADE, amount=5)],
    )
    session = _seduta(db_session, sheet, user)
    assert not has_tried(user.id, netto.id)
    TrainingSessionService.record(session.id, _voce(sheet).id, user, value=4)
    assert has_tried(user.id, netto.id)
    assert popularity_for([netto.id])[netto.id].players == 1


def test_lo_storico_dice_che_la_prova_viene_dalla_scheda(db_session):
    user = _user(db_session)
    a_punti = _challenge(db_session, "A punti", max_score=10)
    sheet = _scheda_a_punteggio(db_session, user, a_punti)
    session = _seduta(db_session, sheet, user)
    TrainingSessionService.record_score(session.id, _voce(sheet).id, user, score=6)

    voci = TrainingHistoryService.get_drill_attempts(user.id)
    assert len(voci) == 1
    assert voci[0]["source"] == "sheet"
    assert voci[0]["sheet_name"] == "Scheda"
    assert voci[0]["score"] == 6


def test_l_andamento_conta_le_prove_e_non_anche_la_casella(db_session):
    """Cinque prove in scheda sono cinque osservazioni, non sei (ADR-068 emendata)."""
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    ChallengeProfileService.set_profile(netto.id, abilita=[Abilita.TIRO.value])
    sheet = _scheda(
        db_session,
        user,
        [SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.MADE, amount=5)],
    )
    session = _seduta(db_session, sheet, user)
    TrainingSessionService.record(session.id, _voce(sheet).id, user, value=4)
    TrainingSessionService.close(session.id, user)
    db_session.flush()

    andamento = build_andamento(user.id, Periodo.MESE)
    assert andamento.attempts == 5
    assert andamento.sheet_attempts == 5
    assert andamento.pct == 80


def test_una_casella_vecchia_senza_prove_si_legge_ancora(db_session):
    """Le caselle scritte prima dell'ADR-072 non hanno prove: restano osservazioni."""
    from models.training_sheet.models import TrainingEntry

    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    ChallengeProfileService.set_profile(netto.id, abilita=[Abilita.TIRO.value])
    sheet = _scheda(
        db_session,
        user,
        [SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.MADE, amount=5)],
    )
    session = _seduta(db_session, sheet, user)
    session.entries.append(
        TrainingEntry(
            item_id=_voce(sheet).id,
            value=4,
            measure=SheetMeasure.MADE.value,
            target_amount=5,
        )
    )
    db_session.flush()
    TrainingSessionService.close(session.id, user)
    db_session.flush()

    andamento = build_andamento(user.id, Periodo.MESE)
    assert andamento.attempts == 1
    assert andamento.sheet_attempts == 1


# ── 6 · l'XP lo dà la seduta ───────────────────────────────────────────────
@pytest.fixture
def eventi_delle_prove():
    """Cattura gli eventi di prova completata, senza toccare gli altri ascoltatori."""
    originali = {k: list(v) for k, v in EventBus._handlers.items()}
    raccolti = []
    EventBus.subscribe(ChallengeAttemptCompletedEvent)(raccolti.append)
    yield raccolti
    EventBus._handlers = originali


def test_la_prova_in_scheda_annuncia_la_sua_origine(db_session, eventi_delle_prove):
    user = _user(db_session)
    netto = _challenge(db_session, "Netto", pass_fail=True)
    sheet = _scheda(
        db_session,
        user,
        [SheetItemSpec(challenge_id=netto.id, measure=SheetMeasure.MADE, amount=2)],
    )
    session = _seduta(db_session, sheet, user)
    TrainingSessionService.record(session.id, _voce(sheet).id, user, value=1)
    assert len(eventi_delle_prove) == 2
    assert all(e.origin == DrillOrigin.SHEET.value for e in eventi_delle_prove)
    assert all(e.is_from_sheet for e in eventi_delle_prove)


def test_l_xp_non_lo_paga_la_prova_in_scheda(db_session):
    from models.gamification.event_handlers import GamificationEventHandlers
    from models.gamification.models import XPTransaction, XPTransactionType

    user = _user(db_session)
    evento = ChallengeAttemptCompletedEvent(
        attempt_id=1,
        challenge_id=1,
        challenge_name="X",
        user_id=user.id,
        origin=DrillOrigin.SHEET.value,
        passed=True,
    )
    GamificationEventHandlers.handle_challenge_attempt_completed_for_xp(evento)
    db_session.flush()
    assert (
        XPTransaction.query.filter_by(
            user_id=user.id, transaction_type=XPTransactionType.CHALLENGE_COMPLETION
        ).count()
        == 0
    )
