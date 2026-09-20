"""La cornice di esecuzione di un esercizio (redesign TPA ed esercizi, fase 5a).

La vista sta in ``models/challenge/execution_view.py`` ed è di sola lettura:
dice quali prove sono «di oggi», come si chiama quella che sta per arrivare,
che cosa disegna il grafico dal vivo e quale frase lo accompagna.

«Oggi» non è un'entità: si ricava dall'ora delle prove, nel fuso di chi legge
(ADR-043). È il motivo per cui la modalità a punteggio entra nella cornice
senza cambiare dati.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from models.challenge.execution_view import build_progress
from models.challenge.live_chart import bars_chart
from models.challenge.models import Challenge, ChallengeAttempt
from models.user.models import User
from models.user.role_enum import UserRole

ROMA = ZoneInfo("Europe/Rome")
# Le 21:00 di Roma del 20 settembre, in UTC naive come le tiene il DB.
ADESSO = datetime(2026, 9, 20, 19, 0)


def _utente(db_session):
    u = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _esercizio(db_session, *, pass_fail=False, max_score=10):
    c = Challenge(
        title=f"Spot {uuid.uuid4().hex[:5]}",
        description="x",
        image_path="t.jpg",
        pass_fail_only=pass_fail,
        max_score=None if pass_fail else max_score,
        is_active=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _prova(db_session, utente, esercizio, quando, *, score=None, passed=None):
    a = ChallengeAttempt(
        user_id=utente.id,
        challenge_id=esercizio.id,
        score=score,
        passed=passed,
        completed=True,
        attempted_at=quando,
    )
    db_session.add(a)
    db_session.flush()
    return a


class TestOggi:
    def test_il_giorno_e_quello_di_chi_legge(self, db_session):
        """Le 23:30 UTC del 19 sono già il 20 a Roma: quella prova è di oggi."""
        u, c = _utente(db_session), _esercizio(db_session)
        _prova(db_session, u, c, datetime(2026, 9, 19, 21, 0), score=5)  # 23:00 Roma
        _prova(db_session, u, c, datetime(2026, 9, 19, 23, 30), score=6)  # 01:30 Roma
        _prova(db_session, u, c, ADESSO - timedelta(minutes=5), score=7)

        vista = build_progress(c, u.id, tz=ROMA, now=ADESSO)

        assert [p.score for p in vista.today] == [7, 6]  # la più recente per prima

    def test_le_prove_aperte_non_contano(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        aperta = _prova(db_session, u, c, ADESSO, score=None)
        aperta.completed = False
        db_session.flush()

        assert build_progress(c, u.id, tz=ROMA, now=ADESSO).today == []

    def test_la_prossima_prova_ha_un_nome(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        assert build_progress(c, u.id, tz=ROMA, now=ADESSO).next_label == "prima prova"
        for i in range(3):
            _prova(db_session, u, c, ADESSO - timedelta(minutes=30 - i), score=6)
        assert build_progress(c, u.id, tz=ROMA, now=ADESSO).next_label == "quarta prova"

    def test_oltre_la_decima_si_conta_in_cifre(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        for i in range(10):
            _prova(db_session, u, c, ADESSO - timedelta(minutes=30 - i), score=6)
        assert build_progress(c, u.id, tz=ROMA, now=ADESSO).next_label == "prova 11"


class TestFrase:
    def test_sopra_la_media_da_due_prove(self, db_session):
        """La media di confronto è quella di PRIMA di oggi: confrontare le prove
        di oggi con una media che le contiene le tirerebbe verso il centro."""
        u, c = _utente(db_session), _esercizio(db_session)
        ieri = ADESSO - timedelta(days=1)
        for s in (6, 6, 7, 10):  # media 7,25 — record 10
            _prova(db_session, u, c, ieri, score=s)
        for i, s in enumerate((6, 8, 8)):
            _prova(db_session, u, c, ADESSO - timedelta(minutes=30 - i), score=s)

        vista = build_progress(c, u.id, tz=ROMA, now=ADESSO)

        assert vista.average == 7.25
        assert vista.best == 10
        assert "sopra la tua media da 2 prove" in vista.sentence
        assert "Record: 10" in vista.sentence

    def test_senza_storia_niente_media(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        vista = build_progress(c, u.id, tz=ROMA, now=ADESSO)
        assert vista.average is None
        assert vista.chart is None
        assert vista.sentence  # una frase c'è sempre: dice che è la prima volta

    def test_riuscita_o_no_conta_le_riuscite(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session, pass_fail=True)
        for i, esito in enumerate((True, False, True)):
            _prova(db_session, u, c, ADESSO - timedelta(minutes=30 - i), passed=esito)

        vista = build_progress(c, u.id, tz=ROMA, now=ADESSO)

        assert "2 riuscite su 3" in vista.sentence


class TestGrafico:
    def test_un_posto_per_prova_e_qualcuno_ancora_vuoto(self):
        """I posti vuoti dicono che la serata non è finita: mai meno di sei, e
        sempre almeno due oltre l'ultima prova."""
        assert len(bars_chart([6, 8], top=10).slots) == 6
        assert len(bars_chart([5] * 7, top=10).slots) == 9

    def test_l_ultima_barra_e_quella_accesa(self):
        g = bars_chart([6, 8, 7], top=10)
        piene = [s for s in g.slots if s.filled]
        assert [s.now for s in piene] == [False, False, True]

    def test_la_barra_e_alta_quanto_il_punteggio(self):
        g = bars_chart([0, 5, 10], top=10)
        basse, mezze, alte = [s.height for s in g.slots[:3]]
        assert basse < mezze < alte
        assert alte == g.plot_height

    def test_senza_tetto_il_fondoscala_e_il_massimo_visto(self):
        g = bars_chart([3, 30], top=None, reference=12)
        assert g.slots[1].height == g.plot_height

    def test_la_linea_di_confronto_sta_alla_sua_quota(self):
        g = bars_chart([5], top=10, reference=5)
        assert g.reference_y == g.baseline - g.plot_height / 2

    def test_il_grafico_della_vista_usa_la_media_di_prima(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        _prova(db_session, u, c, ADESSO - timedelta(days=2), score=4)
        _prova(db_session, u, c, ADESSO - timedelta(minutes=3), score=9)

        vista = build_progress(c, u.id, tz=ROMA, now=ADESSO)

        assert vista.chart is not None
        assert [s.value for s in vista.chart.slots if s.filled] == [9]
        assert vista.chart.reference_label == "la tua media 4"
