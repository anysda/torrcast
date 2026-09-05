"""Зеркало описи очереди отбора: что взято, что отсеяно и что из этого сказано вслух."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.usecases.select_bench.world import plan, rel
from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.episode import Episode
from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.select_bench._bench_queue import _bench_queue


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русская строка описи очереди отбора."""


_ASKED = Args(query=["кино"])


def test_the_queue_is_what_the_gate_let_through() -> None:
    """Очередь - это план, спрошенный своими воротами, и ничего сверх того."""
    ranked = [rel(name=f"r{n}", seeders=100 - n) for n in range(3)]

    assert _bench_queue(plan(ranked), _ASKED) == [1, 2, 3]


def test_an_empty_queue_is_a_refusal_with_the_whole_count_of_the_pool() -> None:
    """🔴 TC-432. Ворота не пропустил никто - подставить отсеянное значило бы подменить."""
    image = rel(name="Кино / Movie (1999) BDRemux 2160p ISO", size_gb=41.0, quality=None)

    with pytest.raises(NotFoundError, match="годного релиза нет: раздач в выдаче 1"):
        _bench_queue(plan([image], recode_at=0.0), _ASKED)


def test_releases_without_the_asked_episode_are_named_aloud_before_the_swap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Человек попросил серию, половину выдачи мы не взяли - и это сказано вслух.

    Отсев по серии зритель видит как подмену: спрашивал s01e05, а показ идёт из другой
    раздачи, чем верх выдачи. Молчание тут читается поломкой отбора, а строка называет
    решение своим именем - и потому она обязана быть, а не быть по случаю.
    """
    want = Episode(1, 5)
    has = replace(rel(name="Сериал s01e05"), season=1, episode=5)
    misses = [replace(rel(name=f"Сериал s01e0{n}"), season=1, episode=n) for n in (3, 4)]
    asked = plan([*misses, has])
    asked.series = _Series(want=want)

    queue = _bench_queue(asked, _ASKED)

    said = capsys.readouterr().out
    assert queue == [3], "в очередь идёт только раздача с нужной серией"
    assert phrase("select_bench.skipped_note", want=want, count=2, name="Сериал s01e03") in said, (
        "отсев по серии назван вслух"
    )


def test_a_named_release_is_the_whole_queue_and_says_nothing_extra(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Номер назвал человек - судить его нечем, и лишних строк ему не печатают."""
    ranked = [rel(name=f"r{n}", seeders=100 - n) for n in range(3)]

    assert _bench_queue(plan(ranked), Args(query=["кино"], release=2)) == [2]
    assert capsys.readouterr().out == ""
