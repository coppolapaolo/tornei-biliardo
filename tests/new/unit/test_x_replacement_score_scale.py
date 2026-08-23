"""La prova giocata al posto della X: quanto vale, e quanto può valere.

`SPECIFICHE.md` riga 65 — chi resta senza avversario può giocare una prova di
abilità invece di stare fermo, e ottiene «il match vinto e una differenza rack
pari al punteggio nella challenge», dove la prova dà «un punteggio da zero alla
massima differenza rack raggiungibile in quella gara».

Sono **due** regole, e per anni il codice ne ha applicata una terza. Storia
breve, perché spiega la forma di questo file:

* la versione originale usava lo score grezzo della prova come numero di rack.
  Una prova tarata 0-15 in una gara «al 5» metteva 15 triangoli in classifica:
  il triplo di quanti se ne possano vincere giocando;
* la code review del 2026-06-09 lo notò e assegnò al bye la distanza del turno,
  allineandolo ai bye normali. Difesa efficace, posto sbagliato: appiattire
  ogni prova sullo stesso valore rende la variante con challenge
  indistinguibile dalla X secca, cioè cancella la riga 65;
* dal 2026-08-23 il controllo sta dove il dato entra —
  `complete_x_replacement_attempt` rifiuta i punteggi fuori da [0, distanza del
  turno] — e il punteggio accettato arriva in classifica così com'è.

La differenza pratica: due giocatori che giocano la stessa prova con esiti
diversi ora si distinguono in classifica, e nessuno dei due può superare chi ha
vinto giocando.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.competition.models import Gara
from models.exceptions import ValidationError
from models.challenge.models import Challenge, ChallengeAttempt
from models.match.models import Match
from models.user.models import User
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus
from models.challenge.services import ChallengeService


def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(
        username=f"x_{uid}", email=f"x_{uid}@test.local", role=UserRole.PLAYER.value
    )
    u.set_password("p")
    db_session.add(u)
    db_session.flush()
    return u


def _gara(db_session, *, distance: int = 5) -> Gara:
    count = db_session.query(Gara).count()
    gara = Gara(
        name=f"X-repl gara {count + 1}",
        number=count + 1,
        date=date.today(),
        distance=distance,
        discipline="9_ball",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        rounds_count=3,
        current_round=1,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _bye(db_session, gara: Gara, player: User) -> Match:
    """La partita con la X, come la crea il sorteggio del turno: 0 triangoli."""
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=player.id,
        player2_id=None,
        is_bye=True,
        player1_score=0,
        player2_score=0,
        winner_id=player.id,
        status="completed",
    )
    db_session.add(match)
    db_session.flush()
    return match


def _attempt(db_session, gara: Gara, player: User, score: int) -> ChallengeAttempt:
    challenge = Challenge(
        description="Spot shot",
        image_path="x.png",
        pass_fail_only=False,
        created_by_id=player.id,
    )
    db_session.add(challenge)
    db_session.flush()

    attempt = ChallengeAttempt(
        challenge_id=challenge.id,
        user_id=player.id,
        gara_id=gara.id,
        round_number=1,
        score=score,
        completed=True,
    )
    db_session.add(attempt)
    db_session.flush()
    return attempt


@pytest.mark.unit
def test_il_punteggio_della_prova_diventa_la_differenza_triangoli(db_session):
    """`SPECIFICHE.md` riga 65: la differenza è **pari** al punteggio."""
    gara = _gara(db_session, distance=5)
    player = _user(db_session)
    _bye(db_session, gara, player)
    attempt = _attempt(db_session, gara, player, score=3)

    ChallengeService._create_x_replacement_match_result(attempt)

    match = Match.query.filter_by(
        gara_id=gara.id, round_number=1, player1_id=player.id, is_bye=True
    ).first()
    assert match is not None
    assert match.player1_score == 3
    assert match.player2_score == 0


@pytest.mark.unit
def test_due_prove_diverse_danno_classifiche_diverse(db_session):
    """La ragione per cui la riga 65 esiste: la prova deve discriminare.

    Con la versione precedente — distanza del turno a chiunque — questi due
    giocatori avrebbero avuto lo stesso identico punteggio, e giocare bene la
    prova non sarebbe servito a niente.
    """
    gara = _gara(db_session, distance=5)
    bravo, meno_bravo = _user(db_session), _user(db_session)
    for giocatore, punteggio in ((bravo, 4), (meno_bravo, 1)):
        _bye(db_session, gara, giocatore)
        ChallengeService._create_x_replacement_match_result(
            _attempt(db_session, gara, giocatore, score=punteggio)
        )

    punteggi = {
        match.player1_id: match.player1_score
        for match in Match.query.filter_by(gara_id=gara.id, is_bye=True).all()
    }
    assert punteggi[bravo.id] == 4
    assert punteggi[meno_bravo.id] == 1


@pytest.mark.unit
def test_un_punteggio_oltre_la_distanza_viene_rifiutato(db_session):
    """Il presidio che rende sicuro usare il punteggio grezzo.

    È il caso che la review del 2026-06-09 aveva davanti: prova tarata 0-15,
    gara «al 5». Prima veniva assorbito silenziosamente scartando il numero;
    ora viene rifiutato, perché quel 12 è un dato sbagliato e va corretto, non
    reinterpretato.
    """
    gara = _gara(db_session, distance=5)
    player = _user(db_session)
    _bye(db_session, gara, player)
    attempt = _attempt(db_session, gara, player, score=0)

    with pytest.raises(ValidationError):
        ChallengeService.complete_x_replacement_attempt(attempt.id, score=12)


@pytest.mark.unit
def test_un_punteggio_negativo_viene_rifiutato(db_session):
    """«Da zero», dice la riga 65: sotto lo zero non c'è scala."""
    gara = _gara(db_session, distance=5)
    player = _user(db_session)
    _bye(db_session, gara, player)
    attempt = _attempt(db_session, gara, player, score=0)

    with pytest.raises(ValidationError):
        ChallengeService.complete_x_replacement_attempt(attempt.id, score=-1)


@pytest.mark.unit
def test_il_limite_segue_la_distanza_del_turno_non_quella_della_gara(db_session):
    """ADR-027: gli override per turno contano anche qui.

    In un turno «al 3» dentro una gara «al 5», il massimo è 3. Leggere
    `gara.distance` invece di `match.effective_distance` accetterebbe un 5, che
    in quel turno nessuno può ottenere giocando.
    """
    gara = _gara(db_session, distance=5)
    player = _user(db_session)
    match = _bye(db_session, gara, player)
    match.match_distance = 3  # override per turno
    db_session.flush()
    assert match.effective_distance == 3

    attempt = _attempt(db_session, gara, player, score=0)

    with pytest.raises(ValidationError):
        ChallengeService.complete_x_replacement_attempt(attempt.id, score=5)
