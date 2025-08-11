import pytest
from models.matchmaking.policies import anti_rematch_allowed


class _StubEncounter:
    played = set()

    @classmethod
    def have_played(cls, prova_id: int, a: int, b: int) -> bool:
        key = (prova_id, min(a, b), max(a, b))
        return key in cls.played


def test_anti_rematch_allowed_monkeypatch(monkeypatch):
    from models import PlayerEncounter

    monkeypatch.setattr(PlayerEncounter, "have_played", _StubEncounter.have_played)

    _StubEncounter.played.clear()
    assert anti_rematch_allowed(1, 10, 20) is True

    _StubEncounter.played.add((1, 10, 20))
    assert anti_rematch_allowed(1, 10, 20) is False
