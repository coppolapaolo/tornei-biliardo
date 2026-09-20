"""L'andamento dell'allenamento: due mondi, una scala sola (ADR-068, #181).

La verifica che il piano della fase 7 chiede è questa: le prove del catalogo e
le caselle delle schede **si presentano insieme senza sommarsi**. Qui vuol dire
tre cose, e ognuna ha il suo test:

* entrambe diventano una **quota di ciò che era ottenibile**, e un 12 su 15 vale
  quanto un 4 su 5 tiri;
* ogni registrazione conta **una**, e la riga di un asse dice quante vengono
  dalle schede;
* ciò che una scala non ce l'ha — minuti, spunte, prove senza tetto dichiarato —
  resta **fuori** e si conta, invece di sparire.

Il resto difende le regole che rendono leggibile il disegno: un asse con meno di
cinque prove sta sul radar ma non prende una riga, il poligono del «prima» non si
disegna con dei vertici inventati, e con «Sempre» un prima non c'è.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.andamento import MIN_OSSERVAZIONI, Periodo, build_andamento
from models.andamento.radar import build_radar
from models.base import utc_now
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.profile_service import ChallengeProfileService
from models.challenge.vocabulary import Abilita, CategoryAxis, Gesto
from models.training_sheet.measure import SheetMeasure
from models.training_sheet.models import (
    TrainingEntry,
    TrainingSession,
    TrainingSheet,
    TrainingSheetItem,
)
from models.user.models import User
from models.user.role_enum import UserRole


# ── allestimento ────────────────────────────────────────────────────────────
def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"and_{uid}", email=f"and_{uid}@test.local", role=UserRole.PLAYER.value
    )
    user.set_password("p")
    db_session.add(user)
    db_session.flush()
    return user


def _challenge(
    db_session,
    titolo: str,
    *,
    max_score=None,
    pass_fail=False,
    abilita=(),
    gesti=(),
) -> Challenge:
    challenge = Challenge(
        title=titolo,
        description=f"{titolo}: istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=pass_fail,
        max_score=max_score,
    )
    db_session.add(challenge)
    db_session.flush()
    if abilita or gesti:
        ChallengeProfileService.set_profile(
            challenge.id,
            abilita=[a.value for a in abilita],
            gesti=[g.value for g in gesti],
        )
        db_session.flush()
    return challenge


def _prova(db_session, user, challenge, *, score=None, passed=None, giorni_fa=1):
    attempt = ChallengeAttempt(
        challenge_id=challenge.id,
        user_id=user.id,
        score=score,
        passed=passed,
        completed=True,
        attempted_at=utc_now() - timedelta(days=giorni_fa),
    )
    db_session.add(attempt)
    db_session.flush()
    return attempt


def _scheda(db_session, user, voci):
    """Una scheda con le sue voci: `voci` è una lista di (challenge, misura, quanti)."""
    sheet = TrainingSheet(name="Scheda", owner_id=user.id)
    db_session.add(sheet)
    db_session.flush()
    items = []
    for posizione, (challenge, misura, quanti) in enumerate(voci, start=1):
        item = TrainingSheetItem(
            sheet_id=sheet.id,
            challenge_id=challenge.id,
            position=posizione,
            measure=misura.value,
            amount=quanti,
        )
        db_session.add(item)
        items.append(item)
    db_session.flush()
    return sheet, items


def _seduta(db_session, user, sheet, caselle, *, giorni_fa=1, chiusa=True):
    """Una seduta con le sue caselle: `caselle` è una lista di (item, valore)."""
    quando = utc_now() - timedelta(days=giorni_fa)
    session = TrainingSession(
        sheet_id=sheet.id,
        user_id=user.id,
        started_at=quando,
        ended_at=quando if chiusa else None,
    )
    db_session.add(session)
    db_session.flush()
    for item, valore in caselle:
        db_session.add(
            TrainingEntry(
                session_id=session.id,
                item_id=item.id,
                value=valore,
                measure=item.measure,
                target_amount=item.amount,
            )
        )
    db_session.flush()
    return session


# ── la scala comune ─────────────────────────────────────────────────────────
def test_catalogo_e_scheda_usano_la_stessa_scala(db_session):
    """12 su 15 e 4 su 5 tiri sono lo stesso ottanta per cento."""
    user = _user(db_session)
    dal_catalogo = _challenge(
        db_session, "Spot shot", max_score=15, abilita=[Abilita.TIRO]
    )
    in_scheda = _challenge(
        db_session, "Linea tangente", max_score=None, abilita=[Abilita.TIRO]
    )
    _prova(db_session, user, dal_catalogo, score=12)
    sheet, items = _scheda(db_session, user, [(in_scheda, SheetMeasure.MADE, 5)])
    _seduta(db_session, user, sheet, [(items[0], 4)])

    andamento = build_andamento(user.id, Periodo.MESE, CategoryAxis.ABILITA)

    (tiro,) = andamento.radar_rows
    assert tiro.value is Abilita.TIRO
    assert tiro.pct == 80, "le due registrazioni valgono entrambe l'80%"
    assert tiro.count == 2
    assert tiro.sheet_count == 1, "la riga dice quante vengono dalle schede"
    assert andamento.attempts == 2
    assert andamento.sheet_attempts == 1


def test_le_due_fonti_non_si_sommano_sullo_stesso_esercizio(db_session):
    """Sullo stesso esercizio restano due registrazioni, non una somma.

    È il punto dell'ADR-068: insieme, non sommate. Un 10 su 10 nel catalogo e un
    5 su 10 tiri in scheda fanno un asse al 75 per cento — la media di due — non
    un 15 su 20 né un 150 per cento.
    """
    user = _user(db_session)
    challenge = _challenge(
        db_session, "Ghost ball", max_score=10, abilita=[Abilita.POSIZIONE]
    )
    _prova(db_session, user, challenge, score=10)
    sheet, items = _scheda(db_session, user, [(challenge, SheetMeasure.MADE, 10)])
    _seduta(db_session, user, sheet, [(items[0], 5)])

    (posizione,) = build_andamento(
        user.id, Periodo.MESE, CategoryAxis.ABILITA
    ).radar_rows
    assert posizione.pct == 75
    assert posizione.count == 2


def test_una_seduta_aperta_non_entra(db_session):
    """Quella che si sta facendo non è ancora un risultato."""
    user = _user(db_session)
    challenge = _challenge(db_session, "Stop", max_score=5, abilita=[Abilita.TIRO])
    sheet, items = _scheda(db_session, user, [(challenge, SheetMeasure.MADE, 5)])
    _seduta(db_session, user, sheet, [(items[0], 5)], chiusa=False)

    assert build_andamento(user.id).is_empty


# ── ciò che una scala non ce l'ha ───────────────────────────────────────────
@pytest.mark.parametrize(
    "misura, valore",
    [(SheetMeasure.MINUTES, 30), (SheetMeasure.DONE, None)],
)
def test_minuti_e_spunte_restano_fuori_e_si_contano(db_session, misura, valore):
    user = _user(db_session)
    challenge = _challenge(db_session, "Rastrello", abilita=[Abilita.FONDAMENTALI])
    sheet, items = _scheda(db_session, user, [(challenge, misura, 30)])
    _seduta(db_session, user, sheet, [(items[0], valore)])

    andamento = build_andamento(user.id)
    assert andamento.is_empty, "una durata non è una quota di ciò che era ottenibile"
    assert andamento.senza_scala == 1, "e lo si dice, invece di farla sparire"


def test_una_prova_senza_tetto_dichiarato_resta_fuori(db_session):
    user = _user(db_session)
    senza = _challenge(db_session, "A oltranza", max_score=None, abilita=[Abilita.TIRO])
    _prova(db_session, user, senza, score=40)

    andamento = build_andamento(user.id)
    assert andamento.is_empty
    assert andamento.senza_scala == 1


def test_riuscita_o_no_vale_tutto_o_niente(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Kick", pass_fail=True, gesti=[Gesto.KICK])
    _prova(db_session, user, challenge, passed=True)
    _prova(db_session, user, challenge, passed=True)
    _prova(db_session, user, challenge, passed=False)
    _prova(db_session, user, challenge, passed=False)

    (kick,) = build_andamento(user.id, Periodo.MESE, CategoryAxis.GESTO).radar_rows
    assert kick.pct == 50, "due su quattro è la percentuale di successo"


# ── gli assi magri ──────────────────────────────────────────────────────────
def test_un_asse_con_poche_prove_sta_sul_radar_ma_non_prende_una_riga(db_session):
    user = _user(db_session)
    solido = _challenge(db_session, "Tanto", max_score=10, abilita=[Abilita.TIRO])
    magro = _challenge(db_session, "Poco", max_score=10, abilita=[Abilita.DIFESA])
    for _volta in range(MIN_OSSERVAZIONI):
        _prova(db_session, user, solido, score=8)
    _prova(db_session, user, magro, score=3)

    andamento = build_andamento(user.id)

    assert [riga.value for riga in andamento.rows] == [Abilita.TIRO]
    assert Abilita.DIFESA in [riga.value for riga in andamento.radar_rows]
    assert [riga.value for riga in andamento.thin] == [Abilita.DIFESA]


def test_un_esercizio_con_due_abilita_entra_in_entrambe(db_session):
    """Le categorie sono un vocabolario, non una partizione: il tiro vale intero."""
    user = _user(db_session)
    challenge = _challenge(
        db_session, "Doppia", max_score=10, abilita=[Abilita.TIRO, Abilita.POSIZIONE]
    )
    _prova(db_session, user, challenge, score=7)

    righe = {r.value: r for r in build_andamento(user.id).radar_rows}
    assert righe[Abilita.TIRO].pct == 70
    assert righe[Abilita.POSIZIONE].pct == 70


# ── le finestre ─────────────────────────────────────────────────────────────
def test_il_confronto_e_con_la_finestra_di_pari_durata_prima(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Serie", max_score=10, abilita=[Abilita.TIRO])
    _prova(db_session, user, challenge, score=8, giorni_fa=3)
    _prova(db_session, user, challenge, score=5, giorni_fa=40)

    andamento = build_andamento(user.id, Periodo.MESE)
    assert andamento.pct == 80
    assert andamento.pct_before == 50
    assert andamento.delta == 30
    assert andamento.attempts == 1, "il periodo prima non entra nel conto di adesso"


def test_con_sempre_non_ce_un_prima(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Serie", max_score=10, abilita=[Abilita.TIRO])
    _prova(db_session, user, challenge, score=8, giorni_fa=3)
    _prova(db_session, user, challenge, score=5, giorni_fa=400)

    andamento = build_andamento(user.id, Periodo.SEMPRE)
    assert andamento.attempts == 2, "«Sempre» guarda tutto"
    assert andamento.pct_before is None
    assert andamento.delta is None


def test_il_periodo_ignoto_vale_il_mese(db_session):
    assert Periodo.parse("chissa") is Periodo.MESE
    assert Periodo.parse(None) is Periodo.MESE
    assert Periodo.parse("trimestre") is Periodo.TRIMESTRE


# ── il disegno ──────────────────────────────────────────────────────────────
def test_il_poligono_del_prima_non_si_disegna_con_vertici_inventati():
    """Un asse senza numeri prima non vale zero: vale «non l'avevo allenato»."""
    completo = build_radar(["a", "b", "c"], [50, 60, 70], [40, 50, 60])
    assert completo is not None and completo.has_before

    monco = build_radar(["a", "b", "c"], [50, 60, 70], [40, None, 60])
    assert monco is not None and not monco.has_before


def test_sotto_tre_assi_non_ce_un_poligono():
    assert build_radar(["a", "b"], [50, 60], [None, None]) is None


def test_il_primo_vertice_sta_in_cima():
    radar = build_radar(["a", "b", "c", "d"], [100, 100, 100, 100], [None] * 4)
    assert radar is not None
    primo = radar.now.split(" ")[0]
    x, y = (float(n) for n in primo.split(","))
    assert x == pytest.approx(radar.center, abs=0.1)
    assert y < radar.center, "in SVG la y cresce verso il basso"


def test_il_radar_non_sborda_nemmeno_oltre_il_fondoscala(db_session):
    """Una voce a minuti si può superare; un asse al 140% no.

    Il fondoscala del radar è condiviso da tutti gli assi: uno sforato
    renderebbe illeggibili gli altri.
    """
    user = _user(db_session)
    challenge = _challenge(db_session, "Vinte", max_score=None, abilita=[Abilita.TIRO])
    sheet, items = _scheda(db_session, user, [(challenge, SheetMeasure.WINS, 5)])
    _seduta(db_session, user, sheet, [(items[0], 9)])

    (tiro,) = build_andamento(user.id).radar_rows
    assert tiro.pct == 100


# ── le bande ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "punteggio, banda",
    [
        (9, "solido"),
        (7, "solido"),
        (6, "in crescita"),
        (5, "in crescita"),
        (4, "da costruire"),
    ],
)
def test_le_tre_bande(db_session, punteggio, banda):
    user = _user(db_session)
    challenge = _challenge(db_session, "Banda", max_score=10, abilita=[Abilita.TIRO])
    _prova(db_session, user, challenge, score=punteggio)

    (riga,) = build_andamento(user.id).radar_rows
    assert riga.band == banda
