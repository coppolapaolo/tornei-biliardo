"""Test per la cache metriche request-scoped in UnlockProgressService (#9).

`get_all_features_progress` eseguiva un N+1: per ogni feature, le condizioni
METRIC venivano valutate via UserMetricService.get_metric (una COUNT) sia in
can_access sia in _evaluate_condition. La cache opt-in passata dal solo path di
sola lettura elimina i ricalcoli senza rischiare valori stale nei flussi di
mutazione (che NON passano la cache).
"""

import json
import uuid

import pytest

from models.base import db
from models.match.models import Match
from models.status_enum import MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole
from models.gamification.feature_models import FeatureConfig
from models.gamification.unlock_engine import UnlockEngine
from models.gamification.unlock_progress_service import UnlockProgressService
from models.kpi.user_metrics import UserMetricService


def _player():
    u = User(
        username=f"p_{uuid.uuid4().hex[:8]}",
        email=f"p_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    u.set_password("pass123")
    db.session.add(u)
    db.session.flush()
    return u


def _completed_match(user_id, opponent_id):
    db.session.add(
        Match(
            round_number=1,
            player1_id=user_id,
            player2_id=opponent_id,
            status=MatchStatus.COMPLETED.value,
        )
    )


def _feature(code, required_matches):
    rules = json.dumps(
        [
            {
                "description": f"{required_matches}+ match",
                "conditions": [
                    {
                        "type": "METRIC",
                        "metric": "total_matches",
                        "operator": "gte",
                        "value": required_matches,
                    }
                ],
            }
        ]
    )
    f = FeatureConfig(code=code, name=code, rules=rules, is_active=True)
    db.session.add(f)
    db.session.flush()
    return f


@pytest.fixture
def count_metric_calls(monkeypatch):
    """Conta le invocazioni dell'handler COUNT sottostante (_get_total_matches)."""
    calls = {"n": 0}
    original = UserMetricService._get_total_matches

    def wrapper(user_id, context=None):
        calls["n"] += 1
        return original(user_id, context)

    monkeypatch.setattr(UserMetricService, "_get_total_matches", staticmethod(wrapper))
    return calls


class TestUnlockProgressCache:
    def test_metric_computed_once_across_features(self, db_session, count_metric_calls):
        """La stessa metrica e' calcolata UNA volta per l'intero render, non
        una per (feature x condizione x can_access/evaluate)."""
        user = _player()
        opp = _player()
        for _ in range(3):
            _completed_match(user.id, opp.id)
        # Due feature, entrambe gated sulla stessa metrica total_matches.
        _feature(f"feat_a_{uuid.uuid4().hex[:6]}", 5)
        _feature(f"feat_b_{uuid.uuid4().hex[:6]}", 2)
        db.session.flush()

        UnlockProgressService.get_all_features_progress(user.id)

        # Senza cache sarebbero >= 4 chiamate (2 feature x [can_access +
        # _evaluate_condition]); con la cache condivisa: esattamente 1.
        assert count_metric_calls["n"] == 1

    def test_cached_result_matches_uncached(self, db_session):
        """Il risultato con cache condivisa e' identico a quello senza cache."""
        user = _player()
        opp = _player()
        for _ in range(4):
            _completed_match(user.id, opp.id)
        fa = _feature(f"feat_a_{uuid.uuid4().hex[:6]}", 5)  # non sbloccata (4<5)
        fb = _feature(f"feat_b_{uuid.uuid4().hex[:6]}", 2)  # sbloccata (4>=2)
        db.session.flush()

        cached = {
            p["feature_code"]: p
            for p in UnlockProgressService.get_all_features_progress(user.id)
        }
        # Stessa valutazione ma senza cache, feature per feature.
        for f in (fa, fb):
            uncached = UnlockProgressService.get_feature_progress(user.id, f.code)
            assert cached[f.code]["is_unlocked"] == uncached["is_unlocked"]
            assert (
                cached[f.code]["rule_sets"][0]["conditions"][0]["current_value"]
                == uncached["rule_sets"][0]["conditions"][0]["current_value"]
            )
        assert cached[fa.code]["is_unlocked"] is False
        assert cached[fb.code]["is_unlocked"] is True

    def test_no_cache_path_sees_fresh_data(self, db_session):
        """Il path di mutazione (check_eligibility senza cache) riflette sempre
        i dati correnti: nessuna memoizzazione globale che servirebbe valori
        stale alle award."""
        user = _player()
        opp = _player()
        code = f"feat_{uuid.uuid4().hex[:6]}"
        _feature(code, 3)
        db.session.flush()

        # 2 match: sotto soglia.
        for _ in range(2):
            _completed_match(user.id, opp.id)
        db.session.flush()
        assert UnlockEngine.check_eligibility(user.id, code) is False

        # Aggiungo il terzo: la valutazione successiva (senza cache) lo vede.
        _completed_match(user.id, opp.id)
        db.session.flush()
        assert UnlockEngine.check_eligibility(user.id, code) is True

    def test_separate_renders_use_independent_caches(self, db_session):
        """Due render successivi (cache nuova ognuno) riflettono i dati
        aggiornati: la cache e' locale alla singola chiamata, non globale."""
        user = _player()
        opp = _player()
        code = f"feat_{uuid.uuid4().hex[:6]}"
        _feature(code, 3)
        for _ in range(2):
            _completed_match(user.id, opp.id)
        db.session.flush()

        first = {
            p["feature_code"]: p
            for p in UnlockProgressService.get_all_features_progress(user.id)
        }
        assert first[code]["is_unlocked"] is False
        assert first[code]["rule_sets"][0]["conditions"][0]["current_value"] == 2

        _completed_match(user.id, opp.id)
        db.session.flush()

        second = {
            p["feature_code"]: p
            for p in UnlockProgressService.get_all_features_progress(user.id)
        }
        assert second[code]["is_unlocked"] is True
        assert second[code]["rule_sets"][0]["conditions"][0]["current_value"] == 3
