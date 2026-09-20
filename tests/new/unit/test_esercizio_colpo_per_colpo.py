"""La prova fatta di colpi (redesign TPA ed esercizi, fase 5b; ADR-066).

Due pezzi, provati separati:

* ``models/challenge/target.py`` — il bersaglio come dato dentro la scena del
  disegnatore, e quanti punti vale un punto del panno;
* ``models/challenge/shot_service.py`` — la prova come sequenza di colpi: il
  punteggio **discende** dai colpi e non si scrive a mano, l'ultimo colpo si
  annulla, la prova si chiude con un gesto e una lasciata a metà si riprende.
"""

from __future__ import annotations

import json
import uuid

import pytest

from models.challenge.diagram import parse_scene
from models.challenge.models import Challenge, ChallengeAttempt, ChallengeShot
from models.challenge.recording import RecordingMode
from models.challenge.services import ChallengeService
from models.challenge.shot_service import ShotRunService
from models.challenge.target import Target, target_from_scene
from models.exceptions import ConflictError, ValidationError
from models.user.models import User
from models.user.role_enum import UserRole


def _scena(**bersaglio) -> str:
    voce = {"type": "target", "id": "t1", "x": 600, "y": 200, "step": 50}
    voce.update({"values": [3, 2, 1]}, **bersaglio)
    return json.dumps({"v": 4, "orient": "h", "items": [voce]})


class TestIlBersaglioNellaScena:
    def test_si_legge_dalla_scena(self):
        t = target_from_scene(_scena())
        assert t == Target(x=600, y=200, step=50, values=(3, 2, 1))
        assert t.outer_radius == 150
        assert t.max_points == 3

    def test_una_scena_senza_bersaglio_non_ne_ha(self):
        assert target_from_scene('{"v":4,"items":[]}') is None
        assert target_from_scene(None) is None

    @pytest.mark.parametrize(
        "difetto",
        [
            {"step": 30},  # non è un multiplo di un quarto di diamante
            {"step": 0},
            {"values": []},
            {"values": [1, 2, 3, 4, 5, 6]},  # più di cinque anelli
            {"values": [3, -1]},
            {"values": [3, "due"]},
            {"x": 900},  # fuori dal panno
            {"y": -1},
        ],
    )
    def test_un_bersaglio_storto_si_rifiuta_al_salvataggio(self, difetto):
        with pytest.raises(ValidationError):
            parse_scene(_scena(**difetto))

    def test_un_bersaglio_solo(self):
        scena = json.loads(_scena())
        scena["items"].append(dict(scena["items"][0], id="t2"))
        with pytest.raises(ValidationError):
            parse_scene(json.dumps(scena))

    def test_il_bersaglio_buono_passa(self):
        assert target_from_scene(parse_scene(_scena())) is not None


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


def _esercizio(db_session, *, colpi=3, scena=None):
    c = Challenge(
        title=f"Ferma {uuid.uuid4().hex[:5]}",
        description="x",
        image_path="t.png",
        diagram_scene=scena or _scena(),
        pass_fail_only=False,
        recording_mode=RecordingMode.SHOTS.value,
        shots_count=colpi,
        max_score=colpi * 3,
        is_active=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


class TestLaProvaFattaDiColpi:
    def test_il_colpo_prende_i_punti_dal_punto(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        run = ShotRunService.record_shot(u.id, c.id, made=True, x=610, y=200)
        assert [s.points for s in run.shots] == [3]
        assert run.attempt.completed is False
        assert run.attempt.score is None  # finché è aperta non ha un punteggio

    def test_la_non_imbucata_vale_zero_e_non_ha_un_punto(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        run = ShotRunService.record_shot(u.id, c.id, made=False, x=600, y=200)
        colpo = run.shots[0]
        assert (colpo.made, colpo.points, colpo.x, colpo.y) == (False, 0, None, None)

    # Un rifiuto per test: il rollback di `@transactional` porta via anche ciò
    # che la fixture ha creato col solo `flush`.
    def test_l_imbucata_vuole_un_punto(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        with pytest.raises(ValidationError):
            ShotRunService.record_shot(u.id, c.id, made=True, x=None, y=None)

    def test_il_punto_sta_sul_panno(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        with pytest.raises(ValidationError):
            ShotRunService.record_shot(u.id, c.id, made=True, x=801, y=10)

    def test_i_colpi_vanno_nella_stessa_prova_aperta(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.record_shot(u.id, c.id, made=True, x=600, y=200)
        run = ShotRunService.record_shot(u.id, c.id, made=False)
        assert [s.position for s in run.shots] == [1, 2]
        assert ChallengeAttempt.query.filter_by(user_id=u.id).count() == 1

    def test_oltre_l_ultimo_colpo_non_si_va(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session, colpi=1)
        ShotRunService.record_shot(u.id, c.id, made=False)
        with pytest.raises(ConflictError):
            ShotRunService.record_shot(u.id, c.id, made=False)

    def test_si_chiude_con_un_gesto_e_il_punteggio_e_la_somma(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        for x in (600, 670, 730):  # 3 + 2 + 1
            ShotRunService.record_shot(u.id, c.id, made=True, x=x, y=200)
        chiusa = ShotRunService.close(u.id, c.id)
        assert (chiusa.completed, chiusa.score) == (True, 6)

    def test_a_meta_non_si_chiude(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.record_shot(u.id, c.id, made=False)
        with pytest.raises(ConflictError):
            ShotRunService.close(u.id, c.id)

    def test_l_annulla_toglie_l_ultimo_colpo(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.record_shot(u.id, c.id, made=True, x=600, y=200)
        ShotRunService.record_shot(u.id, c.id, made=False)
        run = ShotRunService.undo_last(u.id, c.id)
        assert [s.points for s in run.shots] == [3]

    def test_tolto_l_ultimo_colpo_la_prova_aperta_sparisce(self, db_session):
        """Una prova aperta senza colpi è una riga che nessuno chiuderà più."""
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.record_shot(u.id, c.id, made=False)
        run = ShotRunService.undo_last(u.id, c.id)
        assert run.attempt is None
        assert ChallengeAttempt.query.filter_by(user_id=u.id).count() == 0

    def test_la_prova_a_meta_si_riprende(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.record_shot(u.id, c.id, made=True, x=600, y=200)
        run = ShotRunService.current(u.id, c.id)
        assert run.next_position == 2
        assert run.total == 3

    def test_ricominciare_butta_la_prova_aperta(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        ShotRunService.record_shot(u.id, c.id, made=False)
        ShotRunService.restart(u.id, c.id)
        assert ChallengeShot.query.count() == 0
        assert ShotRunService.current(u.id, c.id).attempt is None

    def test_il_totale_a_mano_si_rifiuta(self, db_session):
        """Due segnapunti che si contraddicono al primo tocco non devono
        esistere: è la regola dell'ADR-044, portata agli esercizi."""
        u, c = _utente(db_session), _esercizio(db_session)
        with pytest.raises(ValidationError):
            ChallengeService.record_attempt(user_id=u.id, challenge_id=c.id, score=5)

    def test_su_un_esercizio_a_totale_i_colpi_non_si_registrano(self, db_session):
        u, c = _utente(db_session), _esercizio(db_session)
        c.recording_mode = RecordingMode.TOTAL.value
        db_session.flush()
        with pytest.raises(ValidationError):
            ShotRunService.record_shot(u.id, c.id, made=False)
