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


@pytest.fixture
def trio_chiuso(db_session, gara_in_corso, isolated_players):
    """Un trio del turno 1 chiuso dal direttore 4-2-0.

    Alla distanza 5 il trio ha due gironi: sei triangoli, quattro a testa.
    """
    from models.match.models import Match, TrioMatch
    from models.match.trio_scoring_service import TrioScoringService

    p1, p2, p3 = isolated_players[:3]
    match = Match(
        gara_id=gara_in_corso.id,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        is_trio=True,
        status=MatchStatus.PLAYING.value,
    )
    db_session.add(match)
    db_session.flush()
    trio = TrioMatch(
        match_id=match.id, player1_id=p1.id, player2_id=p2.id, player3_id=p3.id
    )
    db_session.add(trio)
    db_session.commit()
    TrioScoringService.set_result_direct(trio.id, 4, 2, 0)
    db_session.commit()
    return match.id, trio.id


class TestIlTrioSiCorregge:
    """Il trio si corregge come la partita a due: tre numeri invece di due."""

    @staticmethod
    def _corregge(match_id, punti, chi, note=None):
        return MatchCorrectionService.correct_result(
            match_id=match_id,
            player1_score=punti[0],
            player2_score=punti[1],
            player3_score=punti[2],
            corrected_by_id=chi,
            note=note,
        )

    def test_il_trio_chiuso_si_puo_correggere(self, trio_chiuso):
        consentito, motivo = MatchCorrectionService.can_correct(trio_chiuso[0])
        assert consentito, motivo

    def test_il_punteggio_e_il_vincitore_diventano_quelli_corretti(
        self, db_session, trio_chiuso, isolated_players
    ):
        from models.match.models import Match, TrioMatch

        match_id, trio_id = trio_chiuso
        self._corregge(match_id, (1, 3, 2), isolated_players[4].id)

        trio = db_session.get(TrioMatch, trio_id)
        match = db_session.get(Match, match_id)
        assert trio.player_racks_list == [1, 3, 2]
        assert trio.winner_id == isolated_players[1].id
        assert match.winner_id == isolated_players[1].id
        assert (match.player1_score, match.player2_score) == (1, 3)
        assert match.status == MatchStatus.CLOSED_UNILATERALLY.value

    def test_i_triangoli_si_ricostruiscono_nell_ordine_del_girone(
        self, db_session, trio_chiuso, isolated_players
    ):
        from models.match.models import TrioMatch

        match_id, trio_id = trio_chiuso
        self._corregge(match_id, (1, 3, 2), isolated_players[4].id)

        trio = db_session.get(TrioMatch, trio_id)
        racks = sorted(trio.active_racks, key=lambda r: r.rack_number)
        assert len(racks) == trio.trio_config.total_played_racks
        for posizione, rack in enumerate(racks, start=1):
            primo, secondo, attende = trio.trio_config.get_matchup_for_rack(posizione)
            assert (rack.player1_id, rack.player2_id) == (
                trio.player_ids[primo],
                trio.player_ids[secondo],
            )
            assert rack.winner_id in (rack.player1_id, rack.player2_id)

    def test_la_traccia_dice_i_tre_numeri_di_prima_e_di_dopo(
        self, db_session, trio_chiuso, isolated_players
    ):
        match_id, _ = trio_chiuso
        traccia = self._corregge(
            match_id, (1, 3, 2), isolated_players[4].id, note="nomi scambiati"
        )

        assert (
            traccia.previous_player1_score,
            traccia.previous_player2_score,
            traccia.previous_player3_score,
        ) == (4, 2, 0)
        assert (
            traccia.new_player1_score,
            traccia.new_player2_score,
            traccia.new_player3_score,
        ) == (1, 3, 2)
        assert traccia.note == "nomi scambiati"

    def test_il_pari_in_testa_non_ha_vincitore(
        self, db_session, trio_chiuso, isolated_players
    ):
        """`SPECIFICHE.md` riga 164, anche per chi corregge."""
        from models.match.models import Match, TrioMatch

        match_id, trio_id = trio_chiuso
        self._corregge(match_id, (3, 3, 0), isolated_players[4].id)

        assert db_session.get(TrioMatch, trio_id).winner_id is None
        assert db_session.get(Match, match_id).winner_id is None

    @pytest.mark.parametrize(
        "punti",
        [(3, 2, 0), (5, 1, 0), (2, 2, 3), (-1, 4, 3)],
        ids=["somma-corta", "oltre-il-massimo", "somma-lunga", "negativo"],
    )
    def test_un_punteggio_impossibile_si_rifiuta(
        self, db_session, trio_chiuso, isolated_players, punti
    ):
        from models.match.models import TrioMatch

        match_id, trio_id = trio_chiuso
        with pytest.raises(ValueError):
            self._corregge(match_id, punti, isolated_players[4].id)
        assert db_session.get(TrioMatch, trio_id).player_racks_list == [4, 2, 0]

    def test_senza_il_terzo_numero_non_si_corregge(
        self, db_session, trio_chiuso, isolated_players
    ):
        match_id, _ = trio_chiuso
        with pytest.raises(ValueError):
            MatchCorrectionService.correct_result(
                match_id=match_id,
                player1_score=2,
                player2_score=4,
                corrected_by_id=isolated_players[4].id,
            )

    def test_il_turno_bloccato_blocca_anche_il_trio(
        self, db_session, trio_chiuso, gara_in_corso, isolated_players
    ):
        from models.match.models import Match

        db_session.add(
            Match(
                gara_id=gara_in_corso.id,
                round_number=2,
                player1_id=isolated_players[3].id,
                player2_id=isolated_players[4].id,
                status=MatchStatus.PENDING.value,
            )
        )
        db_session.commit()

        consentito, motivo = MatchCorrectionService.can_correct(trio_chiuso[0])
        assert not consentito
        assert motivo.strip()


def _partita_a_set(db_session, gara, giocatori, punteggi):
    """Una partita al 2 set, set al 5, chiusa dal direttore con `punteggi`."""
    from models.match.models import Match
    from models.match.set_models import Set

    p1, p2 = giocatori[3], giocatori[4]
    vinti = [sum(1 for a, b in punteggi if a > b), sum(1 for a, b in punteggi if b > a)]
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        is_multi_set=True,
        match_distance=2,
        is_race_to_sets=True,
        player1_score=vinti[0],
        player2_score=vinti[1],
        winner_id=p1.id if vinti[0] > vinti[1] else p2.id,
        current_set_number=len(punteggi),
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    db_session.add(match)
    db_session.flush()
    for numero, (a, b) in enumerate(punteggi, start=1):
        db_session.add(
            Set(
                match_id=match.id,
                set_number=numero,
                distance=5,
                is_race_to=True,
                player1_racks=a,
                player2_racks=b,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
                winner_id=p1.id if a > b else p2.id,
            )
        )
    db_session.commit()
    return match.id


class TestLaPartitaASetSiCorregge:
    """La partita a set si corregge set per set: set vinti e vincitore seguono."""

    @staticmethod
    def _corregge(match_id, sets, chi, note=None):
        vinti1 = sum(1 for a, b in sets if a > b)
        vinti2 = sum(1 for a, b in sets if b > a)
        return MatchCorrectionService.correct_result(
            match_id=match_id,
            player1_score=vinti1,
            player2_score=vinti2,
            sets=sets,
            corrected_by_id=chi,
            note=note,
        )

    @staticmethod
    def _sets(match_id):
        from models.match.set_models import Set

        return [
            (s.set_number, s.player1_racks, s.player2_racks, s.winner_id, s.status)
            for s in Set.query.filter_by(match_id=match_id).order_by(Set.set_number)
        ]

    def test_la_partita_a_set_chiusa_si_puo_correggere(
        self, db_session, gara_in_corso, isolated_players
    ):
        match_id = _partita_a_set(
            db_session, gara_in_corso, isolated_players, [(5, 1), (5, 3)]
        )
        consentito, motivo = MatchCorrectionService.can_correct(match_id)
        assert consentito, motivo

    def test_un_set_in_piu_cambia_il_vincitore(
        self, db_session, gara_in_corso, isolated_players
    ):
        from models.match.models import Match

        p1, p2 = isolated_players[3], isolated_players[4]
        match_id = _partita_a_set(
            db_session, gara_in_corso, isolated_players, [(5, 1), (5, 3)]
        )
        self._corregge(match_id, [(5, 1), (3, 5), (2, 5)], isolated_players[0].id)

        match = db_session.get(Match, match_id)
        assert (match.player1_score, match.player2_score) == (1, 2)
        assert match.winner_id == p2.id
        assert match.status == MatchStatus.CLOSED_UNILATERALLY.value
        chiuso = MatchStatus.CLOSED_UNILATERALLY.value
        assert self._sets(match_id) == [
            (1, 5, 1, p1.id, chiuso),
            (2, 3, 5, p2.id, chiuso),
            (3, 2, 5, p2.id, chiuso),
        ]

    def test_un_set_in_meno(self, db_session, gara_in_corso, isolated_players):
        from models.match.models import Match

        match_id = _partita_a_set(
            db_session, gara_in_corso, isolated_players, [(5, 1), (3, 5), (5, 4)]
        )
        self._corregge(match_id, [(5, 1), (5, 4)], isolated_players[0].id)

        match = db_session.get(Match, match_id)
        assert (match.player1_score, match.player2_score) == (2, 0)
        assert match.winner_id == isolated_players[3].id
        assert [s[:3] for s in self._sets(match_id)] == [(1, 5, 1), (2, 5, 4)]

    def test_la_traccia_dice_i_set_di_prima_e_di_dopo(
        self, db_session, gara_in_corso, isolated_players
    ):
        match_id = _partita_a_set(
            db_session, gara_in_corso, isolated_players, [(5, 1), (5, 3)]
        )
        traccia = self._corregge(
            match_id, [(5, 1), (3, 5), (2, 5)], isolated_players[0].id
        )

        assert (traccia.previous_player1_score, traccia.previous_player2_score) == (
            2,
            0,
        )
        assert (traccia.new_player1_score, traccia.new_player2_score) == (1, 2)
        assert traccia.previous_detail == "5–1 · 5–3"
        assert traccia.new_detail == "5–1 · 3–5 · 2–5"

    def test_la_classifica_somma_i_triangoli_dei_set_corretti(
        self, db_session, gara_in_corso, isolated_players
    ):
        from models.classification.score_aggregator import ScoreAggregator

        match_id = _partita_a_set(
            db_session, gara_in_corso, isolated_players, [(5, 1), (5, 3)]
        )
        self._corregge(match_id, [(5, 1), (3, 5), (2, 5)], isolated_players[0].id)

        voci = {
            v.player_id: v
            for v in ScoreAggregator().aggregate_round_scores(gara_in_corso.id, 1)
        }
        primo, secondo = voci[isolated_players[3].id], voci[isolated_players[4].id]
        assert (primo.matches_won, secondo.matches_won) == (0, 1)
        assert (primo.racks_won, secondo.racks_won) == (10, 11)
        assert (primo.sets_won, secondo.sets_won) == (1, 2)

    @pytest.mark.parametrize(
        "sets",
        [
            [(5, 1), (4, 3)],
            [(5, 1), (5, 3), (5, 0)],
            [(5, 1)],
            [(5, 5), (5, 1)],
            [],
            [(-1, 5), (5, 1), (5, 2)],
        ],
        ids=[
            "set-non-finito",
            "set-dopo-la-decisione",
            "partita-non-decisa",
            "tutti-e-due-al-traguardo",
            "nessun-set",
            "negativo",
        ],
    )
    def test_una_partita_impossibile_si_rifiuta(
        self, db_session, gara_in_corso, isolated_players, sets
    ):
        match_id = _partita_a_set(
            db_session, gara_in_corso, isolated_players, [(5, 1), (5, 3)]
        )
        with pytest.raises(ValueError):
            self._corregge(match_id, sets, isolated_players[0].id)
        assert [s[:3] for s in self._sets(match_id)] == [(1, 5, 1), (2, 5, 3)]

    def test_senza_i_set_non_si_corregge(
        self, db_session, gara_in_corso, isolated_players
    ):
        match_id = _partita_a_set(
            db_session, gara_in_corso, isolated_players, [(5, 1), (5, 3)]
        )
        with pytest.raises(ValueError):
            MatchCorrectionService.correct_result(
                match_id=match_id,
                player1_score=0,
                player2_score=2,
                corrected_by_id=isolated_players[0].id,
            )

    def test_il_turno_bloccato_blocca_anche_la_partita_a_set(
        self, db_session, gara_in_corso, isolated_players
    ):
        from models.match.models import Match

        match_id = _partita_a_set(
            db_session, gara_in_corso, isolated_players, [(5, 1), (5, 3)]
        )
        db_session.add(
            Match(
                gara_id=gara_in_corso.id,
                round_number=2,
                player1_id=isolated_players[5].id,
                player2_id=isolated_players[6].id,
                status=MatchStatus.PENDING.value,
            )
        )
        db_session.commit()

        consentito, motivo = MatchCorrectionService.can_correct(match_id)
        assert not consentito
        assert motivo.strip()
