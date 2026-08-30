"""Correggere un risultato già chiuso, lasciandone traccia.

Il direttore inserisce un punteggio sbagliato e se ne accorge dopo (issue
#90). Correggerlo si poteva già — annullando e reinserendo — ma i giocatori
quel risultato l'avevano visto, e una classifica che cambia senza dire perché
sembra un errore dell'applicazione.

Il perimetro non è nuovo: è quello di `can_modify_match`. Si corregge dentro
una gara **in corso** e solo dove la correzione non ricade sui turni
successivi — con la formula casuale, dove i turni nascono tutti insieme, anche
un turno passato; con Amalfi, dove il turno seguente si costruisce sulla
classifica, solo finché quel turno non è partito.
"""

from __future__ import annotations

import pytest

from models.base import utc_now
from models.match.correction_service import MatchCorrectionService
from models.status_enum import GaraStatus, MatchStatus


@pytest.fixture
def gara_in_corso(db_session):
    from models.competition.models import Gara

    gara = Gara(
        number=1,
        name="Gara di prova",
        date=utc_now().date(),
        time=utc_now().time(),
        discipline="8_ball",
        distance=5,
        is_race_to=True,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        matchmaking_strategy="amalfi",
    )
    db_session.add(gara)
    db_session.commit()
    return gara


@pytest.fixture
def partita_chiusa(db_session, gara_in_corso, isolated_players):
    """Una partita del turno 1, chiusa dal direttore 5-3."""
    from models.match.models import Match

    match = Match(
        gara_id=gara_in_corso.id,
        round_number=1,
        player1_id=isolated_players[0].id,
        player2_id=isolated_players[1].id,
        player1_score=5,
        player2_score=3,
        winner_id=isolated_players[0].id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db_session.add(match)
    db_session.commit()
    return match


class TestLaCorrezioneCambiaIlRisultato:
    def test_il_punteggio_diventa_quello_corretto(
        self, db_session, partita_chiusa, isolated_players
    ):
        MatchCorrectionService.correct_result(
            match_id=partita_chiusa.id,
            player1_score=3,
            player2_score=5,
            corrected_by_id=isolated_players[0].id,
        )

        assert partita_chiusa.player1_score == 3
        assert partita_chiusa.player2_score == 5
        assert partita_chiusa.winner_id == isolated_players[1].id
        assert MatchStatus.is_finished(partita_chiusa.status)

    def test_la_traccia_dice_da_cosa_a_cosa(
        self, db_session, partita_chiusa, isolated_players
    ):
        """È la metà che conta: senza, la classifica cambia e nessuno sa perché."""
        traccia = MatchCorrectionService.correct_result(
            match_id=partita_chiusa.id,
            player1_score=3,
            player2_score=5,
            corrected_by_id=isolated_players[2].id,
            note="punteggio invertito in fase di inserimento",
        )

        assert traccia.previous_player1_score == 5
        assert traccia.previous_player2_score == 3
        assert traccia.new_player1_score == 3
        assert traccia.new_player2_score == 5
        assert traccia.previous_status == MatchStatus.CLOSED_UNILATERALLY.value
        assert traccia.corrected_by_id == isolated_players[2].id
        assert traccia.note == "punteggio invertito in fase di inserimento"
        assert partita_chiusa.corrections == [traccia]

    def test_una_nota_vuota_non_si_registra(
        self, db_session, partita_chiusa, isolated_players
    ):
        """Meglio nessuna nota che una stringa vuota da mostrare."""
        traccia = MatchCorrectionService.correct_result(
            match_id=partita_chiusa.id,
            player1_score=3,
            player2_score=5,
            corrected_by_id=isolated_players[0].id,
            note="   ",
        )

        assert traccia.note is None

    def test_i_triangoli_si_cancellano(
        self, db_session, partita_chiusa, isolated_players
    ):
        """Un punteggio scritto a mano e un elenco di triangoli che dice
        un'altra cosa sono due segnapunti che si contraddicono."""
        from models.match.models import Rack

        for numero in range(1, 6):
            db_session.add(
                Rack(
                    match_id=partita_chiusa.id,
                    rack_number=numero,
                    winner_id=isolated_players[0].id,
                    reported_by_id=isolated_players[0].id,
                )
            )
        db_session.commit()

        MatchCorrectionService.correct_result(
            match_id=partita_chiusa.id,
            player1_score=3,
            player2_score=5,
            corrected_by_id=isolated_players[0].id,
        )

        assert Rack.query.filter_by(match_id=partita_chiusa.id).count() == 0


class TestIlPunteggioDeveEsserePossibile:
    def test_nessuno_arriva_alla_distanza(
        self, db_session, partita_chiusa, isolated_players
    ):
        with pytest.raises(ValueError):
            MatchCorrectionService.correct_result(
                match_id=partita_chiusa.id,
                player1_score=4,
                player2_score=3,
                corrected_by_id=isolated_players[0].id,
            )

    def test_non_vincono_tutti_e_due(
        self, db_session, partita_chiusa, isolated_players
    ):
        with pytest.raises(ValueError):
            MatchCorrectionService.correct_result(
                match_id=partita_chiusa.id,
                player1_score=5,
                player2_score=5,
                corrected_by_id=isolated_players[0].id,
            )

    def test_niente_punteggi_negativi(
        self, db_session, partita_chiusa, isolated_players
    ):
        with pytest.raises(ValueError):
            MatchCorrectionService.correct_result(
                match_id=partita_chiusa.id,
                player1_score=5,
                player2_score=-1,
                corrected_by_id=isolated_players[0].id,
            )

    def test_la_distanza_e_quella_del_turno_non_della_gara(
        self, db_session, gara_in_corso, partita_chiusa, isolated_players
    ):
        """ADR-027: in un turno «al 3» dentro una gara «al 5» il massimo è 3.

        L'override del turno arriva sul match come `match_distance`, che è
        dove round-creation lo scrive: leggere `gara.distance` accetterebbe un
        punteggio che in quel turno nessuno può fare giocando.
        """
        partita_chiusa.match_distance = 3
        partita_chiusa.is_race_to = True
        db_session.commit()

        MatchCorrectionService.correct_result(
            match_id=partita_chiusa.id,
            player1_score=3,
            player2_score=1,
            corrected_by_id=isolated_players[0].id,
        )
        assert partita_chiusa.player1_score == 3

        with pytest.raises(ValueError):
            MatchCorrectionService.correct_result(
                match_id=partita_chiusa.id,
                player1_score=5,
                player2_score=1,
                corrected_by_id=isolated_players[0].id,
            )


class TestIlPerimetro:
    def test_la_x_a_tavolino_non_ha_nulla_da_correggere(
        self, db_session, gara_in_corso, isolated_players
    ):
        from models.match.models import Match

        bye = Match(
            gara_id=gara_in_corso.id,
            round_number=1,
            player1_id=isolated_players[3].id,
            player2_id=None,
            is_bye=True,
            player1_score=0,
            player2_score=0,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
        db_session.add(bye)
        db_session.commit()

        consentito, motivo = MatchCorrectionService.can_correct(bye.id)

        assert not consentito
        assert motivo

    def test_a_gara_conclusa_non_si_corregge(
        self, db_session, gara_in_corso, partita_chiusa
    ):
        """Il perimetro è quello di `can_modify_match`, e lì la gara conclusa
        è chiusa: la via d'uscita è riaprire la gara, non correggere."""
        gara_in_corso.status = GaraStatus.COMPLETED.value
        db_session.commit()

        consentito, motivo = MatchCorrectionService.can_correct(partita_chiusa.id)

        assert not consentito
        assert motivo

    def test_il_motivo_del_rifiuto_non_e_mai_muto(
        self, db_session, gara_in_corso, partita_chiusa
    ):
        """Chi non può correggere deve sapere cosa fare, non solo che non può."""
        gara_in_corso.status = GaraStatus.INSCRIPTION.value
        db_session.commit()

        _, motivo = MatchCorrectionService.can_correct(partita_chiusa.id)

        assert motivo.strip()
