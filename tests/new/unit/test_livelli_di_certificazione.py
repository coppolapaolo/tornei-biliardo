"""I livelli di certificazione delle partite (ADR-083).

Una partita di torneo l'ha garantita un direttore; una sfida confermata da
entrambi l'hanno garantita i due giocatori; una sfida firmata da uno solo l'ha
garantita solo lui. Le prestazioni di un giocatore si leggono in tre viste
cumulative — Tornei, Confermate, Tutte — e il livello di ogni partita si decide
in un posto solo: ``models/certificazione.py``.

Casi d'uso in ``docs/usecases/sfide-e-certificazione.md`` (UC4–UC8).
"""

from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.certificazione import (
    Livello,
    Vista,
    esito_dichiarato,
    livello_di_partita,
    livello_di_sfida,
)
from models.individual_match.match_models import IndividualMatch
from models.match.models import Match
from models.player.history_service import HistoryFilters, PlayerHistoryService
from models.status_enum import Discipline, MatchStatus


def _sfida(status=MatchStatus.IN_PROGRESS, p1=False, p2=False, s1=3, s2=1, **kw):
    return IndividualMatch(
        player1_id=1,
        player2_id=2,
        status=status,
        player1_confirmed=p1,
        player2_confirmed=p2,
        player1_score=s1,
        player2_score=s2,
        distance=3,
        is_race_to=True,
        **kw,
    )


class TestLivelloDellaSfida:
    def test_confermata_da_entrambi(self):
        sfida = _sfida(MatchStatus.CONFIRMED_BY_BOTH, p1=True, p2=True)
        assert livello_di_sfida(sfida) is Livello.CONFERMATA

    def test_il_forfait_e_confermato(self):
        """Chi abbandona ammette la sconfitta (decisione del 2026-10-06)."""
        sfida = _sfida(MatchStatus.CLOSED_UNILATERALLY, s1=1, s2=3, winner_id=2)
        assert livello_di_sfida(sfida) is Livello.CONFERMATA

    @pytest.mark.parametrize("p1,p2", [(True, False), (False, True)])
    def test_firmata_da_uno_solo_e_in_attesa(self, p1, p2):
        assert livello_di_sfida(_sfida(p1=p1, p2=p2)) is Livello.IN_ATTESA

    @pytest.mark.parametrize(
        "status",
        [MatchStatus.SCHEDULED, MatchStatus.IN_PROGRESS, MatchStatus.CANCELLED],
    )
    def test_senza_firme_non_ha_livello(self, status):
        """Una sfida in corso, programmata o annullata non dice niente di
        nessuno: i due stanno ancora giocando, o non hanno giocato."""
        assert livello_di_sfida(_sfida(status)) is None


class TestLivelloDellaPartitaDiTorneo:
    @pytest.mark.parametrize("status", MatchStatus.finished_values())
    def test_conclusa_e_torneo(self, status):
        assert livello_di_partita(Match(status=status)) is Livello.TORNEO

    @pytest.mark.parametrize(
        "status", [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
    )
    def test_non_conclusa_non_ha_livello(self, status):
        assert livello_di_partita(Match(status=status)) is None


class TestLeVisteSonoCumulative:
    def test_tornei(self):
        assert Vista.TORNEI.livelli == frozenset({Livello.TORNEO})

    def test_confermate(self):
        assert Vista.CONFERMATE.livelli == frozenset(
            {Livello.TORNEO, Livello.CONFERMATA}
        )

    def test_tutte(self):
        assert Vista.TUTTE.livelli == frozenset(Livello)

    def test_ogni_vista_contiene_la_precedente(self):
        viste = list(Vista)
        for piu_stretta, piu_larga in zip(viste, viste[1:]):
            assert piu_stretta.livelli < piu_larga.livelli


class TestEsitoDichiarato:
    """Una sfida in attesa non ha ancora ``winner_id``: lo scrive la seconda
    firma. Il risultato che il firmatario ha dichiarato sta nel punteggio."""

    def test_in_attesa_vince_chi_e_avanti(self):
        assert esito_dichiarato(_sfida(p1=True, s1=1, s2=3)) == 2

    def test_in_attesa_in_parita_e_pareggio(self):
        assert esito_dichiarato(_sfida(p1=True, s1=2, s2=2)) is None

    def test_confermata_vale_il_vincitore_scritto(self):
        sfida = _sfida(MatchStatus.CONFIRMED_BY_BOTH, p1=True, p2=True, winner_id=1)
        assert esito_dichiarato(sfida) == 1


# ──────────────────────────────────────────────────────────────────────────
# Storico e statistiche per vista (UC4, UC5, UC7)
# ──────────────────────────────────────────────────────────────────────────


def _salva(p1, p2, **kw):
    valori = dict(
        player1_id=p1.id,
        player2_id=p2.id,
        location="Sala Test",
        scheduled_at=utc_now() - timedelta(hours=2),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
    )
    valori.update(kw)
    sfida = IndividualMatch(**valori)
    db.session.add(sfida)
    db.session.commit()
    return sfida


@pytest.fixture
def storico(app, db_session, isolated_players):
    """Paolo contro Pietro: una per ogni livello, e due senza livello."""
    paolo, pietro = isolated_players[:2]
    vinta_confermata = _salva(
        paolo,
        pietro,
        status=MatchStatus.CONFIRMED_BY_BOTH,
        player1_score=3,
        player2_score=1,
        player1_confirmed=True,
        player2_confirmed=True,
        winner_id=paolo.id,
    )
    forfait = _salva(
        paolo,
        pietro,
        status=MatchStatus.CLOSED_UNILATERALLY,
        player1_score=1,
        player2_score=3,
        winner_id=pietro.id,
    )
    in_attesa = _salva(
        paolo,
        pietro,
        status=MatchStatus.IN_PROGRESS,
        player1_score=3,
        player2_score=0,
        player1_confirmed=True,
        player1_confirmed_at=utc_now(),
    )
    _salva(paolo, pietro, status=MatchStatus.IN_PROGRESS, player1_score=1)
    _salva(paolo, pietro, status=MatchStatus.CANCELLED)
    return paolo, pietro, vinta_confermata, forfait, in_attesa


class TestStoricoPerVista:
    def test_la_vista_predefinita_e_quella_di_sempre(self, storico):
        paolo, _, vinta, forfait, _ = storico

        pagina, stats = PlayerHistoryService.get_unified_match_history(
            paolo.id, HistoryFilters()
        )

        assert {v.match_id for v in pagina.items} == {vinta.id, forfait.id}
        assert (stats.won_matches, stats.lost_matches) == (1, 1)

    def test_tutte_aggiunge_la_sfida_in_attesa_col_suo_esito(self, storico):
        paolo, _, _, _, in_attesa = storico

        pagina, stats = PlayerHistoryService.get_unified_match_history(
            paolo.id, HistoryFilters(), vista=Vista.TUTTE
        )

        voce = next(v for v in pagina.items if v.match_id == in_attesa.id)
        assert voce.in_attesa
        # `winner_id` non c'è ancora: l'esito è quello dichiarato da chi ha
        # firmato, non un pareggio.
        assert voce.outcome == "won"
        assert (stats.won_matches, stats.lost_matches) == (2, 1)

    def test_le_sfide_non_entrano_nella_vista_tornei(self, storico):
        paolo = storico[0]

        _, stats = PlayerHistoryService.get_unified_match_history(
            paolo.id, HistoryFilters(), vista=Vista.TORNEI
        )

        assert stats.total_matches == 0

    def test_le_tre_viste_dalle_stesse_voci(self, storico):
        paolo = storico[0]
        pagina, _ = PlayerHistoryService.get_unified_match_history(
            paolo.id, HistoryFilters(), per_page=100, vista=Vista.TUTTE
        )

        per_vista = PlayerHistoryService.stats_per_vista(pagina.items)

        assert [per_vista[v].total_matches for v in Vista] == [0, 2, 3]

    def test_per_l_avversario_la_sfida_in_attesa_e_persa(self, storico):
        _, pietro, _, _, in_attesa = storico

        pagina, _ = PlayerHistoryService.get_unified_match_history(
            pietro.id, HistoryFilters(result="lost"), vista=Vista.TUTTE
        )

        assert in_attesa.id in {v.match_id for v in pagina.items}

    def test_i_pareggi_si_contano(self, app, db_session, isolated_players):
        paolo, pietro = isolated_players[:2]
        _salva(
            paolo,
            pietro,
            status=MatchStatus.CONFIRMED_BY_BOTH,
            distance=4,
            is_race_to=False,
            player1_score=2,
            player2_score=2,
            player1_confirmed=True,
            player2_confirmed=True,
        )

        _, stats = PlayerHistoryService.get_unified_match_history(
            paolo.id, HistoryFilters()
        )

        assert stats.tied_matches == 1


# ──────────────────────────────────────────────────────────────────────────
# L'ELO della vista «Tutte» (UC4, UC5, UC7, UC9)
# ──────────────────────────────────────────────────────────────────────────


def _righe(sfida_id, sistema):
    from models.rating.models import MatchRatingHistory

    return MatchRatingHistory.query.filter_by(
        individual_match_id=sfida_id, rating_system=sistema
    ).count()


def _rating(user_id, sistema):
    from models.rating.models import PlayerRating

    riga = PlayerRating.get_user_rating(user_id, sistema)
    return None if riga is None else round(riga.rating_value, 6)


def _pronta(p1, p2, **kw):
    """Una sfida «al 3» finita 3-1, che nessuno ha ancora firmato."""
    valori = dict(status=MatchStatus.IN_PROGRESS, player1_score=3, player2_score=1)
    valori.update(kw)
    return _salva(p1, p2, **valori)


class TestEloDiTutte:
    def test_si_muove_alla_prima_firma(self, app, db_session, isolated_players):
        from models.individual_match.match_lifecycle_service import (
            MatchLifecycleService,
        )
        from models.rating.models import RatingSystem

        paolo, pietro = isolated_players[:2]
        sfida = _pronta(paolo, pietro)

        MatchLifecycleService.confirm_match_result(sfida.id, paolo.id)

        assert _righe(sfida.id, RatingSystem.ELO_ALL) == 2
        assert _righe(sfida.id, RatingSystem.ELO_GLOBAL) == 0
        assert _rating(paolo.id, RatingSystem.ELO_ALL) > _rating(
            pietro.id, RatingSystem.ELO_ALL
        )

    def test_la_seconda_firma_non_la_conta_due_volte(
        self, app, db_session, isolated_players
    ):
        from models.individual_match.match_lifecycle_service import (
            MatchLifecycleService,
        )
        from models.rating.models import RatingSystem

        paolo, pietro = isolated_players[:2]
        sfida = _pronta(paolo, pietro)
        MatchLifecycleService.confirm_match_result(sfida.id, paolo.id)
        prima = _rating(paolo.id, RatingSystem.ELO_ALL)

        MatchLifecycleService.confirm_match_result(sfida.id, pietro.id)

        assert _righe(sfida.id, RatingSystem.ELO_ALL) == 2
        assert _righe(sfida.id, RatingSystem.ELO_GLOBAL) == 2
        assert _rating(paolo.id, RatingSystem.ELO_ALL) == prima

    def test_il_rifiuto_la_toglie_come_se_non_ci_fosse_mai_stata(
        self, app, db_session, isolated_players
    ):
        from models.individual_match.match_lifecycle_service import (
            MatchLifecycleService,
        )
        from models.rating.calculation_service import RatingCalculationService
        from models.rating.models import RatingSystem

        paolo, pietro, gianni = isolated_players[:3]
        # Una sfida già in conto prima, perché togliere quella dopo non sia
        # banalmente «tornare a zero».
        vecchia = _pronta(paolo, gianni)
        MatchLifecycleService.confirm_match_result(vecchia.id, paolo.id)
        sfida = _pronta(paolo, pietro)
        MatchLifecycleService.confirm_match_result(sfida.id, paolo.id)

        MatchLifecycleService.reject_match_result(sfida.id, pietro.id)

        assert _righe(sfida.id, RatingSystem.ELO_ALL) == 0
        dopo = [_rating(u.id, RatingSystem.ELO_ALL) for u in (paolo, pietro, gianni)]
        RatingCalculationService.recalculate_all_elo_all()
        db.session.commit()
        da_zero = [_rating(u.id, RatingSystem.ELO_ALL) for u in (paolo, pietro, gianni)]
        assert dopo == da_zero

    def test_il_forfait_esce_dall_elo(self, app, db_session, isolated_players):
        from models.individual_match.match_lifecycle_service import (
            MatchLifecycleService,
        )
        from models.rating.models import RatingSystem

        paolo, pietro = isolated_players[:2]
        sfida = _pronta(paolo, pietro)
        MatchLifecycleService.confirm_match_result(sfida.id, paolo.id)

        MatchLifecycleService.forfeit_match(sfida.id, pietro.id)

        for sistema in RatingSystem:
            assert _righe(sfida.id, sistema) == 0

    def test_il_pareggio_non_muove_l_elo(self, app, db_session, isolated_players):
        from models.individual_match.match_lifecycle_service import (
            MatchLifecycleService,
        )
        from models.rating.models import RatingSystem

        paolo, pietro = isolated_players[:2]
        sfida = _pronta(
            paolo,
            pietro,
            distance=4,
            is_race_to=False,
            player1_score=2,
            player2_score=2,
        )

        MatchLifecycleService.confirm_match_result(sfida.id, paolo.id)
        MatchLifecycleService.confirm_match_result(sfida.id, pietro.id)

        assert _righe(sfida.id, RatingSystem.ELO_ALL) == 0
        assert _righe(sfida.id, RatingSystem.ELO_GLOBAL) == 0

    def test_il_ricalcolo_da_zero_ritrova_le_sfide_in_attesa(
        self, app, db_session, isolated_players
    ):
        """UC9: il primo calcolo in produzione è un ricalcolo da zero."""
        from models.rating.calculation_service import RatingCalculationService
        from models.rating.models import RatingSystem

        paolo, pietro = isolated_players[:2]
        _pronta(paolo, pietro, player1_confirmed=True, player1_confirmed_at=utc_now())
        _pronta(paolo, pietro)  # senza firme: non conta

        conti = RatingCalculationService.recalculate_all_elo_all()
        db.session.commit()

        assert conti["processed"] == 1
        assert _rating(paolo.id, RatingSystem.ELO_ALL) is not None
        assert _rating(paolo.id, RatingSystem.ELO_GLOBAL) is None

    def test_il_ricalcolo_dell_elo_globale_salta_i_pareggi(
        self, app, db_session, isolated_players
    ):
        """L'evento della seconda firma salta i pareggi; il ricalcolo da zero
        li contava. Ora decide per entrambi `sfida_conta_per_elo`."""
        from models.rating.calculation_service import RatingCalculationService
        from models.rating.models import RatingSystem

        paolo, pietro = isolated_players[:2]
        _salva(
            paolo,
            pietro,
            status=MatchStatus.CONFIRMED_BY_BOTH,
            distance=4,
            is_race_to=False,
            player1_score=2,
            player2_score=2,
            player1_confirmed=True,
            player2_confirmed=True,
        )

        RatingCalculationService.recalculate_all_elo_global()
        db.session.commit()

        assert _rating(paolo.id, RatingSystem.ELO_GLOBAL) is None

    def test_se_il_rating_fallisce_la_firma_resta(
        self, app, db_session, isolated_players, monkeypatch
    ):
        """Il rating è da mostrare: un suo errore non deve far perdere la
        firma del giocatore. Il lavoro gira in un savepoint."""
        from models.individual_match.match_lifecycle_service import (
            MatchLifecycleService,
        )
        from models.rating import elo_tutte

        def guasto(_ids):
            raise RuntimeError("rating rotto")

        monkeypatch.setattr(elo_tutte, "sincronizza", guasto)
        paolo, pietro = isolated_players[:2]
        sfida = _pronta(paolo, pietro)

        MatchLifecycleService.confirm_match_result(sfida.id, paolo.id)

        db.session.expire_all()
        assert db.session.get(IndividualMatch, sfida.id).player1_confirmed is True


class TestRunoutPerVista:
    """UC8: i triangoli chiusi in un turno contano come la loro partita."""

    @staticmethod
    def _runout(sfida, vincitore):
        from models.individual_match.match_models import IndividualRack

        db.session.add(
            IndividualRack(
                match_id=sfida.id,
                rack_number=1,
                winner_id=vincitore.id,
                break_player_id=vincitore.id,
                is_run_out=True,
            )
        )
        db.session.commit()

    def test_seguono_la_firma(self, app, db_session, isolated_players):
        from models.user.runout_stats import runout_summary

        paolo, pietro = isolated_players[:2]
        senza_firme = _pronta(paolo, pietro)
        self._runout(senza_firme, paolo)
        in_attesa = _pronta(
            paolo, pietro, player1_confirmed=True, player1_confirmed_at=utc_now()
        )
        self._runout(in_attesa, paolo)

        conti = {v: runout_summary(paolo.id, vista=v)["total"] for v in Vista}

        assert conti == {Vista.TORNEI: 0, Vista.CONFERMATE: 0, Vista.TUTTE: 1}
