"""Un tentativo di esercizio fra i turni registrato per sbaglio si toglie.

`SPECIFICHE.md`, «Cosa deve essere chiuso prima del turno successivo»
(2026-09-13): a gara in corso e finche' il turno dopo non e' partito — con la
strategia casuale per tutta la gara — il direttore toglie un tentativo. Esce
dalla classifica degli esercizi, i tentativi rimasti si rinumerano, e se era
l'unico tentativo del giocatore su quell'esercizio l'XP pagato torna indietro.

Fino a oggi il foglio diceva «un tentativo registrato non si toglie»: un tocco
sbagliato sul telefono restava in classifica per sempre.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.competition.gara_challenge import (
    GaraChallenge,
    GaraChallengeAttempt,
    GaraChallengeClassification,
)
from models.competition.gara_challenge_service import GaraChallengeService
from models.competition.models import Gara, Inscription
from models.exceptions import ConflictError, NotFoundError
from models.gamification.models import XPTransaction, XPTransactionType
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
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
    client.post(
        "/auth/login",
        data={"username": utente.username, "password": "test1234"},
        follow_redirects=True,
    )


def _scenario(db_session, *, strategia="amalfi", tentativi=3):
    """Gara in corso al turno 1 concluso, quattro iscritti, un esercizio."""
    direttore = _utente(db_session, "dir", UserRole.DIRECTOR.value)
    giocatori = [_utente(db_session, f"tt{i}") for i in range(4)]
    gara = Gara(
        number=1,
        name=f"Gara tentativi {uuid.uuid4().hex[:6]}",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        matchmaking_strategy=strategia,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        min_participants=4,
        director_id=direttore.id,
    )
    db_session.add(gara)
    db_session.commit()
    for u in giocatori:
        db_session.add(Inscription(user_id=u.id, gara_id=gara.id, is_waitlist=False))
    for a, b in ((giocatori[0], giocatori[1]), (giocatori[2], giocatori[3])):
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=a.id,
                player2_id=b.id,
                player1_score=5,
                player2_score=3,
                winner_id=a.id,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
    sfida = Challenge(
        description="Spot shot",
        image_path="/x.png",
        pass_fail_only=False,
        is_active=True,
        created_by_id=direttore.id,
    )
    db_session.add(sfida)
    db_session.commit()
    gc = GaraChallenge(
        gara_id=gara.id,
        challenge_id=sfida.id,
        round_number=1,
        max_attempts=tentativi,
        added_by_id=direttore.id,
    )
    db_session.add(gc)
    db_session.commit()
    return gara, direttore, giocatori, gc


def _tentativi(gc_id, user_id):
    db.session.expire_all()
    return (
        GaraChallengeAttempt.query.filter_by(gara_challenge_id=gc_id, user_id=user_id)
        .order_by(GaraChallengeAttempt.attempt_number)
        .all()
    )


def _xp_del_tentativo(user_id, attempt_id, gara_id):
    totale = 0
    for m in XPTransaction.query.filter_by(
        user_id=user_id, transaction_type=XPTransactionType.CHALLENGE_COMPLETION
    ).all():
        legami = json.loads(m.related_entities or "{}")
        if (
            legami.get("challenge_attempt_id") == attempt_id
            and legami.get("gara_id") == gara_id
        ):
            totale += m.xp_amount
    return totale


class TestIlServizio:
    def test_toglie_e_rinumera(self, db_session):
        gara, _dir, giocatori, gc = _scenario(db_session)
        anna = giocatori[0]
        for punti in (4, 9, 6):
            GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=punti)
        db_session.commit()
        secondo = _tentativi(gc.id, anna.id)[1]

        GaraChallengeService.remove_challenge_attempt(secondo.id)
        db_session.commit()

        rimasti = _tentativi(gc.id, anna.id)
        assert [(t.attempt_number, t.score) for t in rimasti] == [(1, 4), (2, 6)]

    def test_la_classifica_degli_esercizi_si_ricalcola(self, db_session):
        gara, _dir, giocatori, gc = _scenario(db_session)
        anna = giocatori[0]
        GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=4)
        GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=12)
        db_session.commit()
        sbagliato = _tentativi(gc.id, anna.id)[1]

        GaraChallengeService.remove_challenge_attempt(sbagliato.id)
        db_session.commit()

        db.session.expire_all()
        riga = GaraChallengeClassification.query.filter_by(
            gara_id=gara.id, user_id=anna.id
        ).one()
        assert riga.total_best_score == 4

    def test_l_unico_tentativo_tolto_restituisce_l_xp(self, db_session):
        gara, _dir, giocatori, gc = _scenario(db_session)
        anna = giocatori[0]
        GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=4)
        db_session.commit()
        (tentativo,) = _tentativi(gc.id, anna.id)
        pagato = _xp_del_tentativo(anna.id, tentativo.id, gara.id)
        assert (
            pagato > 0
        ), "il tentativo deve aver pagato XP, o il test non prova niente"

        GaraChallengeService.remove_challenge_attempt(tentativo.id)
        db_session.commit()

        assert _xp_del_tentativo(anna.id, tentativo.id, gara.id) == 0

    def test_se_resta_un_tentativo_l_xp_resta(self, db_session):
        gara, _dir, giocatori, gc = _scenario(db_session)
        anna = giocatori[0]
        GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=4)
        GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=7)
        db_session.commit()
        primo = _tentativi(gc.id, anna.id)[0]
        pagato = _xp_del_tentativo(anna.id, primo.id, gara.id)
        assert pagato > 0

        GaraChallengeService.remove_challenge_attempt(primo.id)
        db_session.commit()

        # L'esercizio l'ha fatto comunque: il drill resta pagato.
        assert _xp_del_tentativo(anna.id, primo.id, gara.id) == pagato

    def test_a_turno_dopo_partito_non_si_toglie(self, db_session):
        gara, _dir, giocatori, gc = _scenario(db_session)
        GaraChallengeService.record_challenge_attempt(gc.id, giocatori[0].id, score=4)
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=2,
                player1_id=giocatori[0].id,
                player2_id=giocatori[2].id,
                status=MatchStatus.PLAYING.value,
            )
        )
        db_session.commit()
        (tentativo,) = _tentativi(gc.id, giocatori[0].id)

        with pytest.raises(ConflictError):
            GaraChallengeService.remove_challenge_attempt(tentativo.id)
        db.session.rollback()
        assert len(_tentativi(gc.id, giocatori[0].id)) == 1

    def test_col_casuale_si_toglie_anche_a_turni_avanti(self, db_session):
        gara, _dir, giocatori, gc = _scenario(db_session, strategia="random")
        GaraChallengeService.record_challenge_attempt(gc.id, giocatori[0].id, score=4)
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=2,
                player1_id=giocatori[0].id,
                player2_id=giocatori[2].id,
                status=MatchStatus.PLAYING.value,
            )
        )
        db_session.commit()
        (tentativo,) = _tentativi(gc.id, giocatori[0].id)

        GaraChallengeService.remove_challenge_attempt(tentativo.id)
        db_session.commit()
        assert _tentativi(gc.id, giocatori[0].id) == []

    def test_a_gara_chiusa_non_si_toglie(self, db_session):
        gara, _dir, giocatori, gc = _scenario(db_session)
        GaraChallengeService.record_challenge_attempt(gc.id, giocatori[0].id, score=4)
        gara.status = GaraStatus.COMPLETED.value
        db_session.commit()
        (tentativo,) = _tentativi(gc.id, giocatori[0].id)

        with pytest.raises(ConflictError):
            GaraChallengeService.remove_challenge_attempt(tentativo.id)
        db.session.rollback()

    def test_un_tentativo_che_non_esiste(self, db_session):
        with pytest.raises(NotFoundError):
            GaraChallengeService.remove_challenge_attempt(987654)


class TestLaRoute:
    def test_il_direttore_toglie_il_tentativo(self, client, db_session):
        gara, direttore, giocatori, gc = _scenario(db_session)
        GaraChallengeService.record_challenge_attempt(gc.id, giocatori[0].id, score=4)
        db_session.commit()
        (tentativo,) = _tentativi(gc.id, giocatori[0].id)
        _login(client, direttore)

        risposta = client.post(f"/admin/match/challenge_attempt/{tentativo.id}/togli")
        assert risposta.status_code == 200
        assert risposta.get_json()["success"] is True
        assert _tentativi(gc.id, giocatori[0].id) == []

    def test_chi_non_dirige_la_gara_no(self, client, db_session):
        gara, _dir, giocatori, gc = _scenario(db_session)
        GaraChallengeService.record_challenge_attempt(gc.id, giocatori[0].id, score=4)
        db_session.commit()
        (tentativo,) = _tentativi(gc.id, giocatori[0].id)
        _login(client, _utente(db_session, "altro", UserRole.DIRECTOR.value))

        risposta = client.post(f"/admin/match/challenge_attempt/{tentativo.id}/togli")
        assert risposta.status_code == 403
        assert len(_tentativi(gc.id, giocatori[0].id)) == 1

    def test_il_rifiuto_del_dominio_e_un_409(self, client, db_session):
        gara, direttore, giocatori, gc = _scenario(db_session)
        GaraChallengeService.record_challenge_attempt(gc.id, giocatori[0].id, score=4)
        gara.status = GaraStatus.COMPLETED.value
        db_session.commit()
        (tentativo,) = _tentativi(gc.id, giocatori[0].id)
        _login(client, direttore)

        risposta = client.post(f"/admin/match/challenge_attempt/{tentativo.id}/togli")
        assert risposta.status_code == 409
        assert risposta.get_json()["success"] is False

    def test_la_route_e_nella_matrice_dei_ruoli(self):
        from utils.feature_flags import ENDPOINT_ROLES

        assert ENDPOINT_ROLES["admin.match.remove_challenge_attempt"] == {"director"}


class TestLaPagina:
    def test_la_riga_porta_i_tentativi_da_togliere(self, client, db_session):
        gara, direttore, giocatori, gc = _scenario(db_session, tentativi=1)
        GaraChallengeService.record_challenge_attempt(gc.id, giocatori[0].id, score=4)
        db_session.commit()
        (tentativo,) = _tentativi(gc.id, giocatori[0].id)
        _login(client, direttore)

        html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        # Tentativi finiti: prima la riga non si toccava piu', ora apre il
        # foglio per togliere.
        assert f'"id": {tentativo.id}' in html
        assert "Togli il tentativo" in html
        assert "Un tentativo registrato non si toglie" not in html


def _xp_della_gara(user_id, gara_id):
    """L'XP degli esercizi di questa gara per il giocatore, al netto."""
    totale = 0
    for m in XPTransaction.query.filter_by(
        user_id=user_id, transaction_type=XPTransactionType.CHALLENGE_COMPLETION
    ).all():
        if json.loads(m.related_entities or "{}").get("gara_id") == gara_id:
            totale += m.xp_amount
    return totale


class TestL_XPInOgniOrdine:
    """L'XP dell'esercizio segue i tentativi rimasti, in qualunque ordine si
    tolgano: finche' ne resta uno l'esercizio e' fatto e l'XP resta; senza
    tentativi torna indietro. Anche togliendo prima quello che l'aveva pagato
    e poi l'ultimo — il caso che la prima stesura sbagliava."""

    @pytest.mark.parametrize(
        "ordine",
        [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)],
    )
    def test_ogni_ordine_di_rimozione(self, db_session, ordine):
        gara, _dir, giocatori, gc = _scenario(db_session)
        anna = giocatori[0]
        for punti in (4, 9, 6):
            GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=punti)
        db_session.commit()
        tariffa = _xp_della_gara(anna.id, gara.id)
        assert tariffa > 0, "il primo tentativo deve pagare, o il test non prova niente"
        ids = [t.id for t in _tentativi(gc.id, anna.id)]

        for passo, indice in enumerate(ordine, start=1):
            GaraChallengeService.remove_challenge_attempt(ids[indice])
            db_session.commit()
            rimasti = len(ids) - passo
            atteso = tariffa if rimasti else 0
            assert _xp_della_gara(anna.id, gara.id) == atteso, (ordine, passo)

    def test_tolti_tutti_e_registrato_di_nuovo_paga_una_volta(self, db_session):
        gara, _dir, giocatori, gc = _scenario(db_session)
        anna = giocatori[0]
        GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=4)
        GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=5)
        db_session.commit()
        tariffa = _xp_della_gara(anna.id, gara.id)
        for t in _tentativi(gc.id, anna.id):
            GaraChallengeService.remove_challenge_attempt(t.id)
            db_session.commit()
        assert _xp_della_gara(anna.id, gara.id) == 0

        GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=7)
        GaraChallengeService.record_challenge_attempt(gc.id, anna.id, score=8)
        db_session.commit()
        assert _xp_della_gara(anna.id, gara.id) == tariffa
