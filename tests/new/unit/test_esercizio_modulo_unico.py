"""Il modulo unico dell'esercizio: crea, modifica, e la copia quando ci sono prove.

La issue #252 in una frase: correggere un esercizio che ha già dei risultati
riscrive il passato. Questo file fissa **quando** il salvataggio si ferma a
chiedere, e che cosa succede con ciascuna delle due risposte.
"""

from __future__ import annotations

import uuid

import pytest

from models.challenge.authoring import (
    ChallengeAuthoringService,
    ChallengeDraft,
    EvidenceDecisionRequired,
    MeaningChangeKind,
    OnEvidence,
)
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.services import ChallengeService
from models.challenge.vocabulary import Abilita, Gesto
from models.exceptions import ValidationError
from models.user.models import User
from models.user.role_enum import UserRole

ISTRUZIONI = "Dieci tiri dalla stessa posizione"


def _utente(db_session, ruolo=UserRole.PLAYER.value):
    u = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@test.com",
        role=ruolo,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _bozza(**campi) -> ChallengeDraft:
    base = dict(title="Spot Shot Rally", description=ISTRUZIONI, max_score=10)
    base.update(campi)
    return ChallengeDraft(**base)


def _creato(db_session, **campi) -> Challenge:
    autore = _utente(db_session, UserRole.DIRECTOR.value)
    return ChallengeAuthoringService.create(
        _bozza(**campi), image_path="uploads/challenges/a.png", created_by_id=autore.id
    )


class TestCreare:
    def test_nasce_col_suo_profilo(self, db_session):
        c = _creato(
            db_session,
            abilita=["tiro", "posizione"],
            gesti=["draw"],
            declared_level=1,
            variants=[{"label": "dx"}, {"label": "sx"}],
        )
        c = db_session.get(Challenge, c.id)
        assert c.abilita == [Abilita.TIRO, Abilita.POSIZIONE]
        assert c.gesti == [Gesto.DRAW]
        assert c.declared_level == 1
        assert [v.label for v in c.variants] == ["dx", "sx"]
        assert c.max_score == 10

    def test_senza_istruzioni_non_nasce(self, db_session):
        with pytest.raises(ValidationError):
            _creato(db_session, description="   ")

    def test_un_profilo_sbagliato_non_lascia_un_esercizio_a_meta(self, db_session):
        prima = db_session.query(Challenge).count()
        with pytest.raises(ValidationError):
            _creato(db_session, abilita=["tiro", "posizione", "sponde", "difesa"])
        assert db_session.query(Challenge).count() == prima


class TestCheCosaCambiaIlSenso:
    def test_il_titolo_e_il_profilo_no(self, db_session):
        c = _creato(db_session)
        bozza = _bozza(title="Un altro nome", abilita=["difesa"], declared_level=4)
        assert ChallengeAuthoringService.meaning_changes(c, bozza) == []

    def test_il_massimo_si(self, db_session):
        c = _creato(db_session)
        (cambio,) = ChallengeAuthoringService.meaning_changes(c, _bozza(max_score=15))
        assert cambio.kind == MeaningChangeKind.MAX_SCORE
        assert (cambio.before, cambio.after) == ("10", "15")

    def test_il_tipo_si_e_assorbe_il_massimo(self, db_session):
        """Passando a superato/non superato il massimo sparisce per forza:
        dirlo due volte sarebbe rumore."""
        c = _creato(db_session)
        cambi = ChallengeAuthoringService.meaning_changes(
            c, _bozza(pass_fail_only=True, max_score=None)
        )
        assert [x.kind for x in cambi] == [MeaningChangeKind.SCORING_TYPE]

    def test_le_istruzioni_si_ma_gli_spazi_no(self, db_session):
        c = _creato(db_session)
        assert not ChallengeAuthoringService.meaning_changes(
            c, _bozza(description=f"  {ISTRUZIONI}\n")
        )
        (cambio,) = ChallengeAuthoringService.meaning_changes(
            c, _bozza(description="Quindici tiri")
        )
        assert cambio.kind == MeaningChangeKind.INSTRUCTIONS


class TestModificare:
    def test_senza_prove_si_modifica_sul_posto(self, db_session):
        c = _creato(db_session)
        esito = ChallengeAuthoringService.update(
            c.id, _bozza(max_score=15, abilita=["tiro"]), acting_user_id=None
        )
        assert not esito.copied
        c = db_session.get(Challenge, c.id)
        assert c.max_score == 15
        assert c.abilita == [Abilita.TIRO]

    def test_con_prove_il_refuso_nel_titolo_passa_liscio(self, db_session):
        c = _creato(db_session)
        ChallengeService.record_attempt(_utente(db_session).id, c.id, score=7)
        esito = ChallengeAuthoringService.update(
            c.id, _bozza(title="Spot Shot Rally!"), acting_user_id=None
        )
        assert not esito.copied
        assert db_session.get(Challenge, c.id).title == "Spot Shot Rally!"

    def test_con_prove_cambiare_il_massimo_si_ferma_a_chiedere(self, db_session):
        c = _creato(db_session)
        a, b = _utente(db_session), _utente(db_session)
        ChallengeService.record_attempt(a.id, c.id, score=7)
        ChallengeService.record_attempt(a.id, c.id, score=8)
        ChallengeService.record_attempt(b.id, c.id, score=3)

        with pytest.raises(EvidenceDecisionRequired) as fermo:
            ChallengeAuthoringService.update(
                c.id, _bozza(max_score=15), acting_user_id=None
            )
        assert fermo.value.evidence.attempts == 3
        assert fermo.value.evidence.players == 2
        assert [x.kind for x in fermo.value.changes] == [MeaningChangeKind.MAX_SCORE]

    def test_la_risposta_copia_lascia_intatto_l_originale(self, db_session):
        c = _creato(db_session, abilita=["tiro"], variants=[{"label": "dx"}])
        chi = _utente(db_session, UserRole.DIRECTOR.value)
        ChallengeService.record_attempt(_utente(db_session).id, c.id, score=7)
        originale = db_session.get(Challenge, c.id)
        variante = originale.variants[0]

        esito = ChallengeAuthoringService.update(
            c.id,
            _bozza(
                max_score=15,
                abilita=["difesa"],
                variants=[{"id": variante.id, "label": "dx"}],
            ),
            acting_user_id=chi.id,
            copy_image_path="uploads/challenges/copia.png",
            on_evidence=OnEvidence.COPY,
        )

        assert esito.copied
        copia = esito.challenge
        assert copia.id != c.id
        assert copia.created_by_id == chi.id
        assert copia.max_score == 15
        assert copia.abilita == [Abilita.DIFESA]
        assert copia.image_path == "uploads/challenges/copia.png"
        # le varianti della copia sono righe sue
        assert [v.label for v in copia.variants] == ["dx"]
        assert copia.variants[0].id != variante.id
        assert (
            db_session.query(ChallengeAttempt).filter_by(challenge_id=copia.id).count()
            == 0
        )

        originale = db_session.get(Challenge, c.id)
        assert originale.max_score == 10
        assert originale.abilita == [Abilita.TIRO]
        assert originale.image_path == "uploads/challenges/a.png"

    def test_la_risposta_modifica_comunque_scrive_qui(self, db_session):
        c = _creato(db_session)
        ChallengeService.record_attempt(_utente(db_session).id, c.id, score=7)
        esito = ChallengeAuthoringService.update(
            c.id,
            _bozza(max_score=15),
            acting_user_id=None,
            on_evidence=OnEvidence.OVERWRITE,
        )
        assert not esito.copied
        assert db_session.get(Challenge, c.id).max_score == 15

    def test_una_decisione_sconosciuta_vale_chiedi(self):
        assert OnEvidence.parse("boh") is OnEvidence.ASK
        assert OnEvidence.parse(None) is OnEvidence.ASK
        assert OnEvidence.parse("COPY") is OnEvidence.COPY

    def test_togliere_il_massimo(self, db_session):
        c = _creato(db_session)
        ChallengeAuthoringService.update(
            c.id, _bozza(max_score=None), acting_user_id=None
        )
        assert db_session.get(Challenge, c.id).max_score is None

    def test_una_foto_nuova_spegne_il_disegno_di_prima(self, db_session):
        c = _creato(db_session)
        c.diagram_scene = '{"v": 1, "items": []}'
        db_session.flush()
        ChallengeAuthoringService.update(
            c.id, _bozza(), acting_user_id=None, image_path="uploads/challenges/f.jpg"
        )
        c = db_session.get(Challenge, c.id)
        assert c.diagram_scene is None
        assert c.image_path == "uploads/challenges/f.jpg"
