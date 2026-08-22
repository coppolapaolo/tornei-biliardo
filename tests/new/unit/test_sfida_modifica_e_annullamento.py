"""La finestra in cui una sfida individuale si corregge ancora.

Annullare e modificare rispondono alla stessa domanda — «avete già segnato
qualcosa?» — e questi test la fanno in tutti i modi in cui può ricevere una
risposta sbagliata: il punteggio a zero che nasconde un set in corso, il
referto TPA con dei comandi e nessun rack, e la partita chiusa dai due
giocatori, che prima si lasciava annullare **dopo** aver mosso l'Elo.
"""

import pytest
from datetime import timedelta

from models.base import utc_now
from models.individual_match.models import IndividualMatch
from models.individual_match.services import IndividualMatchService
from models.status_enum import Discipline, MatchStatus


def _sfida(db_session, players, **campi):
    player1, player2 = players[:2]
    valori = dict(
        player1_id=player1.id,
        player2_id=player2.id,
        location="Sala di prova",
        scheduled_at=utc_now() + timedelta(hours=1),
        status=MatchStatus.IN_PROGRESS,
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
    )
    valori.update(campi)
    match = IndividualMatch(**valori)
    db_session.add(match)
    db_session.commit()
    return match


class TestQuandoLaSfidaSiCorreggeAncora:
    def test_appena_aperta_si_corregge(self, app, db_session, isolated_players):
        match = _sfida(db_session, isolated_players)
        assert match.has_recorded_play() is False
        assert match.can_be_revised() is True

    def test_dal_primo_triangolo_non_piu(self, app, db_session, isolated_players):
        match = _sfida(db_session, isolated_players)
        match.add_rack_result(match.player1_id)
        db_session.commit()

        assert match.has_recorded_play() is True
        assert match.can_be_revised() is False

    def test_un_triangolo_annullato_riapre_la_finestra(
        self, app, db_session, isolated_players
    ):
        """Il rack tolto è cancellato in modo morbido, non è mai esistito."""
        match = _sfida(db_session, isolated_players)
        match.add_rack_result(match.player1_id)
        db_session.commit()
        match._remove_last_rack(match.player1_id)
        db_session.commit()

        assert match.has_recorded_play() is False

    def test_a_set_lo_zero_a_zero_non_basta(self, app, db_session, isolated_players):
        """Nei match a set ``player*_score`` conta i **set**.

        0-0 può quindi voler dire «primo set in corso, con dei triangoli
        dentro»: guardare il solo punteggio direbbe che non è stato giocato
        niente, e la partita si lascerebbe riconfigurare a metà.
        """
        match = _sfida(
            db_session,
            isolated_players,
            status=MatchStatus.SCHEDULED,
            is_multi_set=True,
            match_distance=3,
            is_race_to_sets=True,
        )
        match.start_match()
        db_session.commit()
        assert match.has_recorded_play() is False

        match.add_rack_result(match.player1_id)
        db_session.commit()

        assert match.player1_score == 0, "nessun set ancora vinto"
        assert match.has_recorded_play() is True


class TestAnnullamento:
    def test_una_sfida_intonsa_si_annulla(self, app, db_session, isolated_players):
        match = _sfida(db_session, isolated_players)
        IndividualMatchService.cancel_match(match.id, match.player1_id)
        assert match.status == MatchStatus.CANCELLED

    def test_con_dei_triangoli_segnati_non_si_annulla(
        self, app, db_session, isolated_players
    ):
        match = _sfida(db_session, isolated_players)
        match.add_rack_result(match.player2_id)
        db_session.commit()

        with pytest.raises(ValueError, match="cominciata"):
            IndividualMatchService.cancel_match(match.id, match.player1_id)

    def test_una_sfida_confermata_dai_due_non_si_annulla(
        self, app, db_session, isolated_players
    ):
        """Il buco che c'era: ``CONFIRMED_BY_BOTH`` passava il controllo.

        È la chiusura per doppia conferma, cioè l'unica che muove l'Elo
        globale (ADR-051). Annullarla faceva sparire il risultato e lasciava i
        suoi effetti dov'erano.
        """
        match = _sfida(db_session, isolated_players)
        match.status = MatchStatus.CONFIRMED_BY_BOTH
        db_session.commit()

        with pytest.raises(ValueError, match="già chiusa"):
            IndividualMatchService.cancel_match(match.id, match.player1_id)

        assert match.status == MatchStatus.CONFIRMED_BY_BOTH


class TestModifica:
    def test_si_cambia_la_distanza_prima_di_segnare(
        self, app, db_session, isolated_players
    ):
        match = _sfida(db_session, isolated_players)
        IndividualMatchService.update_settings(
            match.id, match.player1_id, distance=7, is_race_to=False
        )

        assert match.distance == 7
        assert match.is_race_to is False

    def test_a_partita_cominciata_la_modifica_e_rifiutata(
        self, app, db_session, isolated_players
    ):
        match = _sfida(db_session, isolated_players)
        match.add_rack_result(match.player1_id)
        db_session.commit()

        with pytest.raises(ValueError, match="cominciata"):
            IndividualMatchService.update_settings(
                match.id, match.player1_id, distance=9
            )

        assert match.distance == 5

    def test_solo_i_due_giocatori(self, app, db_session, isolated_players):
        match = _sfida(db_session, isolated_players)
        estraneo = isolated_players[2]

        with pytest.raises(ValueError, match="due giocatori"):
            IndividualMatchService.update_settings(match.id, estraneo.id, distance=7)

    def test_un_campo_non_previsto_non_passa(self, app, db_session, isolated_players):
        """L'elenco è una lista bianca: `**fields` senza filtro sarebbe una
        scrittura arbitraria su qualunque colonna, punteggio compreso."""
        match = _sfida(db_session, isolated_players)

        with pytest.raises(ValueError, match="non modificabili"):
            IndividualMatchService.update_settings(
                match.id, match.player1_id, player1_score=5
            )

    def test_passare_a_set_apre_il_primo_set(self, app, db_session, isolated_players):
        """Un match a set senza set aperto non è giocabile."""
        match = _sfida(db_session, isolated_players)
        assert match.sets == []

        IndividualMatchService.update_settings(
            match.id,
            match.player1_id,
            is_multi_set=True,
            match_distance=3,
            is_race_to_sets=True,
        )

        assert len(match.sets) == 1
        assert match.sets[0].set_number == 1
