"""Una prova si chiude una volta sola, e dalla sua porta (2026-11-10).

Il difetto, trovato da una revisione il 2026-11-10: la chiusura di una prova
non guardava in che stato fosse la prova né di che genere fosse.

* `ChallengeService.complete_challenge_attempt` non controllava che la prova
  fosse ancora aperta, non confrontava il punteggio col massimo dell'esercizio
  e non guardava come l'esercizio si registra. Chiudere di nuovo una prova già
  chiusa ne riscriveva il punteggio — anche oltre il massimo — e ripagava l'XP
  a ogni giro.
* La route generica `challenge.complete_attempt` accettava qualunque prova di
  chi la chiamava: quella a colpi ancora aperta (ADR-066: il punteggio discende
  dai colpi), quella nata in una scheda (ADR-072: la scrive la seduta) e quella
  giocata al posto della X, che ha un limite suo (SPECIFICHE.md, «Strategia di
  abbinamento»).
* `challenge.start_attempt` prendeva gara e turno dal modulo: il legame fra una
  prova e una gara nasceva senza il controllo «ha davvero la X in quel turno»,
  che vive in `create_x_replacement_attempt`.

Qui si percorrono le strade via HTTP, come le percorre un giocatore, e si
verifica anche che quelle legittime continuino a funzionare.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.recording import RecordingMode
from models.challenge.services import ChallengeService
from models.competition.gara_bye_challenge import GaraByeChallenge
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.exceptions import ConflictError, ValidationError
from models.gamification.models import XPTransaction, XPTransactionType
from models.match.models import Match
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(db_session, prefisso, ruolo=UserRole.PLAYER.value):
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}",
        email=f"{prefisso}_{s}@test.com",
        role=ruolo,
        onboarding_completed=True,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, utente):
    from flask import g

    g.pop("_login_user", None)
    with client.session_transaction() as sess:
        sess["_user_id"] = utente.get_id()
        sess["_fresh"] = True


def _esercizio(db_session, autore, **campi):
    campi.setdefault("max_score", 10)
    esercizio = Challenge(
        title=f"E {uuid.uuid4().hex[:6]}",
        description="d",
        image_path="x.png",
        created_by_id=autore.id,
        is_active=True,
        **campi,
    )
    db_session.add(esercizio)
    db_session.commit()
    return esercizio


def _xp_delle_prove(user_id):
    return [
        t.xp_amount
        for t in XPTransaction.query.filter_by(
            user_id=user_id,
            transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
        ).all()
    ]


@pytest.fixture
def giocatore(db_session):
    return _utente(db_session, "gioc")


@pytest.fixture
def gara_con_x(db_session):
    """Gara Amalfi a cinque: a ogni turno uno gioca la prova al posto della X."""
    direttore = _utente(db_session, "dir", UserRole.DIRECTOR.value)
    giocatori = [_utente(db_session, f"p{i}") for i in range(5)]
    esercizio = _esercizio(db_session, direttore, max_score=None)

    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Gara X {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        location="Test",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=8,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=direttore.id,
        matchmaking_strategy="amalfi",
        first_round_policy="random",
        odd_number_policy="bye_with_challenge",
        anti_rematch_enabled=True,
        x_challenge_id=esercizio.id,
    )
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(days=5)
    )
    for g in giocatori:
        InscriptionService.inscribe_user(g.id, gara.id)
    db_session.commit()
    RoundService.start_first_round(gara.id)
    db_session.commit()

    match_x = Match.query.filter_by(gara_id=gara.id, round_number=1, is_bye=True).one()
    di_turno = db.session.get(User, match_x.player1_id)
    return {
        "gara": gara,
        "giocatore": di_turno,
        "altro": next(g for g in giocatori if g.id != di_turno.id),
    }


class TestUnaProvaChiusaNonSiRichiude:
    def test_richiudere_non_riscrive_il_punteggio_e_non_ripaga(
        self, client, db_session, giocatore
    ):
        esercizio = _esercizio(db_session, giocatore)
        prova = ChallengeService.record_attempt(
            user_id=giocatore.id, challenge_id=esercizio.id, score=5
        )
        prova_id = prova.id
        pagato = _xp_delle_prove(giocatore.id)
        _login(client, giocatore)

        for _giro in range(3):
            risposta = client.post(
                f"/challenges/attempt/{prova_id}/complete", json={"score": 9}
            )
            assert risposta.status_code == 409
            assert risposta.get_json()["success"] is False

        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, prova_id).score == 5
        assert _xp_delle_prove(giocatore.id) == pagato

    def test_il_servizio_rifiuta_la_seconda_chiusura(self, db_session, giocatore):
        esercizio = _esercizio(db_session, giocatore)
        prova = ChallengeService.start_challenge_attempt(
            user_id=giocatore.id, challenge_id=esercizio.id
        )
        ChallengeService.complete_challenge_attempt(prova.id, score=4)
        with pytest.raises(ConflictError):
            ChallengeService.complete_challenge_attempt(prova.id, score=7)
        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, prova.id).score == 4

    def test_il_massimo_vale_anche_alla_chiusura(self, client, db_session, giocatore):
        esercizio = _esercizio(db_session, giocatore, max_score=10)
        _login(client, giocatore)
        prova_id = client.post(
            f"/challenges/{esercizio.id}/attempt", json={}
        ).get_json()["attempt_id"]

        risposta = client.post(
            f"/challenges/attempt/{prova_id}/complete", json={"score": 999}
        )

        assert risposta.status_code == 422
        db_session.expire_all()
        prova = db_session.get(ChallengeAttempt, prova_id)
        assert prova.completed is False
        assert prova.score is None
        assert _xp_delle_prove(giocatore.id) == []

    def test_il_servizio_valida_il_massimo(self, db_session, giocatore):
        esercizio = _esercizio(db_session, giocatore, max_score=10)
        prova = ChallengeService.start_challenge_attempt(
            user_id=giocatore.id, challenge_id=esercizio.id
        )
        with pytest.raises(ValidationError):
            ChallengeService.complete_challenge_attempt(prova.id, score=11)

    def test_aprire_e_chiudere_una_volta_funziona_ancora(
        self, client, db_session, giocatore
    ):
        esercizio = _esercizio(db_session, giocatore, max_score=10)
        _login(client, giocatore)
        prova_id = client.post(
            f"/challenges/{esercizio.id}/attempt", json={}
        ).get_json()["attempt_id"]

        risposta = client.post(
            f"/challenges/attempt/{prova_id}/complete", json={"score": 7}
        )

        assert risposta.status_code == 200
        assert risposta.get_json()["final_score"] == 7
        db_session.expire_all()
        prova = db_session.get(ChallengeAttempt, prova_id)
        assert prova.completed is True and prova.score == 7
        assert len(_xp_delle_prove(giocatore.id)) == 1


class TestLaChiusuraGenericaNonEUnaPortaSulRetro:
    def test_una_prova_a_colpi_non_si_chiude_col_totale(
        self, client, db_session, giocatore
    ):
        """ADR-066: il punteggio di una prova a colpi discende dai colpi."""
        esercizio = _esercizio(
            db_session,
            giocatore,
            max_score=30,
            recording_mode=RecordingMode.SHOTS.value,
            shots_count=10,
        )
        aperta = ChallengeAttempt(user_id=giocatore.id, challenge_id=esercizio.id)
        db_session.add(aperta)
        db_session.commit()
        _login(client, giocatore)

        risposta = client.post(
            f"/challenges/attempt/{aperta.id}/complete", json={"score": 30}
        )

        assert risposta.status_code == 422
        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, aperta.id).completed is False
        assert _xp_delle_prove(giocatore.id) == []

    def test_una_prova_nata_in_scheda_non_si_riscrive(
        self, client, db_session, giocatore
    ):
        """ADR-072: le prove di una casella le scrive la seduta."""
        from models.training_sheet import TrainingSessionService
        from models.training_sheet.models import TrainingEntry, TrainingSheetItem
        from models.training_sheet.services import TrainingSheetService

        esercizio = _esercizio(
            db_session, giocatore, pass_fail_only=True, max_score=None
        )
        scheda = TrainingSheetService.create_sheet(giocatore, "Scheda")
        voce = TrainingSheetItem(
            sheet_id=scheda.id,
            challenge_id=esercizio.id,
            position=1,
            measure="made",
            amount=5,
        )
        db_session.add(voce)
        db_session.commit()
        seduta = TrainingSessionService.start(scheda.id, giocatore)
        TrainingSessionService.record(seduta.id, voce.id, giocatore, value=2)
        casella = TrainingEntry.query.filter_by(session_id=seduta.id).one()
        fallita = next(p for p in casella.attempts if not p.passed)
        fallita_id = fallita.id
        # Anche se per qualche ragione la prova risultasse ancora aperta, la
        # porta generica non è la sua.
        fallita.completed = False
        db_session.commit()
        _login(client, giocatore)

        risposta = client.post(
            f"/challenges/attempt/{fallita_id}/complete", json={"passed": True}
        )

        assert risposta.status_code == 409
        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, fallita_id).passed is False

    def test_la_prova_della_x_non_passa_dalla_chiusura_generica(
        self, client, db_session, gara_con_x
    ):
        gara, di_turno = gara_con_x["gara"], gara_con_x["giocatore"]
        _login(client, di_turno)
        client.post(f"/challenges/x-replacement/{gara.id}/1", json={})
        prova = ChallengeAttempt.query.filter_by(user_id=di_turno.id).one()

        risposta = client.post(
            f"/challenges/attempt/{prova.id}/complete", json={"score": 999}
        )

        assert risposta.status_code == 409
        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, prova.id).completed is False


class TestLaProvaDellaX:
    def test_si_chiude_una_volta_e_nel_suo_limite(self, client, db_session, gara_con_x):
        gara, di_turno = gara_con_x["gara"], gara_con_x["giocatore"]
        _login(client, di_turno)
        client.post(f"/challenges/x-replacement/{gara.id}/1", json={})
        prova = ChallengeAttempt.query.filter_by(user_id=di_turno.id).one()
        indirizzo = f"/challenges/x-replacement/{prova.id}/complete"

        fuori_scala = client.post(indirizzo, json={"score": 999})
        assert fuori_scala.status_code == 422

        buona = client.post(indirizzo, json={"score": 4})
        assert buona.status_code == 200
        pagato = _xp_delle_prove(di_turno.id)

        di_nuovo = client.post(indirizzo, json={"score": 5})
        assert di_nuovo.status_code == 409

        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, prova.id).score == 4
        assert _xp_delle_prove(di_turno.id) == pagato

    def test_il_direttore_corregge_ancora_il_punteggio_dichiarato(
        self, db_session, gara_con_x
    ):
        """La correzione del direttore non è una seconda chiusura del giocatore."""
        gara, di_turno = gara_con_x["gara"], gara_con_x["giocatore"]
        prova = ChallengeService.create_x_replacement_attempt(
            user_id=di_turno.id, gara_id=gara.id, round_number=1
        )
        ChallengeService.complete_x_replacement_attempt(prova.id, score=4)

        ChallengeService.validate_x_replacement(
            gara_id=gara.id,
            round_number=1,
            user_id=di_turno.id,
            actor_id=gara.director_id,
            score=3,
        )

        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, prova.id).score == 3


class TestAvviareUnaProvaNonLaLegaAUnaGara:
    def test_gara_e_turno_nel_modulo_non_creano_il_legame(
        self, client, db_session, giocatore
    ):
        direttore = _utente(db_session, "dir", UserRole.DIRECTOR.value)
        esercizio = _esercizio(db_session, direttore, max_score=None)
        gara = Gara(
            name="G",
            number=1,
            discipline="8_ball",
            date=date.today(),
            director_id=direttore.id,
            distance=5,
        )
        db_session.add(gara)
        db_session.commit()
        _login(client, giocatore)

        risposta = client.post(
            f"/challenges/{esercizio.id}/attempt",
            json={"gara_id": gara.id, "round_number": 1},
        )

        assert risposta.status_code == 200
        prova = db_session.get(ChallengeAttempt, risposta.get_json()["attempt_id"])
        assert prova.gara_id is None and prova.round_number is None
        assert GaraByeChallenge.query.count() == 0
        # E senza legame la porta della X resta chiusa.
        chiusura = client.post(
            f"/challenges/x-replacement/{prova.id}/complete", json={"score": 999}
        )
        assert chiusura.status_code == 403

    def test_chi_non_ha_la_x_non_apre_la_prova_della_x(
        self, client, db_session, gara_con_x
    ):
        gara, altro = gara_con_x["gara"], gara_con_x["altro"]
        _login(client, altro)

        risposta = client.post(f"/challenges/x-replacement/{gara.id}/1", json={})

        assert risposta.status_code == 400
        assert risposta.get_json()["success"] is False
        assert GaraByeChallenge.query.filter_by(user_id=altro.id).count() == 0
