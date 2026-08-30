"""Il tavolo dove si è giocato sopravvive alla fine della partita.

`match.table_assignment` risponde a «quale tavolo è occupato adesso»: alla
chiusura torna a NULL, ed è giusto così — è quel NULL che rimette il tavolo
in circolo per chi sta aspettando. Ma con lui spariva anche il fatto storico
«questa partita si è giocata al tavolo 3», e nella tabella dei turni le
partite concluse potevano mostrare solo un trattino (issue #154).

Da qui `played_on_table`, scritta da un hook `before_insert`/`before_update`
come `ended_at`: i punti che assegnano un tavolo sono otto e quelli che lo
liberano quattro, e presidiare i chiamanti lascerebbe scoperto il nono che
ancora non esiste. Questi test guardano la garanzia a valle.
"""

from __future__ import annotations

import pytest

from models.base import utc_now
from models.status_enum import MatchStatus


@pytest.fixture
def partita(db_session, isolated_players):
    """Una partita di gara in corso, al tavolo 3."""
    from models.competition.models import Gara
    from models.match.models import Match
    from models.status_enum import GaraStatus

    gara = Gara(
        number=1,
        name="Gara di prova",
        date=utc_now().date(),
        time=utc_now().time(),
        discipline="8_ball",
        distance=5,
        is_race_to=True,
        status=GaraStatus.PLAYING.value,
    )
    db_session.add(gara)
    db_session.flush()

    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=isolated_players[0].id,
        player2_id=isolated_players[1].id,
        player1_score=0,
        player2_score=0,
        status=MatchStatus.PLAYING.value,
        table_assignment="3",
    )
    db_session.add(match)
    db_session.commit()
    return match


class TestIlTavoloRestaScritto:
    def test_assegnare_un_tavolo_lo_ricorda(self, db_session, partita):
        assert partita.played_on_table == "3"

    def test_liberare_il_tavolo_non_cancella_dove_si_e_giocato(
        self, db_session, partita
    ):
        """È il difetto: qui la tabella dei turni perdeva il dato."""
        partita.status = MatchStatus.CLOSED_UNILATERALLY.value
        partita.table_assignment = None
        db_session.commit()

        assert partita.table_assignment is None, "il tavolo torna in circolo"
        assert partita.played_on_table == "3", "ma dove si è giocato resta"

    def test_lo_spostamento_a_un_altro_tavolo_aggiorna_il_fatto(
        self, db_session, partita
    ):
        """Chi cambia tavolo a metà partita ha giocato sull'ultimo, non sul primo."""
        partita.table_assignment = "5"
        db_session.commit()

        assert partita.played_on_table == "5"

    def test_una_partita_senza_tavolo_non_ne_inventa_uno(
        self, db_session, isolated_players, partita
    ):
        """Le gare senza tavoli dichiarati chiudono con `played_on_table` vuoto."""
        from models.match.models import Match

        senza_tavolo = Match(
            gara_id=partita.gara_id,
            round_number=1,
            player1_id=isolated_players[2].id,
            player2_id=isolated_players[3].id,
            player1_score=5,
            player2_score=2,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
        db_session.add(senza_tavolo)
        db_session.commit()

        assert senza_tavolo.played_on_table is None
