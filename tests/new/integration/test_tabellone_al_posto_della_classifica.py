"""Il tabellone al posto della classifica nelle gare a eliminazione (issue #240).

Le quattro verifiche chieste dall'issue, sulla pagina vera:

* una gara a tabellone in gioco mostra i nomi dei turni e il tabellone
  compatto, e non la tabella «Vinte / Diff»;
* subito dopo il sorteggio la pagina del tabellone disegna anche i nodi dei
  turni successivi, vuoti;
* una gara a turni conserva la sua classifica, esattamente com'era;
* a gara conclusa la classifica e' a bande: due quartifinalisti hanno la
  stessa posizione mostrata, e gli stessi punti di campionato.

Piu' le parole della fascia fra un turno e l'altro, il menu del turno 1 e la
card che dice dove va chi vince.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import List

import pytest

from models import Gara, Match, User
from models.base import utc_now
from models.classification.bracket_standings import bracket_positions
from models.classification.position_points import points_for_position
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.match.services import RackService
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user("tab_admin", "tab_admin@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "tab_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def _players(db_session, count: int) -> List[User]:
    batch = str(uuid.uuid4())[:8]
    players = []
    for index in range(count):
        player = User(
            username=f"tab{index}_{batch}",
            email=f"tab{index}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        players.append(player)
    db_session.add_all(players)
    db_session.commit()
    return players


def _gara_a_tabellone(db_session, n: int, *, strategy="direct_elimination") -> Gara:
    players = _players(db_session, n)
    gara = Gara(
        number=1,
        name=f"Tabellone {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        discipline=Discipline.NINE_BALL.value,
        distance=2,
        is_race_to=True,
        rounds_count=3,
        min_participants=4,
        max_participants=16,
        matchmaking_strategy=strategy,
        classification_system="POSITION",
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


def _gioca_turno(db_session, gara_id: int, round_number: int) -> None:
    """Chiude il turno: vince sempre `player1`."""
    for match in Match.query.filter_by(gara_id=gara_id, round_number=round_number):
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=match.player1_id,
                reported_by_id=match.player1_id,
                validated_by_admin=True,
            )
    db_session.commit()


def _pagina(client, gara) -> str:
    response = client.get(f"/admin/gara/{gara.id}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


class TestInGioco:
    def test_nomi_dei_turni_e_tabellone_compatto_senza_vinte(
        self, admin_client, db_session
    ):
        gara = _gara_a_tabellone(db_session, 8)
        RoundService.start_first_round(gara.id)

        page = _pagina(admin_client, gara)

        assert "c7-tabellino" in page
        assert "Quarti · Turno 1 di 3" in page
        assert "Semifinali" in page  # la colonna del turno dopo, gia' disegnata
        assert ">Vinte<" not in page and ">Diff<" not in page
        # La card dice dove va chi vince.
        assert "Chi vince: Semifinali contro chi vince" in page

    def test_il_menu_del_turno_1_annulla_il_sorteggio(self, admin_client, db_session):
        gara = _gara_a_tabellone(db_session, 8)
        RoundService.start_first_round(gara.id)

        page = _pagina(admin_client, gara)

        assert "Annulla il sorteggio" in page
        assert "Annulla l&#39;avvio del turno 1" not in page

    def test_fra_un_turno_e_l_altro_la_fascia_parla_del_tabellone(
        self, admin_client, db_session
    ):
        gara = _gara_a_tabellone(db_session, 8)
        RoundService.start_first_round(gara.id)
        _gioca_turno(db_session, gara.id, 1)

        page = _pagina(admin_client, gara)

        assert "Semifinali pronte" in page
        assert "Avvia le semifinali" in page
        assert "già fissati dal tabellone" in page
        assert "sulla classifica di adesso" not in page

    def test_chi_passa_il_turno_non_riposa(self, admin_client, db_session):
        gara = _gara_a_tabellone(db_session, 6)
        RoundService.start_first_round(gara.id)

        page = _pagina(admin_client, gara)

        assert "passa il turno" in page
        assert "riposa" not in page


class TestSubitoDopoIlSorteggio:
    def test_il_tabellone_disegna_i_nodi_futuri(self, client, db_session):
        gara = _gara_a_tabellone(db_session, 8)
        RoundService.start_first_round(gara.id)

        page = client.get(f"/admin/gara/{gara.id}/tabellone").get_data(as_text=True)

        # Quattro quarti giocati, due semifinali e una finale vuote.
        assert page.count("c7-bracket__node--vuoto") == 3
        assert "Finale" in page and "Semifinali" in page


class TestGaraATurni:
    def test_la_classifica_resta_com_era(self, admin_client, db_session):
        from models.user.services import UserService

        gara = Gara(
            number=1,
            name="Gara a turni",
            date=date.today(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=5,
            is_race_to=True,
            matchmaking_strategy="amalfi",
            status=GaraStatus.PLAYING.value,
            current_round=1,
            rounds_count=3,
            min_participants=2,
        )
        db_session.add(gara)
        db_session.commit()
        p1 = UserService.create_user("turni_a", "turni_a@test.local", "pw12345")
        p2 = UserService.create_user("turni_b", "turni_b@test.local", "pw12345")
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=p1.id,
                player2_id=p2.id,
                player1_score=5,
                player2_score=3,
                winner_id=p1.id,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
        db_session.commit()

        page = _pagina(admin_client, gara)

        assert 'id="classificaDirettore"' in page
        assert ">Vinte<" in page and ">Diff<" in page
        assert "c7-tabellino" not in page
        assert "Turno 1 di 3 · concluso" in page


class TestGaraConclusa:
    def test_i_quartifinalisti_condividono_il_posto_e_i_punti(
        self, admin_client, db_session
    ):
        gara = _gara_a_tabellone(db_session, 8)
        RoundService.start_first_round(gara.id)
        for turno in (1, 2, 3):
            if turno > 1:
                RoundService.start_next_round(gara.id, turno)
            _gioca_turno(db_session, gara.id, turno)
        gara = db_session.get(Gara, gara.id)
        gara.status = GaraStatus.COMPLETED.value
        db_session.commit()

        posizioni = bracket_positions(gara)
        quinti = [uid for uid, pos in posizioni.items() if pos == 5]
        assert len(quinti) == 4
        assert len({points_for_position(posizioni[uid]) for uid in quinti}) == 1

        page = _pagina(admin_client, gara)

        assert ">Vinte<" not in page
        assert len(re.findall(r'data-banda="5"', page)) == 4
        assert page.count("5°–8°") == 4
        assert page.count("esce ai quarti") == 4
        assert "3°–4°" in page  # senza finalina due terzi, dichiarati
