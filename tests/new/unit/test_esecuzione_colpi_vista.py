"""La prova in corso colpo per colpo, come la si vede (fase 5b; ADR-066).

`models/challenge/run_view.py` è di sola lettura: dice a che colpo si è, quanto
si è fatto finora, che cosa disegna il grafico e quale frase lo accompagna. La
proiezione è una previsione, quindi deve tacere quando non ha di che appoggiarsi.
"""

from __future__ import annotations

import json
import uuid

from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.recording import RecordingMode
from models.challenge.run_view import build_run
from models.challenge.shot_service import ShotRunService
from models.user.models import User
from models.user.role_enum import UserRole

SCENA = json.dumps(
    {
        "v": 4,
        "items": [
            {"type": "target", "x": 600, "y": 200, "step": 50, "values": [3, 2, 1]}
        ],
    }
)


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


def _esercizio(db_session, colpi=10):
    c = Challenge(
        title=f"Ferma {uuid.uuid4().hex[:5]}",
        description="x",
        image_path="t.png",
        diagram_scene=SCENA,
        pass_fail_only=False,
        recording_mode=RecordingMode.SHOTS.value,
        shots_count=colpi,
        max_score=colpi * 3,
        is_active=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _tira(utente, esercizio, *punti):
    """Un colpo per valore: 3 al centro, 2 e 1 sugli anelli, 0 = mancata."""
    dove = {3: 600, 2: 660, 1: 720}
    for p in punti:
        if p:
            ShotRunService.record_shot(
                utente.id, esercizio.id, made=True, x=dove[p], y=200
            )
        else:
            ShotRunService.record_shot(utente.id, esercizio.id, made=False)
    return ShotRunService.current(utente.id, esercizio.id)


def _prova_chiusa(db_session, utente, esercizio, punteggio):
    db_session.add(
        ChallengeAttempt(
            user_id=utente.id,
            challenge_id=esercizio.id,
            score=punteggio,
            completed=True,
        )
    )
    db_session.flush()


class TestSenzaProvaAperta:
    def test_non_c_e_niente_da_mostrare(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        assert build_run(ShotRunService.current(u.id, c.id)) is None


class TestLaProvaInCorso:
    def test_dice_a_che_colpo_si_e(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session, colpi=10)
        vista = build_run(_tira(u, c, 3, 2))
        assert vista is not None
        assert vista.kicker == "Colpo 3 di 10"
        assert vista.figure == "5 punti"
        assert [(s.position, s.points) for s in vista.shots] == [(1, 3), (2, 2)]
        # Il punto d'arrivo viaggia con la striscia: è quello che il panno
        # disegna come nuvola delle imbucate.
        assert (vista.shots[0].x, vista.shots[0].y) == (600, 200)
        assert vista.can_undo is True

    def test_all_ultimo_colpo_il_titolo_non_sfora(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session, colpi=2)
        vista = build_run(_tira(u, c, 3, 3))
        assert vista is not None
        assert vista.kicker == "Colpo 2 di 2"
        assert vista.is_full is True
        assert "chiudi la prova" in vista.sentence

    def test_le_due_percentuali(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        vista = build_run(_tira(u, c, 3, 0, 1))
        assert vista is not None
        assert vista.pocketing == 67  # due imbucate su tre
        # Posizione, sulle due imbucate: il centro vale 1, il colpo a 120 unità
        # su un raggio di 150 vale 0,2. La mancata non entra nel conto.
        assert vista.position == 60

    def test_il_grafico_ha_una_barra_per_colpo(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        vista = build_run(_tira(u, c, 3, 1))
        assert vista is not None and vista.chart is not None
        assert [s.value for s in vista.chart.slots if s.filled] == [3, 1]


class TestLaFrase:
    def test_senza_storia_e_la_prima_volta(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        vista = build_run(_tira(u, c, 3))
        assert vista is not None
        assert "prima prova" in vista.sentence
        assert vista.chart is not None and vista.chart.reference_y is None

    def test_coi_primi_colpi_non_si_proietta_ancora(self, db_session):
        """Due colpi fortunati direbbero «chiudi a 30» con troppa sicurezza."""
        u, c = _utente(db_session), _esercizio(db_session, colpi=10)
        _prova_chiusa(db_session, u, c, 20)
        vista = build_run(_tira(u, c, 3, 3))
        assert vista is not None
        assert vista.sentence == "Di solito chiudi a 20."

    def test_la_proiezione_si_confronta_col_solito(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session, colpi=10)
        _prova_chiusa(db_session, u, c, 20)  # il solito: 2 a colpo
        vista = build_run(_tira(u, c, 3, 3, 3))  # a questo ritmo: 30
        assert vista is not None
        assert (
            vista.sentence
            == "A questo ritmo chiudi a 30: 10 punti sopra il tuo solito."
        )

    def test_sotto_il_solito_lo_dice(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session, colpi=10)
        _prova_chiusa(db_session, u, c, 20)
        vista = build_run(_tira(u, c, 1, 1, 1))  # a questo ritmo: 10
        assert vista is not None
        assert (
            vista.sentence
            == "A questo ritmo chiudi a 10: 10 punti sotto il tuo solito."
        )

    def test_la_media_di_confronto_e_a_colpo(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session, colpi=10)
        _prova_chiusa(db_session, u, c, 20)
        vista = build_run(_tira(u, c, 3))
        assert vista is not None and vista.chart is not None
        assert vista.chart.reference_label == "la tua media 2 a colpo"
