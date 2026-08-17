"""Regression (bug 6 docs/debug20260528.md): nuove debug action
`complete_next_match` (un match alla volta) e `complete_gara` (loop
fino a fine gara con avanzamento automatico dei turni)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, User
from models.base import utc_now
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _make_player(db_session, idx: int) -> User:
    uid = uuid.uuid4().hex[:6]
    u = User(
        username=f"player{idx}_{uid}",
        email=f"p{idx}_{uid}@test.local",
        role=UserRole.PLAYER.value,
    )
    u.set_password("x")
    db_session.add(u)
    db_session.commit()
    return u


def _setup_random_pregenerated_gara(db_session, num_players: int = 4):
    """Crea gara PLAYING al turno 1, 2 turni, match pre-generati su
    entrambi (random/round-robin style)."""
    players = [_make_player(db_session, i) for i in range(1, num_players + 1)]
    gara = Gara(
        number=1,
        name="GaraDbg",
        date=date.today() + timedelta(days=1),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        rounds_count=2,
        min_participants=num_players,
        max_participants=num_players,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() + timedelta(days=2),
        available_tables='["1", "2"]',
        matchmaking_strategy="random",
    )
    db_session.add(gara)
    db_session.commit()
    for p in players:
        db_session.add(Inscription(gara_id=gara.id, user_id=p.id))
    db_session.commit()

    # Round 1 - 2 match PLAYING con tavolo
    matches = [
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            status=MatchStatus.PLAYING.value,
            table_assignment="1",
            match_distance=5,
            is_race_to=True,
        ),
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=players[2].id,
            player2_id=players[3].id,
            status=MatchStatus.PLAYING.value,
            table_assignment="2",
            match_distance=5,
            is_race_to=True,
        ),
        # Round 2 - 2 match PENDING senza tavolo (rotazione)
        Match(
            gara_id=gara.id,
            round_number=2,
            player1_id=players[0].id,
            player2_id=players[2].id,
            status=MatchStatus.PENDING.value,
            match_distance=5,
            is_race_to=True,
        ),
        Match(
            gara_id=gara.id,
            round_number=2,
            player1_id=players[1].id,
            player2_id=players[3].id,
            status=MatchStatus.PENDING.value,
            match_distance=5,
            is_race_to=True,
        ),
    ]
    db_session.add_all(matches)
    db_session.commit()
    return gara


@pytest.mark.integration
def test_complete_next_match_completes_one(client, db_session):
    gara = _setup_random_pregenerated_gara(db_session)

    resp = client.get(f"/debug/complete_next_match/{gara.id}", follow_redirects=False)
    assert resp.status_code in (302, 303)

    # Complete Match pesca da TUTTI i round attivi (bug 12), quindi il match
    # completato puo' essere indifferentemente di round 1 o round 2.
    completed_total = Match.query.filter_by(
        gara_id=gara.id, status=MatchStatus.CLOSED_UNILATERALLY.value
    ).count()
    pending_total = (
        Match.query.filter_by(gara_id=gara.id)
        .filter(
            Match.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value])
        )
        .count()
    )

    assert completed_total == 1, f"Atteso 1 completato, trovati {completed_total}"
    assert pending_total == 3, f"Atteso 3 ancora aperti, trovati {pending_total}"


@pytest.mark.integration
def test_complete_round_advances_to_next_active_round(client, db_session):
    """Bug 12: dopo aver completato il turno 1, current_round resta 1
    (update_round_progression non avanza finche' round 2 non e'
    completato). Il secondo click su Complete Round deve riconoscere
    che il primo round attivo e' ora il 2 e completarlo, non dire
    "nessun match"."""
    gara = _setup_random_pregenerated_gara(db_session)

    # Primo click: completa round 1
    resp1 = client.get(
        f"/debug/complete_current_round/{gara.id}", follow_redirects=False
    )
    assert resp1.status_code in (302, 303)
    r1_done = (
        Match.query.filter_by(gara_id=gara.id, round_number=1)
        .filter(Match.status == MatchStatus.CLOSED_UNILATERALLY.value)
        .count()
    )
    assert r1_done == 2

    # Secondo click: deve completare round 2 (non dire "nessun match")
    resp2 = client.get(
        f"/debug/complete_current_round/{gara.id}", follow_redirects=False
    )
    assert resp2.status_code in (302, 303)
    r2_done = (
        Match.query.filter_by(gara_id=gara.id, round_number=2)
        .filter(
            Match.status.in_(
                [
                    MatchStatus.CLOSED_UNILATERALLY.value,
                    MatchStatus.CONFIRMED_BY_BOTH.value,
                ]
            )
        )
        .count()
    )
    assert r2_done == 2, f"Atteso 2 match round 2 completati, trovati {r2_done}"


@pytest.mark.integration
def test_complete_next_match_picks_from_any_round(client, db_session):
    """Bug 12: Complete Match deve pescare da qualsiasi round attivo,
    non solo da gara.current_round."""
    gara = _setup_random_pregenerated_gara(db_session)

    # Forza la simulazione che current_round resti a 1 ma round 2 abbia
    # match PLAYING attivi: completa direttamente i 2 match di round 1.
    r1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
    for m in r1_matches:
        m.status = MatchStatus.CLOSED_UNILATERALLY.value
        m.player1_score = 5
        m.player2_score = 0
        m.winner_id = m.player1_id
    db_session.commit()

    # Promuovi i match di round 2 a PLAYING con tavolo, mantenendo
    # current_round=1 (caso "tipico" random: i match successivi sono
    # gia' pronti ma current_round non si e' avanzato)
    r2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
    for i, m in enumerate(r2_matches):
        m.status = MatchStatus.PLAYING.value
        m.table_assignment = str(i + 1)
    db_session.commit()

    resp = client.get(f"/debug/complete_next_match/{gara.id}", follow_redirects=False)
    assert resp.status_code in (302, 303)

    r2_completed = Match.query.filter_by(
        gara_id=gara.id,
        round_number=2,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    ).count()
    assert (
        r2_completed == 1
    ), f"Atteso 1 match round 2 completato, trovati {r2_completed}"


@pytest.mark.integration
def test_complete_next_match_ignores_matches_without_table(client, db_session):
    """Bug 13: Complete Match deve completare SOLO match con tavolo
    assegnato e in corso. Se nessun match ha un tavolo (tutti PENDING in
    attesa), non deve completare nulla."""
    gara = _setup_random_pregenerated_gara(db_session)

    # Rimuove i tavoli e riporta tutti i match a PENDING: nessuno è "al
    # tavolo", quindi Complete Match non deve toccare nulla.
    for m in Match.query.filter_by(gara_id=gara.id).all():
        m.status = MatchStatus.PENDING.value
        m.table_assignment = None
    db_session.commit()

    resp = client.get(f"/debug/complete_next_match/{gara.id}", follow_redirects=False)
    assert resp.status_code in (302, 303)

    completed = Match.query.filter_by(
        gara_id=gara.id, status=MatchStatus.CLOSED_UNILATERALLY.value
    ).count()
    assert (
        completed == 0
    ), f"Nessun match ha tavolo: atteso 0 completati, trovati {completed}"


@pytest.mark.integration
def test_completable_matches_only_playing_with_table(client, db_session):
    """Bug 13: l'helper di selezione restituisce solo i match PLAYING con
    tavolo assegnato, mai i PENDING senza tavolo."""
    from routes.main import _debug_completable_matches

    gara = _setup_random_pregenerated_gara(db_session)

    completable = _debug_completable_matches(gara.id)

    # Setup: 2 match round 1 PLAYING+tavolo, 2 round 2 PENDING senza tavolo.
    assert len(completable) == 2
    for m in completable:
        assert m.status == MatchStatus.PLAYING.value
        assert m.table_assignment is not None
        assert m.round_number == 1


@pytest.mark.integration
def test_complete_gara_finishes_all_matches(client, db_session):
    gara = _setup_random_pregenerated_gara(db_session)

    resp = client.get(f"/debug/complete_gara/{gara.id}", follow_redirects=False)
    assert resp.status_code in (302, 303)

    # Tutti i 4 match devono essere completati
    all_matches = Match.query.filter_by(gara_id=gara.id).all()
    assert len(all_matches) == 4
    assert all(
        m.status
        in (MatchStatus.CLOSED_UNILATERALLY.value, MatchStatus.CONFIRMED_BY_BOTH.value)
        for m in all_matches
    ), f"Match status: {[m.status for m in all_matches]}"
