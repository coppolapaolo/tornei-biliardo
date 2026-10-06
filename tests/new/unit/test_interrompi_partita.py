"""«Interrompi partita»: il direttore chiude a tempo (ADR-077).

Le regole, da `models/match/chiusura.py`:

* si interrompe una partita **in gioco** con un limite di tempo; non a set,
  trio o X; anche prima dello scadere, e il foglio dice quanto mancava;
* chi è avanti vince; a parità c'è **pareggio dove il pareggio è ammesso** —
  fuori dal tabellone — e nel tabellone il direttore indica chi passa;
* la partita interrotta porta `closed_on_time`; una partita arrivata alla
  distanza, anche a tempo scaduto, si chiude come sempre e **non** lo porta;
* una partita interrotta si corregge anche sotto la distanza.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta

import pytest

from models.base import db
from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _utente(ruolo=UserRole.PLAYER.value):
    sigla = uuid.uuid4().hex[:8]
    u = User(username=f"ip_{sigla}", email=f"ip_{sigla}@test.com", role=ruolo)
    u.set_password("pwd")
    db.session.add(u)
    db.session.commit()
    return u


def _gara(strategia="round_robin", minuti=30, **kw):
    direttore = _utente(UserRole.DIRECTOR.value)
    base = dict(
        number=1,
        name=f"G {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=1),
        time=time(20, 0),
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        rounds_count=3,
        current_round=1,
        min_participants=2,
        matchmaking_strategy=strategia,
        status=GaraStatus.PLAYING.value,
        time_limit_minutes=minuti,
        director_id=direttore.id,
    )
    base.update(kw)
    gara = Gara(**base)
    db.session.add(gara)
    db.session.commit()
    from models.user.models import DirectorAssignment

    db.session.add(
        DirectorAssignment(
            user_id=direttore.id,
            entity_type="gara",
            entity_id=gara.id,
            assigned_by_id=direttore.id,
        )
    )
    db.session.commit()
    return gara, direttore


def _partita(gara, p1=0, p2=0, **kw):
    a, b = _utente(), _utente()
    base = dict(
        gara_id=gara.id,
        round_number=1,
        player1_id=a.id,
        player2_id=b.id,
        status=MatchStatus.PLAYING.value,
        match_distance=gara.distance,
        table_assignment="1",
        player1_score=p1,
        player2_score=p2,
    )
    base.update(kw)
    match = Match(**base)
    db.session.add(match)
    db.session.commit()
    return match


# ---------------------------------------------------------------------------
# La regola: si può interrompere? con quale esito?
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLaRegola:
    def test_chi_e_avanti_vince(self, db_session):
        from models.match import chiusura

        gara, _ = _gara()
        match = _partita(gara, 2, 1)
        esito = chiusura.esito(match)
        assert esito.vincitore_id == match.player1_id
        assert not esito.pareggio and not esito.serve_chi_passa

    def test_pari_nel_girone_e_pareggio(self, db_session):
        from models.match import chiusura

        gara, _ = _gara()
        esito = chiusura.esito(_partita(gara, 1, 1))
        assert esito.pareggio and esito.vincitore_id is None
        assert not esito.serve_chi_passa

    def test_pari_nel_tabellone_serve_chi_passa(self, db_session):
        from models.match import chiusura

        gara, _ = _gara(strategia="direct_elimination")
        esito = chiusura.esito(_partita(gara, 1, 1))
        assert esito.serve_chi_passa and not esito.pareggio

    @pytest.mark.parametrize("strategia", ["round_robin", "amalfi", "random"])
    def test_pareggio_ammesso_fuori_dal_tabellone(self, db_session, strategia):
        from models.match import chiusura

        gara, _ = _gara(strategia=strategia)
        assert chiusura.pareggio_ammesso(_partita(gara))

    @pytest.mark.parametrize("strategia", ["direct_elimination", "double_knockout"])
    def test_mai_nel_tabellone(self, db_session, strategia):
        from models.match import chiusura

        gara, _ = _gara(strategia=strategia)
        assert not chiusura.pareggio_ammesso(_partita(gara))

    def test_prima_dello_scadere_dice_quanto_manca(self, db_session):
        from models.match import chiusura

        gara, _ = _gara()
        match = _partita(gara, timer_started_at=datetime(2026, 10, 6, 20, 0))
        esito = chiusura.esito(match, adesso=datetime(2026, 10, 6, 20, 24))
        assert esito.secondi_mancanti == 6 * 60
        dopo = chiusura.esito(match, adesso=datetime(2026, 10, 6, 20, 40))
        assert dopo.secondi_mancanti is None

    def test_cosa_non_si_interrompe(self, db_session):
        from models.match import chiusura

        senza, _ = _gara(minuti=0)
        assert chiusura.motivo_non_interrompibile(_partita(senza))
        gara, _ = _gara()
        assert chiusura.motivo_non_interrompibile(
            _partita(gara, status=MatchStatus.PENDING.value, table_assignment=None)
        )
        assert chiusura.motivo_non_interrompibile(
            _partita(gara, status=MatchStatus.CLOSED_UNILATERALLY.value)
        )
        assert chiusura.motivo_non_interrompibile(
            _partita(gara, is_multi_set=True, match_distance=2)
        )
        assert chiusura.motivo_non_interrompibile(_partita(gara)) is None


# ---------------------------------------------------------------------------
# Il servizio
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInterrompi:
    def test_chiude_a_tempo_col_vincitore(self, db_session):
        from models.match.match_service import MatchService

        gara, direttore = _gara()
        match = _partita(gara, 2, 1)
        MatchService.interrompi_partita(match.id, direttore)
        chiusa = db.session.get(Match, match.id)
        assert chiusa.status == MatchStatus.CLOSED_UNILATERALLY.value
        assert chiusa.closed_on_time is True
        assert chiusa.winner_id == match.player1_id
        assert (chiusa.player1_score, chiusa.player2_score) == (2, 1)

    def test_pareggio_nel_girone(self, db_session):
        from models.match.match_service import MatchService

        gara, direttore = _gara()
        match = _partita(gara, 1, 1)
        MatchService.interrompi_partita(match.id, direttore)
        chiusa = db.session.get(Match, match.id)
        assert MatchStatus.is_finished(chiusa.status)
        assert chiusa.winner_id is None and chiusa.closed_on_time

    def test_tabellone_pari_senza_chi_passa_si_rifiuta(self, db_session):
        from models.exceptions import ValidationError
        from models.match.match_service import MatchService

        gara, direttore = _gara(strategia="direct_elimination")
        match = _partita(gara, 1, 1)
        with pytest.raises(ValidationError):
            MatchService.interrompi_partita(match.id, direttore)
        assert db.session.get(Match, match.id).status == MatchStatus.PLAYING.value

    def test_tabellone_pari_passa_chi_indica_il_direttore(self, db_session):
        from models.match.match_service import MatchService

        gara, direttore = _gara(strategia="direct_elimination")
        match = _partita(gara, 1, 1)
        MatchService.interrompi_partita(
            match.id, direttore, chi_passa_id=match.player2_id
        )
        chiusa = db.session.get(Match, match.id)
        assert chiusa.winner_id == match.player2_id and chiusa.closed_on_time

    def test_chi_passa_deve_giocare_la_partita(self, db_session):
        from models.exceptions import ValidationError
        from models.match.match_service import MatchService

        gara, direttore = _gara(strategia="direct_elimination")
        match = _partita(gara, 1, 1)
        with pytest.raises(ValidationError):
            MatchService.interrompi_partita(
                match.id, direttore, chi_passa_id=direttore.id
            )

    def test_un_giocatore_non_interrompe(self, db_session):
        from models.exceptions import PermissionDeniedError
        from models.match.match_service import MatchService

        gara, _ = _gara()
        match = _partita(gara, 2, 1)
        with pytest.raises(PermissionDeniedError):
            MatchService.interrompi_partita(match.id, match.player1)
        assert db.session.get(Match, match.id).status == MatchStatus.PLAYING.value

    def test_senza_limite_non_si_interrompe(self, db_session):
        from models.exceptions import ValidationError
        from models.match.match_service import MatchService

        gara, direttore = _gara(minuti=0)
        match = _partita(gara, 2, 1)
        with pytest.raises(ValidationError):
            MatchService.interrompi_partita(match.id, direttore)

    def test_alla_distanza_a_tempo_scaduto_nessun_segno(self, db_session):
        """Il segno vuol dire «interrotta prima della distanza», non «ha
        sforato il tempo»: arrivata al 3 dopo lo scadere, si chiude come
        sempre e `closed_on_time` resta falso."""
        from models.match.validation_service import MatchValidationService

        gara, _ = _gara()
        match = _partita(gara, 3, 1, timer_started_at=datetime(2000, 1, 1, 20, 0))
        assert match.is_time_expired
        MatchValidationService.validate_and_complete(match.id)
        chiusa = db.session.get(Match, match.id)
        assert MatchStatus.is_finished(chiusa.status)
        assert chiusa.closed_on_time is False
        assert chiusa.winner_id == match.player1_id

    def test_la_validazione_rifiuta_ancora_sotto_la_distanza(self, db_session):
        """Solo «Interrompi» chiude sotto la distanza: la validazione no."""
        from models.match.validation_service import MatchValidationService

        gara, _ = _gara()
        match = _partita(gara, 2, 1)
        with pytest.raises(ValueError):
            MatchValidationService.validate_and_complete(match.id)


# ---------------------------------------------------------------------------
# Correggere una partita interrotta
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCorrezione:
    def _interrotta(self, strategia="round_robin", p1=2, p2=1, chi=None):
        from models.match.match_service import MatchService

        gara, direttore = _gara(strategia=strategia)
        match = _partita(gara, p1, p2)
        MatchService.interrompi_partita(match.id, direttore, chi_passa_id=chi)
        return db.session.get(Match, match.id), direttore

    def test_si_corregge_sotto_la_distanza(self, db_session):
        from models.match.correction_service import MatchCorrectionService

        match, direttore = self._interrotta()
        MatchCorrectionService.correct_result(match.id, 1, 2, direttore.id)
        corretta = db.session.get(Match, match.id)
        assert (corretta.player1_score, corretta.player2_score) == (1, 2)
        assert corretta.winner_id == match.player2_id
        assert corretta.closed_on_time is True

    def test_oltre_la_distanza_no(self, db_session):
        from models.match.correction_service import MatchCorrectionService

        match, direttore = self._interrotta()
        with pytest.raises(ValueError):
            MatchCorrectionService.correct_result(match.id, 4, 1, direttore.id)

    def test_corretta_alla_distanza_perde_il_segno(self, db_session):
        from models.match.correction_service import MatchCorrectionService

        match, direttore = self._interrotta()
        MatchCorrectionService.correct_result(match.id, 3, 1, direttore.id)
        assert db.session.get(Match, match.id).closed_on_time is False

    def test_una_partita_normale_resta_alla_distanza(self, db_session):
        from models.match.correction_service import MatchCorrectionService
        from models.match.validation_service import MatchValidationService

        gara, direttore = _gara()
        match = _partita(gara, 3, 1)
        MatchValidationService.validate_and_complete(match.id)
        with pytest.raises(ValueError):
            MatchCorrectionService.correct_result(match.id, 2, 1, direttore.id)

    def test_nel_tabellone_il_pari_tiene_chi_passa(self, db_session):
        from models.match.correction_service import MatchCorrectionService

        gara, direttore = _gara(strategia="direct_elimination")
        partita = _partita(gara, 2, 1)
        from models.match.match_service import MatchService

        MatchService.interrompi_partita(partita.id, direttore)
        # Corretta in un pari: chi passa resta chi aveva vinto.
        MatchCorrectionService.correct_result(partita.id, 1, 1, direttore.id)
        corretta = db.session.get(Match, partita.id)
        assert corretta.winner_id == partita.player1_id


# ---------------------------------------------------------------------------
# La classifica: chi passa nel tabellone conta come vittoria
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lo_score_aggregator_legge_chi_passa_sul_pari():
    from types import SimpleNamespace

    from models.classification.score_aggregator import ScoreAggregator

    match = SimpleNamespace(
        player1_id=1,
        player2_id=2,
        player1_score=1,
        player2_score=1,
        winner_id=2,
        is_multi_set=False,
        sets=[],
    )
    stats: dict = {}
    ScoreAggregator.__new__(ScoreAggregator)._process_regular_match(match, stats)
    assert stats[2]["matches_won"] == 1 and stats[1]["matches_lost"] == 1
