"""La difficoltà misurata dai risultati di chi ha provato (#174).

Il livello dichiarato è un'opinione: questa la affianca, e non la sostituisce.
Le tre regole che rendono il numero dicibile, e che questo file difende:

* **una osservazione per giocatore**, non per prova — altrimenti la difficoltà
  diventa «quanto è bravo il più assiduo»;
* **sotto le soglie non si dice niente**, perché una stima falsa la si crede;
* **l'Elo entra come banda** e non come correzione, e quando non c'è resta la
  media di tutti — che è meglio di niente.

In sviluppo l'Elo è vuoto (il seed non fa scattare il motore di rating), quindi
i test della banda si costruiscono i propri rating.
"""

from __future__ import annotations

import uuid

import pytest

from models.challenge.difficulty import (
    BANDA_ELO,
    MIN_GIOCATORI,
    MIN_NELLA_BANDA,
    expected_for,
    livello_da_quota,
    measure,
    measure_many,
    peers,
)
from models.challenge.models import Challenge, ChallengeAttempt
from models.rating.models import PlayerRating, RatingSystem
from models.user.models import User
from models.user.role_enum import UserRole


# ── allestimento ────────────────────────────────────────────────────────────
def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"df_{uid}", email=f"df_{uid}@test.local", role=UserRole.PLAYER.value
    )
    user.set_password("p")
    db_session.add(user)
    db_session.flush()
    return user


def _challenge(db_session, titolo, *, max_score=10, pass_fail=False, livello=None):
    challenge = Challenge(
        title=titolo,
        description=f"{titolo}: istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=pass_fail,
        max_score=max_score,
        declared_level=livello,
    )
    db_session.add(challenge)
    db_session.flush()
    return challenge


def _prova(db_session, user, challenge, *, score=None, passed=None):
    db_session.add(
        ChallengeAttempt(
            challenge_id=challenge.id,
            user_id=user.id,
            score=score,
            passed=passed,
            completed=True,
        )
    )
    db_session.flush()


def _elo(db_session, user, valore):
    db_session.add(
        PlayerRating(
            user_id=user.id,
            rating_system=RatingSystem.ELO,
            rating_value=float(valore),
            robustness=20,
        )
    )
    db_session.flush()


def _tanti(db_session, challenge, punteggi):
    """Un giocatore per punteggio. Restituisce i giocatori, in ordine."""
    giocatori = []
    for punteggio in punteggi:
        user = _user(db_session)
        _prova(db_session, user, challenge, score=punteggio)
        giocatori.append(user)
    return giocatori


# ── una osservazione per giocatore ──────────────────────────────────────────
def test_chi_si_allena_venti_volte_non_pesa_venti_volte(db_session):
    """Altrimenti la difficoltà diventa «quanto è bravo il più assiduo»."""
    challenge = _challenge(db_session, "Spot shot", max_score=10)
    assiduo = _user(db_session)
    for _volta in range(20):
        _prova(db_session, assiduo, challenge, score=10)
    for altro in _tanti(db_session, challenge, [2, 2, 2, 2]):
        assert altro is not None

    stima = measure(challenge)
    assert stima.players == 5
    assert stima.attempts == 24
    # Media per giocatore: (100 + 20·4) / 5 = 36, non il 90 che darebbero le prove.
    assert stima.quota == 36


def test_la_media_di_un_giocatore_e_la_media_delle_sue_prove(db_session):
    challenge = _challenge(db_session, "Media", max_score=10)
    tizio = _user(db_session)
    _prova(db_session, tizio, challenge, score=2)
    _prova(db_session, tizio, challenge, score=8)
    _tanti(db_session, challenge, [5, 5])

    assert measure(challenge).quota == 50


# ── sotto le soglie non si dice niente ──────────────────────────────────────
def test_con_pochi_giocatori_non_ce_una_stima(db_session):
    challenge = _challenge(db_session, "Poco provato", max_score=10)
    _tanti(db_session, challenge, [8, 8])

    stima = measure(challenge)
    assert stima.players == 2
    assert not stima.has_estimate
    assert stima.level is None
    assert stima.sentence == ""


def test_con_pochi_tiri_non_ce_una_stima(db_session):
    """Tre giocatori con una prova a testa sono tre tiri."""
    challenge = _challenge(db_session, "Tre tiri", max_score=10)
    _tanti(db_session, challenge, [8, 8, 8])

    stima = measure(challenge)
    assert stima.players == MIN_GIOCATORI
    assert stima.attempts == 3
    assert not stima.has_estimate


def test_un_esercizio_mai_provato_non_ha_stima(db_session):
    challenge = _challenge(db_session, "Nuovo", max_score=10)

    stima = measure(challenge)
    assert stima.players == 0
    assert stima.quota is None
    assert not stima.has_estimate


def test_un_esercizio_senza_tetto_dichiarato_non_ha_stima(db_session):
    """Senza massimo non c'è una quota: la stessa regola dell'andamento."""
    challenge = _challenge(db_session, "Senza tetto", max_score=None)
    _tanti(db_session, challenge, [40, 30, 50, 20, 60])

    assert not measure(challenge).has_estimate


# ── il livello, e il confronto col dichiarato ───────────────────────────────
@pytest.mark.parametrize(
    "quota, livello", [(95, 1), (80, 1), (79, 2), (65, 2), (50, 3), (40, 4), (10, 5)]
)
def test_la_quota_diventa_un_livello(quota, livello):
    assert livello_da_quota(quota) == livello


def test_quando_i_due_livelli_divergono_lo_dice(db_session):
    challenge = _challenge(db_session, "Sembra facile", max_score=10, livello=1)
    _tanti(db_session, challenge, [4, 4, 4, 4, 4])

    stima = measure(challenge)
    assert stima.level == 4
    assert stima.disagrees and stima.harder
    assert "più difficile" in stima.sentence


def test_quando_coincidono_non_dice_niente(db_session):
    challenge = _challenge(db_session, "Come dichiarato", max_score=10, livello=4)
    _tanti(db_session, challenge, [4, 4, 4, 4, 4])

    stima = measure(challenge)
    assert stima.level == 4
    assert not stima.disagrees
    assert stima.sentence == ""


def test_senza_livello_dichiarato_non_ce_un_confronto(db_session):
    challenge = _challenge(db_session, "Senza livello", max_score=10, livello=None)
    _tanti(db_session, challenge, [4, 4, 4, 4, 4])

    stima = measure(challenge)
    assert stima.level == 4
    assert not stima.disagrees
    assert stima.sentence == ""


def test_riuscito_o_no_vale_tutto_o_niente(db_session):
    challenge = _challenge(db_session, "Netto", max_score=None, pass_fail=True)
    for esito in (True, True, False, False, False):
        _prova(db_session, _user(db_session), challenge, passed=esito)

    assert measure(challenge).quota == 40


# ── «Quelli come te» ────────────────────────────────────────────────────────
def test_la_banda_e_la_media_di_chi_ha_un_elo_simile(db_session):
    challenge = _challenge(db_session, "Con banda", max_score=10)
    forti = _tanti(db_session, challenge, [9, 9, 9])
    for user in forti:
        _elo(db_session, user, 1800)
    simili = _tanti(db_session, challenge, [4, 5, 6])
    for user in simili:
        _elo(db_session, user, 1500)

    chi_guarda = _user(db_session)
    _elo(db_session, chi_guarda, 1500)

    banda = peers(challenge, chi_guarda.id)
    assert banda is not None
    assert banda.players == MIN_NELLA_BANDA
    assert banda.quota == 50, "la media dei tre simili, non quella di tutti e sei"
    assert banda.low == 1500 - BANDA_ELO and banda.high == 1500 + BANDA_ELO


def test_senza_elo_di_chi_guarda_non_ce_una_banda(db_session):
    """È il caso normale: la maggior parte di chi si allena non ha un Elo."""
    challenge = _challenge(db_session, "Senza elo", max_score=10)
    for user in _tanti(db_session, challenge, [4, 5, 6]):
        _elo(db_session, user, 1500)

    assert peers(challenge, _user(db_session).id) is None


def test_una_banda_con_troppo_pochi_dentro_non_si_dice(db_session):
    challenge = _challenge(db_session, "Banda magra", max_score=10)
    vicini = _tanti(db_session, challenge, [4, 5])
    for user in vicini:
        _elo(db_session, user, 1500)
    lontani = _tanti(db_session, challenge, [9, 9, 9])
    for user in lontani:
        _elo(db_session, user, 2400)

    chi_guarda = _user(db_session)
    _elo(db_session, chi_guarda, 1500)
    assert peers(challenge, chi_guarda.id) is None


# ── il rovescio: cosa aspettarsi da questo giocatore (#175) ─────────────────
def test_la_stima_per_un_giocatore_usa_la_banda_quando_ce(db_session):
    challenge = _challenge(db_session, "Attesa", max_score=10)
    forti = _tanti(db_session, challenge, [10, 10, 10])
    for user in forti:
        _elo(db_session, user, 2000)
    simili = _tanti(db_session, challenge, [3, 3, 3])
    for user in simili:
        _elo(db_session, user, 1400)

    chi_guarda = _user(db_session)
    _elo(db_session, chi_guarda, 1400)
    assert expected_for(challenge, chi_guarda.id) == 30


def test_senza_banda_la_stima_e_quella_di_tutti(db_session):
    challenge = _challenge(db_session, "Attesa senza banda", max_score=10)
    _tanti(db_session, challenge, [6, 6, 6, 6, 6])

    assert expected_for(challenge, _user(db_session).id) == 60


def test_senza_niente_non_si_stima(db_session):
    challenge = _challenge(db_session, "Vuoto", max_score=10)
    assert expected_for(challenge, _user(db_session).id) is None


# ── il conto si fa in blocco ────────────────────────────────────────────────
def test_piu_esercizi_in_una_chiamata_sola(db_session):
    primo = _challenge(db_session, "Uno", max_score=10)
    secondo = _challenge(db_session, "Due", max_score=10)
    _tanti(db_session, primo, [8, 8, 8, 8, 8])
    _tanti(db_session, secondo, [2, 2, 2, 2, 2])

    stime = measure_many([primo, secondo])
    assert stime[primo.id].quota == 80
    assert stime[secondo.id].quota == 20
    assert measure_many([]) == {}
