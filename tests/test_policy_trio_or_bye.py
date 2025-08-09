import pytest
from models.matchmaking.policies import decide_trio_or_bye, OddResolution


def test_decide_trio_or_bye_trio():
    assert decide_trio_or_bye(tournament_without_x=True, can_trio=True) is OddResolution.TRIO


def test_decide_trio_or_bye_bye_when_not_without_x():
    assert decide_trio_or_bye(tournament_without_x=False, can_trio=True) is OddResolution.BYE


def test_decide_trio_or_bye_bye_when_cannot_trio():
    assert decide_trio_or_bye(tournament_without_x=True, can_trio=False) is OddResolution.BYE