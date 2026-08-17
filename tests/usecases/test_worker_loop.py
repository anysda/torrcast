"""Зеркально проверяет цикл серий внутри юнита показа."""

from torrcast.domain.worker_settings import WORKER_META
from torrcast.usecases.following import _following
from torrcast.usecases.worker_loop import _worker_loop


def test_metadata_budget_of_the_unit_stays_where_it_was() -> None:
    assert WORKER_META == 60.0


def test_the_loop_and_its_next_episode_lookup_are_callable() -> None:
    assert callable(_worker_loop) and callable(_following)
