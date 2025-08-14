# tests/test_withdraw_policy_pairing.py
from datetime import date, datetime
import pytest

from models import db, User, Tournament, Prova, Inscription, Match
from models.status_enum import MatchStatus
from models.competition.models import WithdrawPolicy
from models.matchmaking.bootstrap import get_matchmaking_service


@pytest.mark.usefixtures("app")
def test_preview_exclude_policy_rimuove_ritirati(app):
    """
    Con policy EXCLUDE a livello Prova, i giocatori ritirati non
    partecipano agli abbinamenti di preview (round 1).
    La disparità (se presente) è gestita da X/Trio dall'engine.
    """
    t = Tournament(name="T", tournament_type="Amalfi", is_active=True, without_x=True)
    db.session.add(t)
    db.session.commit()

    p = Prova(
        tournament_id=t.id,
        number=1,
        name="P",
        date=date.today(),
        rounds_count=2,
        distance=5,
        discipline="palla 8",
    )
    p.withdraw_policy = WithdrawPolicy.EXCLUDE.value
    db.session.add(p)
    db.session.commit()

    # 3 giocatori → dopo esclusione di 1 ritirato restano 2
    a = User(username="a_prev", email="a_prev@test.com", role="player")
    a.set_password("pw")
    b = User(username="b_prev", email="b_prev@test.com", role="player")
    b.set_password("pw")
    c = User(username="c_prev", email="c_prev@test.com", role="player")
    c.set_password("pw")
    db.session.add_all([a, b, c])
    db.session.flush()  # assegna gli id a, b, c

    db.session.add_all(
        [
            Inscription(prova_id=p.id, user_id=a.id),
            Inscription(prova_id=p.id, user_id=b.id),
            Inscription(prova_id=p.id, user_id=c.id),
        ]
    )
    db.session.commit()

    # Ritira C a prova già iniziata (simuliamo current_round=1)
    p.current_round = 1
    db.session.commit()
    ins_c = Inscription.query.filter_by(prova_id=p.id, user_id=c.id).first()
    ins_c.is_withdrawn = True
    ins_c.withdrawn_at = datetime.utcnow()
    db.session.commit()

    svc = get_matchmaking_service()
    pairings = svc.preview(strategy_name="Amalfi", prova=p, round_number=1)

    # Nessun pairing deve includere C
    for pr in pairings:
        assert c.id not in pr.players
    # E in totale i giocatori coinvolti sono solo A e B
    involved = set(pid for pr in pairings for pid in pr.players)
    assert involved.issubset({a.id, b.id})


@pytest.mark.usefixtures("app")
def test_run_forfeit_policy_chiude_match_contro_ritirati(app):
    """
    Con policy FORFEIT a livello Prova, i match contro ritirati vengono
    chiusi a tavolino (status COMPLETED, punteggio massimo all'avversario).
    """
    t = Tournament(name="T2", tournament_type="Amalfi", is_active=True, without_x=False)
    db.session.add(t)
    db.session.commit()

    p = Prova(
        tournament_id=t.id,
        number=1,
        name="P2",
        date=date.today(),
        rounds_count=2,
        distance=5,
        discipline="palla 9",
    )
    p.withdraw_policy = WithdrawPolicy.FORFEIT.value
    db.session.add(p)
    db.session.commit()

    # Crea gli utenti, FLUSH per avere gli id, poi iscrizioni
    users = []
    for i in range(1, 6):  # 5 giocatori così l'engine crea più di un match
        u = User(username=f"user_{i}", email=f"user_{i}@test.com", role="player")
        u.set_password("pw")
        db.session.add(u)
        users.append(u)
    db.session.flush()  # assegna id ai users

    db.session.add_all([Inscription(prova_id=p.id, user_id=u.id) for u in users])
    db.session.commit()

    withdrawn_user = users[1]  # es. user_2

    # Ritira withdrawn a prova in corso
    p.current_round = 1
    db.session.commit()
    ins_w = Inscription.query.filter_by(
        prova_id=p.id, user_id=withdrawn_user.id
    ).first()
    ins_w.is_withdrawn = True
    ins_w.withdrawn_at = datetime.utcnow()
    db.session.commit()

    # Avvio pairing effettivo (round 1)
    svc = get_matchmaking_service()
    svc.run(strategy_name="Amalfi", prova=p, round_number=1)

    # Trova il match che coinvolge il ritirato nel round 1
    matches_round1 = Match.query.filter_by(prova_id=p.id, round_number=1).all()
    assert matches_round1, "Nessun match creato per il round 1"

    m_w = next(
        (
            m
            for m in matches_round1
            if m.player1_id == withdrawn_user.id or m.player2_id == withdrawn_user.id
        ),
        None,
    )
    assert (
        m_w is not None
    ), "Nessun match del round 1 coinvolge il ritirato (controlla setup del pairing)"

    # Deve essere stato chiuso a tavolino
    assert m_w.status == MatchStatus.COMPLETED.value
    win_score = p.get_winning_score()
    assert (m_w.player1_score == win_score) ^ (m_w.player2_score == win_score)
