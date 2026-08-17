"""La pagina del tabellone si apre davvero, anche senza account (US-13).

Il costruttore delle lavagne ha i suoi unit test; qui si verifica il pezzo
che quelli non possono coprire — che la route esista, che risponda a un
anonimo, che il template renda senza esplodere e che i nomi dei giocatori
del turno 1 ci siano davvero.

Il caso interessante non e' quello pieno ma quello con i bye: e' li' che il
tabellone ha nodi a un giocatore solo, ed e' la forma che il template deve
reggere senza `player2`.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List

import pytest

from models import Gara, Match, User
from models.base import utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _make_players(db_session, count: int) -> List[User]:
    batch = str(uuid.uuid4())[:8]
    players = []
    for index in range(count):
        player = User(
            username=f"brk_{index}_{batch}",
            email=f"brk_{index}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        players.append(player)
    db_session.add_all(players)
    db_session.commit()
    return players


def _make_gara(db_session, players: List[User], *, strategy: str) -> Gara:
    batch = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{batch}",
        email=f"dir_{batch}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("director123")
    db_session.add(director)
    db_session.flush()

    gara = Gara(
        director_id=director.id,
        number=db_session.query(Gara).count() + 1,
        name=f"Tabellone {batch}",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=3,
        is_race_to=True,
        rounds_count=8,
        min_participants=4,
        max_participants=16,
        matchmaking_strategy=strategy,
        first_round_policy="random",
    )
    db_session.add(gara)
    db_session.commit()

    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    db_session.commit()
    return gara


class TestVistaTabellone:
    def test_anonimo_vede_il_tabellone_sorteggiato(self, client, db_session):
        """US-13: la segue anche chi non ha un account."""
        players = _make_players(db_session, 6)
        gara = _make_gara(db_session, players, strategy="direct_elimination")
        RoundService.start_first_round(gara.id)

        response = client.get(f"/admin/gara/{gara.id}/tabellone")
        assert response.status_code == 200

        page = response.get_data(as_text=True)
        for player in players:
            assert player.username in page, f"{player.username} manca dal tabellone"
        # 6 iscritti -> tabellone da 8: due nodi sono X a tavolino.
        assert "tavolino" in page

    def test_prima_del_sorteggio_lo_stato_vuoto(self, client, db_session):
        """Senza coordinate non si finge un tabellone: si dice che manca."""
        players = _make_players(db_session, 6)
        gara = _make_gara(db_session, players, strategy="direct_elimination")

        response = client.get(f"/admin/gara/{gara.id}/tabellone")
        assert response.status_code == 200
        assert "c7-empty" in response.get_data(as_text=True)

    def test_doppio_ko_mostra_i_due_rami(self, client, db_session):
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players, strategy="double_knockout")
        RoundService.start_first_round(gara.id)

        # Il ramo dei ripescati nasce al turno 2: prima non esiste nulla da
        # distinguere, quindi il test lo fa comparire chiudendo il turno 1.
        for match in Match.query.filter_by(gara_id=gara.id, round_number=1).all():
            match.status = MatchStatus.CLOSED_UNILATERALLY.value
            match.winner_id = match.player1_id
            match.player1_score = 3
        db_session.commit()
        RoundService.start_next_round(gara.id, 2)

        page = client.get(f"/admin/gara/{gara.id}/tabellone").get_data(as_text=True)
        assert "Vincenti" in page
        assert "Ripescati" in page

    def test_gara_senza_tabellone_non_ha_la_pagina(self, client, db_session):
        """Su una gara ad Amalfi non c'e' un tabellone parziale da mostrare."""
        players = _make_players(db_session, 6)
        gara = _make_gara(db_session, players, strategy="amalfi")

        assert client.get(f"/admin/gara/{gara.id}/tabellone").status_code == 404

    def test_gara_inesistente(self, client):
        assert client.get("/admin/gara/999999/tabellone").status_code == 404


class TestChiDirige:
    def test_i_nodi_sono_cliccabili_solo_per_chi_dirige(self, client, db_session):
        """Al direttore il tabellone serve anche per arrivare alla partita.

        Per tutti gli altri e' sola lettura: `match_detail` chiede comunque
        l'accesso, e un anonimo cliccherebbe per finire sul login.
        """
        players = _make_players(db_session, 6)
        gara = _make_gara(db_session, players, strategy="direct_elimination")
        RoundService.start_first_round(gara.id)
        director = db_session.get(User, gara.director_id)
        # L'onboarding obbligatorio (ADR-035) intercetta la navigazione: qui
        # interessa il tabellone, non quel percorso.
        director.onboarding_completed = True
        db_session.commit()

        anonimo = client.get(f"/admin/gara/{gara.id}/tabellone").get_data(as_text=True)
        assert '<a class="c7-bracket__node' not in anonimo

        client.post(
            "/auth/login",
            data={"username": director.username, "password": "director123"},
            follow_redirects=True,
        )
        page = client.get(f"/admin/gara/{gara.id}/tabellone").get_data(as_text=True)
        assert '<a class="c7-bracket__node' in page
        assert "/admin/match/" in page


class TestCollegamentoDallaGara:
    def test_il_link_compare_solo_a_tabellone_estratto(self, client, db_session):
        players = _make_players(db_session, 6)
        gara = _make_gara(db_session, players, strategy="direct_elimination")

        prima = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert f"/admin/gara/{gara.id}/tabellone" not in prima

        RoundService.start_first_round(gara.id)
        dopo = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
        assert f"/admin/gara/{gara.id}/tabellone" in dopo


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
