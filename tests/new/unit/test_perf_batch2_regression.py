"""Regression (review 2026-06-09, batch 2): N+1/perf + correttezza statistiche.

- Challenge.get_statistics: eseguiva la query lazy='dynamic' 4 volte
  (count/distinct/all + ri-iterazione per `passed`). Ora materializza una sola
  volta: il numero di query NON cresce col numero di tentativi. Inoltre la
  mediana usava sorted()[len//2] (errata per N pari) → ora statistics.median.
- PlayoffService.get_user_playoff_history: dereferenziava
  configuration.campionato.name senza None-check (crash pagina su orfano).
"""

import uuid

import pytest
from sqlalchemy import event

from models.base import db
from models.user.models import User
from models.challenge.models import Challenge, ChallengeAttempt


class _QueryCounter:
    def __init__(self):
        self.count = 0

    def __enter__(self):
        event.listen(db.engine, "before_cursor_execute", self._cb)
        return self

    def __exit__(self, *a):
        event.remove(db.engine, "before_cursor_execute", self._cb)

    def _cb(self, conn, cursor, statement, params, context, executemany):
        head = statement.lstrip().upper()
        if head.startswith("SELECT") or head.startswith("WITH"):
            self.count += 1


def _make_user(suffix, i):
    u = User(username=f"u{i}_{suffix}", email=f"u{i}_{suffix}@t.com", role="player")
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    return u


def _make_numeric_challenge(suffix, scores):
    """Challenge numerica con un tentativo completato per ogni score."""
    ch = Challenge(
        description=f"Ch {suffix}", image_path="/x.jpg", pass_fail_only=False
    )
    db.session.add(ch)
    db.session.flush()
    for i, sc in enumerate(scores):
        u = _make_user(suffix, i)
        db.session.add(
            ChallengeAttempt(challenge_id=ch.id, user_id=u.id, score=sc, completed=True)
        )
    db.session.flush()
    return ch


@pytest.mark.unit
def test_get_statistics_median_even_count(db_session):
    """Mediana corretta per N pari: [2, 8] → 5.0, non 8."""
    ch = _make_numeric_challenge(uuid.uuid4().hex[:8], [2, 8])
    db.session.commit()
    stats = ch.get_statistics()
    assert stats["median_score"] == 5
    assert stats["total_attempts"] == 2


@pytest.mark.unit
def test_get_statistics_median_odd_count(db_session):
    """Mediana corretta per N dispari: [2, 5, 8] → 5."""
    ch = _make_numeric_challenge(uuid.uuid4().hex[:8], [2, 5, 8])
    db.session.commit()
    assert ch.get_statistics()["median_score"] == 5


@pytest.mark.unit
def test_get_statistics_not_n_plus_one(db_session):
    """Il numero di query non cresce col numero di tentativi."""
    suffix = uuid.uuid4().hex[:8]
    ch2 = _make_numeric_challenge(suffix + "a", [3, 7])
    db.session.commit()
    with _QueryCounter() as qc2:
        ch2.get_statistics()

    ch5 = _make_numeric_challenge(suffix + "b", [1, 2, 3, 4, 5])
    db.session.commit()
    with _QueryCounter() as qc5:
        ch5.get_statistics()

    assert (
        qc5.count == qc2.count
    ), f"N+1: {qc2.count} query con 2 tentativi vs {qc5.count} con 5"


@pytest.mark.unit
def test_playoff_history_handles_none_campionato(db_session, monkeypatch):
    """get_user_playoff_history non deve esplodere se campionato e' None."""
    from models.playoff.services import PlayoffService
    from models.playoff import services as playoff_services

    suffix = uuid.uuid4().hex[:8]
    user = _make_user(suffix, 99)
    db.session.commit()

    # Simula una qualifica la cui configuration.campionato e' None (orfano):
    # il path reale e' un FK orfano; qui basta un oggetto con quelle property.
    class _Cfg:
        name = "Playoff X"
        campionato = None

    class _Qual:
        configuration = _Cfg()
        qualifying_position = 1
        created_at = __import__("datetime").datetime(2026, 1, 1)
        responded_at = None

        class status:
            value = "pending"

    monkeypatch.setattr(
        playoff_services.PlayoffQualification,
        "query",
        type(
            "Q",
            (),
            {
                "filter_by": staticmethod(
                    lambda **k: type(
                        "R",
                        (),
                        {
                            "options": lambda self, *a: self,
                            "all": lambda self: [_Qual()],
                        },
                    )()
                )
            },
        )(),
    )

    history = PlayoffService.get_user_playoff_history(user.id)
    assert history[0]["campionato_name"] is None
    assert history[0]["playoff_name"] == "Playoff X"
