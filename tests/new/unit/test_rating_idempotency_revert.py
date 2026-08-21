"""Rating: idempotenza, revert e skip dei match con handicap.

Bug (review 2026-06-09, HIGH correttezza) — `calculation_service.py:39`:
`process_match_result` non era idempotente. Ogni MatchCompletedEvent ri-emesso
(reset→ricompletamento) o un recalc_elo su match già processati ri-applicava il
delta Elo e ri-incrementava games_played in modo cumulativo.

Fix: `match_rating_history` registra il delta per ogni (match, giocatore,
sistema). Idempotenza (skip se esiste già history) + revert su riapertura.

Feature (2026-06): i match "con handicap" (effective_has_handicap, ereditato
da gara/campionato) non aggiornano i rating.

Emendamento (ADR-049, 2026-08): l'handicap da solo non basta più a spegnere
l'Elo. Lo spegne la **differenza di categoria** — fra due giocatori della
stessa categoria l'handicap non è in gioco, quindi il risultato conta. Senza
categorie assegnate il comportamento resta quello di prima, ed è la proprietà
che rende il cambio innocuo sulle gare già esistenti.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models.base import db
from models.user.models import User
from models.competition.models import Gara
from models.match.models import Match
from models.rating.models import PlayerRating, RatingSystem, MatchRatingHistory
from models.rating.calculation_service import RatingCalculationService
from models.status_enum import GaraStatus, MatchStatus


def _user(suffix, name):
    u = User(
        username=f"{name}_{suffix}", email=f"{name}_{suffix}@test.com", role="player"
    )
    u.set_password("test123")
    return u


def _gara(suffix, **overrides):
    base = dict(
        number=1,
        name=f"Gara {suffix}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
    )
    base.update(overrides)
    return Gara(**base)


def _completed_match(gara_id, p1, p2, **overrides):
    base = dict(
        gara_id=gara_id,
        round_number=1,
        player1_id=p1,
        player2_id=p2,
        player1_score=5,
        player2_score=2,
        winner_id=p1,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    base.update(overrides)
    return Match(**base)


def _elo(user_id):
    obj = PlayerRating.get_user_rating(user_id, RatingSystem.ELO)
    return obj.rating_value if obj else None


@pytest.mark.unit
def test_process_is_idempotent(db_session):
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "elo_p1"), _user(suffix, "elo_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    match = _completed_match(_gara_id(suffix), p1.id, p2.id)
    db.session.add(match)
    db.session.flush()

    RatingCalculationService.process_match_result(match)
    db.session.flush()
    elo1_after_first = _elo(p1.id)
    elo2_after_first = _elo(p2.id)
    games1 = PlayerRating.get_user_rating(p1.id, RatingSystem.ELO).games_played

    # Vincitore sale sopra 1200, perdente scende sotto.
    assert elo1_after_first > 1200
    assert elo2_after_first < 1200
    assert games1 == 1
    # Dual pool: un match torneo crea 2 record ELO + 2 ELO_GLOBAL.
    assert (
        MatchRatingHistory.query.filter_by(
            match_id=match.id, rating_system=RatingSystem.ELO
        ).count()
        == 2
    )

    # Seconda chiamata (es. MatchCompletedEvent ri-emesso): NO-OP.
    RatingCalculationService.process_match_result(match)
    db.session.flush()
    assert _elo(p1.id) == elo1_after_first
    assert _elo(p2.id) == elo2_after_first
    assert PlayerRating.get_user_rating(p1.id, RatingSystem.ELO).games_played == 1
    assert (
        MatchRatingHistory.query.filter_by(
            match_id=match.id, rating_system=RatingSystem.ELO
        ).count()
        == 2
    )


@pytest.mark.unit
def test_revert_restores_rating_and_games(db_session):
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "rev_p1"), _user(suffix, "rev_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    match = _completed_match(_gara_id(suffix), p1.id, p2.id)
    db.session.add(match)
    db.session.flush()

    RatingCalculationService.process_match_result(match)
    db.session.flush()
    assert _elo(p1.id) != 1200

    # Revert: l'ultimo match processato torna esattamente allo stato iniziale.
    RatingCalculationService.revert_match_result(match)
    db.session.flush()
    assert _elo(p1.id) == 1200
    assert _elo(p2.id) == 1200
    assert PlayerRating.get_user_rating(p1.id, RatingSystem.ELO).games_played == 0
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 0


@pytest.mark.unit
def test_reprocess_after_revert_applies_again(db_session):
    # Dopo un revert il match può essere riprocessato (es. ricompletamento):
    # l'idempotenza non lo blocca più, niente inflazione.
    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "rr_p1"), _user(suffix, "rr_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    match = _completed_match(_gara_id(suffix), p1.id, p2.id)
    db.session.add(match)
    db.session.flush()

    RatingCalculationService.process_match_result(match)
    db.session.flush()
    elo1 = _elo(p1.id)

    RatingCalculationService.revert_match_result(match)
    db.session.flush()
    RatingCalculationService.process_match_result(match)
    db.session.flush()

    # Stesso risultato del primo calcolo, non raddoppiato.
    assert _elo(p1.id) == elo1
    assert PlayerRating.get_user_rating(p1.id, RatingSystem.ELO).games_played == 1


@pytest.mark.unit
def test_handler_skips_handicap_match(db_session):
    from models.rating.event_handlers import RatingEventHandlers
    from models.events import MatchCompletedEvent

    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "hc_p1"), _user(suffix, "hc_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    gara = _gara(suffix, has_handicap=True)  # gara con handicap
    db.session.add(gara)
    db.session.flush()
    # CONFIRMED_BY_BOTH e non CLOSED_UNILATERALLY: senza righe in `rack` un
    # match chiuso unilateralmente è un walkover, e sarebbe stato saltato per
    # quel motivo — il test avrebbe continuato a passare anche togliendo del
    # tutto la regola sull'handicap.
    match = _completed_match(
        gara.id,
        p1.id,
        p2.id,
        has_handicap=None,  # eredita
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
    )
    db.session.add(match)
    db.session.flush()
    assert match.effective_has_handicap is True
    assert match.is_walkover is False

    event = MatchCompletedEvent(
        match_id=match.id,
        player1_id=p1.id,
        player1_name="p1",
        player2_id=p2.id,
        player2_name="p2",
        winner_id=p1.id,
    )
    RatingEventHandlers.handle_match_completed(event)
    db.session.flush()

    # Nessun rating, nessuna history: nessuno ha assegnato categorie, e
    # "non lo so" non è "sono uguali". È il comportamento storico, invariato.
    assert _elo(p1.id) is None
    assert _elo(p2.id) is None
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 0


def _iscrivi_con_categoria(gara, user, categoria):
    from models.competition.models import Inscription

    db.session.add(
        Inscription(
            gara_id=gara.id,
            user_id=user.id,
            categoria_id=categoria.id if categoria else None,
        )
    )
    db.session.flush()


def _categoria(gara, nome):
    from models.categoria.models import Categoria

    categoria = Categoria(name=nome, gara_id=gara.id)
    db.session.add(categoria)
    db.session.flush()
    return categoria


def _scenario_handicap(suffix, nome1, nome2):
    """Gara con handicap, due iscritti con le categorie indicate, un match."""
    p1, p2 = _user(suffix, "cat_p1"), _user(suffix, "cat_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    gara = _gara(suffix, has_handicap=True)
    db.session.add(gara)
    db.session.flush()

    categorie = {n: _categoria(gara, n) for n in {n for n in (nome1, nome2) if n}}
    _iscrivi_con_categoria(gara, p1, categorie.get(nome1))
    _iscrivi_con_categoria(gara, p2, categorie.get(nome2))

    match = _completed_match(
        gara.id,
        p1.id,
        p2.id,
        has_handicap=None,
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
    )
    db.session.add(match)
    db.session.flush()
    assert match.is_walkover is False
    return p1, p2, match


def _completa(match, p1, p2):
    from models.rating.event_handlers import RatingEventHandlers
    from models.events import MatchCompletedEvent

    RatingEventHandlers.handle_match_completed(
        MatchCompletedEvent(
            match_id=match.id,
            player1_id=p1.id,
            player1_name="p1",
            player2_id=p2.id,
            player2_name="p2",
            winner_id=p1.id,
        )
    )
    db.session.flush()


@pytest.mark.unit
def test_handicap_stessa_categoria_aggiorna_il_rating(db_session):
    """Il cuore di ADR-049: ad armi pari il risultato conta."""
    p1, p2, match = _scenario_handicap(uuid.uuid4().hex[:8], "B", "B")
    assert match.effective_has_handicap is True

    _completa(match, p1, p2)

    assert _elo(p1.id) is not None and _elo(p1.id) > 1200
    assert _elo(p2.id) is not None and _elo(p2.id) < 1200
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() > 0


@pytest.mark.unit
def test_handicap_categorie_diverse_non_aggiorna(db_session):
    p1, p2, match = _scenario_handicap(uuid.uuid4().hex[:8], "B", "A")

    _completa(match, p1, p2)

    assert _elo(p1.id) is None
    assert _elo(p2.id) is None
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 0


@pytest.mark.unit
def test_handicap_stessa_categoria_resta_idempotente(db_session):
    """L'evento ri-emesso non deve raddoppiare il delta."""
    p1, p2, match = _scenario_handicap(uuid.uuid4().hex[:8], "B", "B")

    _completa(match, p1, p2)
    dopo_uno = _elo(p1.id)
    _completa(match, p1, p2)

    assert _elo(p1.id) == dopo_uno


@pytest.mark.unit
def test_handicap_stessa_categoria_si_annulla_alla_riapertura(db_session):
    p1, p2, match = _scenario_handicap(uuid.uuid4().hex[:8], "B", "B")

    _completa(match, p1, p2)
    assert _elo(p1.id) != 1200

    RatingCalculationService.revert_match_result(match)
    db.session.flush()

    assert _elo(p1.id) == 1200
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 0


@pytest.mark.unit
def test_to_playing_reopen_triggers_revert(db_session):
    # Wiring end-to-end: riaprire un match completato e RATED via to_playing
    # deve emettere MatchReopenedEvent → handler → revert (history svuotata,
    # rating ripristinato). Verifica il punto-hook centrale in to_playing.
    from models.match.state_service import MatchStateService

    suffix = uuid.uuid4().hex[:8]
    p1, p2 = _user(suffix, "rp_p1"), _user(suffix, "rp_p2")
    db.session.add_all([p1, p2])
    db.session.flush()
    match = _completed_match(_gara_id(suffix), p1.id, p2.id)
    db.session.add(match)
    db.session.flush()

    RatingCalculationService.process_match_result(match)
    db.session.flush()
    # Tre pool: 2 ELO + 2 ELO_GLOBAL + 2 RACK per il match torneo (ADR-052).
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 6

    # Riapertura: completed → playing.
    MatchStateService.to_playing(match.id)
    db.session.flush()

    # Il revert su riapertura azzera ENTRAMBI i pool.
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 0
    assert _elo(p1.id) == 1200
    assert _elo(p2.id) == 1200


# Helper: crea una gara standalone e ritorna l'id (per i test che non
# necessitano dei flag handicap).
def _gara_id(suffix):
    gara = _gara(suffix)
    db.session.add(gara)
    db.session.flush()
    return gara.id
