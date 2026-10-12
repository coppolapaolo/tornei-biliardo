"""Le pagine di una gara con le finali per piazzamento (ADR-081).

Due gironi, 4 + 4 e 5 + 4, composti per ELO; vince sempre il più forte.

* A gironi finiti: accanto a ogni riga dei gironi la finale che giocherà
  («→ finale 1°/2° posto con …»), e col 5 + 4 l'ultimo del girone da cinque
  «9° diretto». Pagina del direttore, pagina pubblica, schermo in sala.
* A finali in corso: il turno si chiama «Finali per piazzamento», e ogni
  partita ha il suo nome, sulle card del direttore e nella lista pubblica.
* A gara conclusa: la classifica della serata dice com'è andata la finale
  di ognuno, e il riquadro «Pari merito» non promette lo spareggio SSR.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List, Tuple

import pytest

from models import User
from models.base import db, utc_now
from models.competition.fase_finale_service import turni_dei_gironi
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.match.models import Match
from models.match.services import RackService
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

FINALE = "data-finale="


def _utente(role: str, elo=None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"fpg_{role}_{uid}", email=f"fpg_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    user.elo_rating = elo
    db.session.add(user)
    return user


def _gara(n: int) -> Tuple[Gara, User, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value, elo=2000 - 10 * i) for i in range(n)]
    db.session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Lunedì al 74",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=16,
        entry_fee=0.0,
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy="round_robin",
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=False,
        max_groups=2,
        group_seeding="elo",
        final_phase_mode="piazzamento",
    )
    gara.public_token = uuid.uuid4().hex[:10]
    db.session.commit()
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    return gara, director, players


def _gioca(gara_id: int, r: int, elo) -> None:
    for match in Match.query.filter_by(gara_id=gara_id, round_number=r).all():
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        vince = max((match.player1_id, match.player2_id), key=lambda p: elo[p])
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=vince,
                reported_by_id=vince,
                validated_by_admin=True,
            )
    db.session.commit()
    RoundService.update_round_progression(gara_id)
    db.session.commit()


def _fino_a(n: int, fase: str) -> Tuple[Gara, User, List[User]]:
    gara, director, players = _gara(n)
    elo = {p.id: p.elo_rating for p in players}
    RoundService.start_first_round(gara.id, groups_count=2)
    gironi = turni_dei_gironi(db.session.get(Gara, gara.id))
    for r in range(1, gironi + 1):
        if r > 1:
            RoundService.start_next_round(gara.id, r)
        _gioca(gara.id, r, elo)
    if fase in ("finali", "conclusa"):
        RoundService.start_next_round(gara.id, gironi + 1)
        db.session.commit()
    if fase == "conclusa":
        _gioca(gara.id, gironi + 1, elo)
        GaraService.complete(gara.id)
        db.session.commit()
    return db.session.get(Gara, gara.id), director, players


def _come(client, user: User) -> None:
    risposta = client.post(
        "/auth/login", data={"username": user.username, "password": "x"}
    )
    assert risposta.status_code in (200, 302)


def _html(client, url: str) -> str:
    risposta = client.get(url)
    assert risposta.status_code == 200, url
    return risposta.get_data(as_text=True)


def _classifica(html: str) -> str:
    sezione = html[html.index('id="classificaDirettore"') :]
    return sezione[: sezione.index("</section>")]


@pytest.mark.parametrize("iscritti", [8, 9])
def test_a_gironi_finiti_la_finale_accanto_a_ogni_riga(client, iscritti):
    gara, director, players = _fino_a(iscritti, "gironi")
    primo, secondo = players[0].username, players[1].username
    # Prima chi guarda (l'utente collegato resta in `g` fra le richieste).
    pubblica = _html(client, f"/admin/gara/{gara.id}")
    assert pubblica.count(FINALE) >= iscritti
    assert "c7-partita__forma" not in pubblica
    sala = _html(client, f"/g/{gara.public_token}/sala")
    assert sala.count(FINALE) == iscritti

    _come(client, director)
    sezione = _classifica(_html(client, f"/admin/gara/{gara.id}"))
    assert sezione.count(FINALE) == iscritti
    # I due più forti sono primi nei due gironi: si giocano il 1° posto.
    assert f"finale 1°/2° posto con {secondo} (1° girone" in sezione
    assert f"finale 1°/2° posto con {primo} (1° girone" in sezione
    if iscritti == 9:
        assert 'data-finale="diretto"' in sezione and "9° diretto" in sezione
    assert "il 1° di un girone gioca contro il 1°" in sezione


@pytest.mark.parametrize("iscritti", [8, 9])
def test_a_finali_in_corso_il_turno_e_le_partite_hanno_un_nome(client, iscritti):
    gara, director, _players = _fino_a(iscritti, "finali")
    # Prima chi guarda: nei test l'utente collegato resta in `g` fra le
    # richieste, quindi l'ospite va interrogato prima del login.
    pubblica = _html(client, f"/admin/gara/{gara.id}")
    assert "Finali per piazzamento</h3>" in pubblica
    assert pubblica.count('class="c7-match-finale"') == 8  # 4 card + 4 righe

    _come(client, director)
    html = _html(client, f"/admin/gara/{gara.id}")
    for posto in ("1°/2°", "3°/4°", "5°/6°", "7°/8°"):
        assert f"Finale {posto} posto" in html
    assert 'class="c7-partita__forma c7-partita__finale"' in html


@pytest.mark.parametrize("iscritti", [8, 9])
def test_a_gara_conclusa_la_classifica_della_serata(client, iscritti):
    gara, director, players = _fino_a(iscritti, "conclusa")
    pubblica = _html(client, f"/admin/gara/{gara.id}")
    assert "vince la finale 3°/4° posto" in pubblica
    sala = _html(client, f"/g/{gara.public_token}/sala")
    assert "vince la finale 3°/4° posto" in sala

    _come(client, director)
    html = _html(client, f"/admin/gara/{gara.id}")
    sezione = _classifica(html)
    assert "vince la gara" in sezione
    assert "perde la finale 1°/2° posto" in sezione
    assert "vince la finale 3°/4° posto" in sezione
    if iscritti == 9:
        assert "9° diretto" in sezione
    assert "L’ordine lo danno le finali per piazzamento" in sezione
    # Il riquadro dei pari merito non promette lo spareggio SSR.
    assert "niente spareggio SSR" in html
    assert "spareggio SSR fino al" not in html
