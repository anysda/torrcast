"""Зеркало :mod:`tests.fakes.prowlarr`."""

import pytest

from tests.fakes.prowlarr import FakeProwlarr
from torrcast import NotFoundError
from torrcast.domain.goal_spare import GOAL
from torrcast.domain.raw_result import RawResult


def test_fake_answers_the_known_query_and_records_every_ask() -> None:
    row = RawResult(title="Психо", info_hash="0" * 40)
    fake = FakeProwlarr({"психо": [row]})

    assert fake("http://p", "KEY") is fake
    assert fake.search("Психо") == [row]
    with pytest.raises(NotFoundError):
        fake.search("нетакогофильма")
    assert fake.asked == ["Психо", "нетакогофильма"]


def test_fake_never_holds_a_latecomer_and_keeps_the_whole_goal() -> None:
    fake = FakeProwlarr({})

    assert fake.late() == []
    assert fake.spare() == GOAL
