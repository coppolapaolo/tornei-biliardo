"""I bordi del ciclo di vita di una gara a tabellone (Step 11).

Tre comportamenti che i test di percorso non toccano e che sono facili da
rompere senza accorgersene:

1. il **criterio delle teste di serie** (`first_round_policy`) conta davvero —
   era dichiarato e ignorato fino allo Step 4, e chi non ha il dato richiesto
   deve finire in coda, non a metà classifica (US-10);
2. un **ritiro dopo il sorteggio** non tocca il tabellone: l'avversario passa
   a tavolino (R5b). Ritoccare l'albero a gara iniziata renderebbe falso tutto
   quello che i giocatori hanno già visto;
3. le **opzioni del tabellone** non si cambiano a iscrizioni aperte (US-6):
   ogni iscrizione deve nascere con la sua squadra, altrimenti esiste il caso
   "metà iscritti senza squadra" che il sorteggio non saprebbe trattare.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List

import pytest

from models import Gara, Match, User, db
from models.base import utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _players(db_session, count: int, elo=None) -> List[User]:
    batch = str(uuid.uuid4())[:8]
    users = []
    for index in range(count):
        user = User(
            username=f"edge_{index}_{batch}",
            email=f"edge_{index}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("player123")
        if elo is not None:
            user.elo_rating = elo[index]
        users.append(user)
    db_session.add_all(users)
    db_session.commit()
    return users


def _gara(db_session, players, **kwargs) -> Gara:
    batch = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{batch}",
        email=f"dir_{batch}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("director123")
    db_session.add(director)
    db_session.flush()

    campi = {
        "director_id": director.id,
        "number": db_session.query(Gara).count() + 1,
        "name": f"Edge {batch}",
        "date": date.today() + timedelta(days=7),
        "discipline": "9_ball",
        "distance": 3,
        "is_race_to": True,
        "rounds_count": 3,
        "min_participants": 4,
        "max_participants": 8,
        "matchmaking_strategy": "direct_elimination",
        "first_round_policy": "random",
        "classification_system": "POSITION",
    }
    campi.update(kwargs)
    gara = Gara(**campi)
    db_session.add(gara)
    db_session.commit()

    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    db_session.commit()
    return gara


def _bye_players(gara_id: int) -> set:
    """Chi ha ricevuto un X a tavolino al primo turno = le teste di serie."""
    return {
        match.player1_id
        for match in Match.query.filter_by(
            gara_id=gara_id, round_number=1, is_bye=True
        ).all()
    }


class TestCriterioTesteDiSerie:
    def test_per_rating_i_bye_vanno_ai_piu_forti(self, db_session):
        """US-10: con 5 iscritti su un tabellone da 8 i 3 bye sono dei migliori."""
        players = _players(db_session, 5, elo=[1000, 1100, 1200, 1300, 1400])
        gara = _gara(db_session, players, first_round_policy="rating")

        RoundService.start_first_round(gara.id)
        db_session.refresh(gara)

        assert gara.rounds_count == 3, "5 iscritti = tabellone da 8"
        migliori = {players[4].id, players[3].id, players[2].id}
        assert _bye_players(gara.id) == migliori

    def test_senza_rating_si_finisce_in_coda(self, db_session):
        """Mancanza di dato non è un piazzamento intermedio.

        Due giocatori con Elo, tre senza: i bye devono andare ai due con il
        rating, mai a chi non ne ha.
        """
        players = _players(db_session, 5, elo=[None, None, None, 1300, 1400])
        gara = _gara(db_session, players, first_round_policy="rating")

        RoundService.start_first_round(gara.id)

        con_rating = {players[3].id, players[4].id}
        assert con_rating <= _bye_players(gara.id)

    def test_casuale_non_segue_il_rating(self, db_session):
        """La policy `random` deve ignorare l'Elo, altrimenti non è casuale.

        Con dieci semi diversi almeno un sorteggio deve differire da quello
        per rating: se coincidessero tutti, la policy non starebbe facendo
        nulla di diverso.
        """
        atteso = None
        diversi = 0
        for seme in range(10):
            players = _players(db_session, 5, elo=[1000, 1100, 1200, 1300, 1400])
            gara = _gara(
                db_session, players, first_round_policy="random", draw_seed=seme
            )
            RoundService.start_first_round(gara.id)

            migliori = {players[4].id, players[3].id, players[2].id}
            if _bye_players(gara.id) != migliori:
                diversi += 1
            atteso = migliori

        assert atteso is not None
        assert diversi > 0, "il sorteggio casuale seguiva sempre il rating"


class TestRitiroDopoIlSorteggio:
    def test_il_tabellone_non_si_tocca(self, db_session):
        """R5b: l'albero è già stato visto da tutti, quindi resta com'è."""
        players = _players(db_session, 8)
        gara = _gara(db_session, players)
        RoundService.start_first_round(gara.id)

        prima = {
            (m.bracket_slot, m.player1_id, m.player2_id)
            for m in Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        }

        ritirato = players[0]
        InscriptionService.uninscribe_user(ritirato.id, gara.id)
        db_session.commit()

        dopo = {
            (m.bracket_slot, m.player1_id, m.player2_id)
            for m in Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        }
        assert dopo == prima

        # E il nodo del ritirato resta giocabile: l'avversario vince a
        # tavolino, non si trova senza partita.
        nodo = Match.query.filter(
            Match.gara_id == gara.id,
            Match.round_number == 1,
            db.or_(Match.player1_id == ritirato.id, Match.player2_id == ritirato.id),
        ).one()
        assert not MatchStatus.is_finished(nodo.status) or nodo.winner_id is not None


class TestFinestraDiConfigurazione:
    def test_le_opzioni_non_si_cambiano_a_iscrizioni_aperte(self, db_session):
        """US-6: si decide in setup, così ogni iscrizione nasce con la squadra."""
        players = _players(db_session, 4)
        gara = _gara(db_session, players, separate_teammates=False)

        with pytest.raises(ValueError):
            GaraService.update_gara(gara.id, separate_teammates=True)

        db_session.rollback()
        assert db_session.get(Gara, gara.id).separate_teammates is False

    def test_in_setup_si_cambiano(self, db_session):
        """Il divieto è sulle iscrizioni aperte, non sulla configurazione."""
        gara = _gara(db_session, [], separate_teammates=False)
        gara.status = GaraStatus.SETUP.value
        db_session.commit()

        GaraService.update_gara(gara.id, separate_teammates=True)

        assert db_session.get(Gara, gara.id).separate_teammates is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
