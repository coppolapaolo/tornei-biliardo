"""Dichiarare che un esercizio si registra colpo per colpo (fase 5b; ADR-066).

Lo dice chi crea l'esercizio, nel modulo. Due cose non si scrivono a mano: il
**massimo**, che è N colpi per il valore più alto del bersaglio, e il
**bersaglio**, che sta nel disegno. Senza bersaglio la voce non si può
scegliere — un esercizio colpo per colpo senza anelli non saprebbe dare punti.
"""

from __future__ import annotations

import json
import uuid

import pytest
from werkzeug.datastructures import MultiDict

from models.challenge.authoring import (
    ChallengeAuthoringService,
    ChallengeDraft,
    EvidenceDecisionRequired,
    MeaningChangeKind,
)
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.recording import RecordingMode
from models.exceptions import ValidationError
from models.user.models import User
from models.user.role_enum import UserRole
from routes.challenge_form import draft_from_challenge, parse_challenge_draft

SCENA = json.dumps(
    {
        "v": 4,
        "items": [
            {"type": "target", "x": 600, "y": 200, "step": 50, "values": [3, 2, 1]}
        ],
    }
)
SENZA_BERSAGLIO = json.dumps({"v": 4, "items": []})


def _bozza(**extra) -> ChallengeDraft:
    base = dict(
        description="Ferma la bianca nel cerchio",
        recording_mode=RecordingMode.SHOTS.value,
        shots_count=20,
    )
    base.update(extra)
    return ChallengeDraft(**base)


class TestCreare:
    def test_il_massimo_lo_scrive_il_servizio(self, db_session):
        c = ChallengeAuthoringService.create(
            _bozza(max_score=7),  # quello scritto a mano non conta
            image_path="t.png",
            created_by_id=None,
            diagram_scene=SCENA,
        )
        assert (c.recording_mode, c.shots_count, c.max_score) == ("shots", 20, 60)

    def test_senza_bersaglio_non_si_puo(self, db_session):
        with pytest.raises(ValidationError):
            ChallengeAuthoringService.create(
                _bozza(),
                image_path="t.png",
                created_by_id=None,
                diagram_scene=SENZA_BERSAGLIO,
            )

    def test_con_una_foto_non_si_puo(self, db_session):
        with pytest.raises(ValidationError):
            ChallengeAuthoringService.create(
                _bozza(), image_path="t.jpg", created_by_id=None, diagram_scene=None
            )

    @pytest.mark.parametrize("colpi", [None, 0, 101])
    def test_i_colpi_vanno_da_uno_a_cento(self, db_session, colpi):
        with pytest.raises(ValidationError):
            ChallengeAuthoringService.create(
                _bozza(shots_count=colpi),
                image_path="t.png",
                created_by_id=None,
                diagram_scene=SCENA,
            )

    def test_riuscito_o_no_e_colpo_per_colpo_non_stanno_insieme(self, db_session):
        with pytest.raises(ValidationError):
            ChallengeAuthoringService.create(
                _bozza(pass_fail_only=True),
                image_path="t.png",
                created_by_id=None,
                diagram_scene=SCENA,
            )

    def test_col_totale_i_colpi_non_si_tengono(self, db_session):
        c = ChallengeAuthoringService.create(
            _bozza(recording_mode=RecordingMode.TOTAL.value, max_score=10),
            image_path="t.png",
            created_by_id=None,
            diagram_scene=SCENA,
        )
        assert (c.recording_mode, c.shots_count, c.max_score) == ("total", None, 10)


def _esercizio_col_totale(db_session, *, con_prove: bool) -> Challenge:
    c = Challenge(
        title=f"Ferma {uuid.uuid4().hex[:5]}",
        description="Ferma la bianca nel cerchio",
        image_path="t.png",
        diagram_scene=SCENA,
        pass_fail_only=False,
        max_score=10,
        is_active=True,
    )
    db_session.add(c)
    db_session.flush()
    if con_prove:
        u = User(
            username=f"u_{uuid.uuid4().hex[:8]}",
            email=f"u_{uuid.uuid4().hex[:8]}@test.com",
            role=UserRole.PLAYER.value,
        )
        u.set_password("test1234")
        db_session.add(u)
        db_session.flush()
        db_session.add(
            ChallengeAttempt(user_id=u.id, challenge_id=c.id, score=7, completed=True)
        )
        db_session.flush()
    return c


class TestModificare:
    def test_passare_a_colpo_per_colpo(self, db_session):
        c = _esercizio_col_totale(db_session, con_prove=False)
        ChallengeAuthoringService.update(
            c.id, _bozza(shots_count=10), acting_user_id=None
        )
        assert (c.recording_mode, c.shots_count, c.max_score) == ("shots", 10, 30)

    def test_con_delle_prove_cambia_il_senso_e_si_ferma(self, db_session):
        c = _esercizio_col_totale(db_session, con_prove=True)
        with pytest.raises(EvidenceDecisionRequired) as fermo:
            ChallengeAuthoringService.update(c.id, _bozza(), acting_user_id=None)
        assert MeaningChangeKind.RECORDING_MODE in {x.kind for x in fermo.value.changes}

    def test_cambiare_i_colpi_cambia_il_massimo(self, db_session):
        c = _esercizio_col_totale(db_session, con_prove=False)
        ChallengeAuthoringService.update(
            c.id, _bozza(shots_count=10), acting_user_id=None
        )
        cambi = ChallengeAuthoringService.meaning_changes(c, _bozza(shots_count=20))
        assert [x.kind for x in cambi] == [MeaningChangeKind.MAX_SCORE]
        assert (cambi[0].before, cambi[0].after) == ("30", "60")

    def test_la_foto_nuova_toglie_il_bersaglio_quindi_si_rifiuta(self, db_session):
        c = _esercizio_col_totale(db_session, con_prove=False)
        with pytest.raises(ValidationError):
            ChallengeAuthoringService.update(
                c.id, _bozza(), acting_user_id=None, image_path="nuova.jpg"
            )


class TestIlModulo:
    def test_la_terza_voce_arriva_nella_bozza(self):
        bozza = parse_challenge_draft(
            MultiDict(
                {
                    "description": "x",
                    "scoring_type": "shots",
                    "shots_count": "20",
                    "max_score": "99",  # residuo a schermo: non conta
                }
            )
        )
        assert (bozza.recording_mode, bozza.shots_count) == ("shots", 20)
        assert (bozza.pass_fail_only, bozza.max_score) == (False, None)

    def test_a_punteggio_resta_col_totale(self):
        bozza = parse_challenge_draft(
            MultiDict(
                {"description": "x", "scoring_type": "score", "shots_count": "20"}
            )
        )
        assert (bozza.recording_mode, bozza.shots_count) == ("total", None)

    def test_in_modifica_il_modulo_si_apre_sulla_voce_giusta(self, db_session):
        c = _esercizio_col_totale(db_session, con_prove=False)
        ChallengeAuthoringService.update(
            c.id, _bozza(shots_count=12), acting_user_id=None
        )
        bozza = draft_from_challenge(c)
        assert (bozza.recording_mode, bozza.shots_count) == ("shots", 12)
