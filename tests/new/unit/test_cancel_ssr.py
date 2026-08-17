"""La fase di spareggio SSR si può annullare.

`awaiting_ssr` era uno stato a senso unico: ci si entrava con "Avvia SSR" e
l'unica uscita era "Termina Gara". Un director che si accorgeva di un
punteggio sbagliato durante lo spareggio non aveva modo di correggerlo —
il reset dei match è bloccato proprio perché la gara è in spareggio.

`cancel_ssr` chiude il cerchio: riporta la gara a `playing` e cancella i
punteggi SSR inseriti, perché modificare i match cambia la classifica e
quindi anche chi è a pari merito. Punteggi sopravvissuti all'annullamento
sarebbero riferiti a una classifica che non esiste più.
"""

from __future__ import annotations

from datetime import date

import pytest

from models.classification.models import GaraClassification
from models.competition.models import Gara, Inscription
from models.competition.round_manager import AdvancedRoundManager
from models.competition.spareggio_service import SpareggioService
from models.competition.state_service import StateService
from models.exceptions import InvalidTransitionError
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus


def _make_gara(db_session, status: str) -> Gara:
    """Gara Random (round lock sempre UNLOCKED) nello stato richiesto."""
    existing_count = db_session.query(Gara).count()
    gara = Gara(
        name=f"Cancel-SSR gara {existing_count + 1}",
        number=existing_count + 1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="random",
        status=status,
        is_race_to=True,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _add_completed_match(db_session, gara, player1, player2) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=player1.id,
        player2_id=player2.id,
        round_number=1,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        player1_score=5,
        player2_score=3,
        winner_id=player1.id,
    )
    db_session.add(match)
    db_session.add(Inscription(gara_id=gara.id, user_id=player1.id))
    db_session.add(Inscription(gara_id=gara.id, user_id=player2.id))
    db_session.flush()
    return match


def _add_ssr_score(db_session, gara, player, score: int) -> GaraClassification:
    gc = GaraClassification(
        gara_id=gara.id,
        user_id=player.id,
        position=1,
        matches_won=1,
        racks_won=5,
        rack_difference=2,
        spot_shot_wins=score,
        tiebreaker_resolved=True,
    )
    db_session.add(gc)
    db_session.flush()
    return gc


@pytest.mark.unit
class TestCancelSsrTransition:
    def test_cancel_ssr_returns_to_playing(self, db_session, isolated_players):
        gara = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        db_session.commit()

        StateService.cancel_ssr(gara)

        assert gara.status == GaraStatus.PLAYING.value

    def test_cancel_ssr_rejected_while_playing(self, db_session, isolated_players):
        """Non c'è nessuno spareggio da annullare."""
        gara = _make_gara(db_session, GaraStatus.PLAYING.value)
        db_session.commit()

        with pytest.raises(InvalidTransitionError):
            StateService.cancel_ssr(gara)

    def test_cancel_ssr_rejected_when_completed(self, db_session, isolated_players):
        """A gara conclusa i risultati sono definitivi."""
        gara = _make_gara(db_session, GaraStatus.COMPLETED.value)
        db_session.commit()

        with pytest.raises(InvalidTransitionError):
            StateService.cancel_ssr(gara)

        assert gara.status == GaraStatus.COMPLETED.value


@pytest.mark.unit
class TestCancelSsrClearsScores:
    def test_cancel_ssr_clears_ssr_scores(self, db_session, isolated_players):
        gara = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        p1, p2 = isolated_players[:2]
        _add_ssr_score(db_session, gara, p1, 7)
        _add_ssr_score(db_session, gara, p2, 4)
        db_session.commit()

        StateService.cancel_ssr(gara)

        rows = db_session.query(GaraClassification).filter_by(gara_id=gara.id).all()
        assert rows, "le righe di classifica non vanno cancellate"
        for row in rows:
            assert row.spot_shot_wins == 0
            assert row.tiebreaker_resolved is False

    def test_clear_ssr_scores_leaves_other_gare_untouched(
        self, db_session, isolated_players
    ):
        """Il filtro per gara_id è l'unica cosa che separa due spareggi."""
        gara = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        other = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        p1 = isolated_players[0]
        _add_ssr_score(db_session, gara, p1, 7)
        _add_ssr_score(db_session, other, p1, 9)
        db_session.commit()

        SpareggioService.clear_ssr_scores(gara.id)
        db_session.flush()

        untouched = (
            db_session.query(GaraClassification).filter_by(gara_id=other.id).one()
        )
        assert untouched.spot_shot_wins == 9
        assert untouched.tiebreaker_resolved is True


@pytest.mark.unit
class TestCancelSsrReopensModification:
    def test_match_modifiable_again_after_cancel_ssr(
        self, db_session, isolated_players
    ):
        """Il motivo per cui esiste il pulsante: durante l'SSR il reset è
        bloccato, quindi senza annullamento l'errore non è correggibile."""
        gara = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        p1, p2 = isolated_players[:2]
        match = _add_completed_match(db_session, gara, p1, p2)
        db_session.commit()

        blocked, reason = AdvancedRoundManager.can_modify_match(match.id)
        assert blocked is False, "precondizione: durante l'SSR il reset è bloccato"
        assert "spareggio" in reason.lower()

        StateService.cancel_ssr(gara)
        db_session.commit()

        can_modify, reason_after = AdvancedRoundManager.can_modify_match(match.id)
        assert (
            can_modify is True
        ), f"dopo l'annullamento deve essere modificabile: {reason_after}"

    def test_cancel_round_allowed_again_after_cancel_ssr(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        p1, p2 = isolated_players[:2]
        _add_completed_match(db_session, gara, p1, p2)
        db_session.commit()

        StateService.cancel_ssr(gara)
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        # Il turno ha risultati reali: resta bloccato, ma non più dallo stato.
        assert "spareggio" not in message.lower()
        assert success is False
        assert "risultati parziali" in message.lower()
