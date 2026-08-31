"""Круг добора точной строкой «оригинал + год», когда русской дорожки нет ни у кого."""

from __future__ import annotations

from typing import Any

from tests.usecases.reinforce.stand import Indexer, Said, franchise, row
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.reinforce._voice_reinforce import _voice_reinforce

#: Единственный кандидат «тачек»: англоязычный BluRay на 66 сид, играть по-русски нечем.
_ENGLISH = [row("Тачки / Cars (2006) BluRay 1080p", "e", size_gb=8.0, seeders=66)]
#: То, что приезжает по точной строке: честный 1080p с дубляжом на 61 сид.
_DUBBED = [row("Тачки / Cars (2006) BDRip 1080p | D", "f", size_gb=5.0, seeders=61)]


def _asked(
    rows: list[RawResult], *, spare: float = 9.0, query: str = "тачки"
) -> tuple[Indexer, Said, tuple[list[Any], list[Picture], list[Picture]]]:
    client = Indexer(rows, spare=spare)
    client.over_goal = spare <= 0.0
    said = Said()
    found = franchise("тачки", _ENGLISH)
    outcome = _voice_reinforce(client, query, found[0], _ENGLISH, found, said)
    return client, said, outcome


def test_the_year_in_the_line_splits_the_hundred_rows_of_the_indexer() -> None:
    """🔴 По слову ``Cars`` русский ``BDRip 1080p | D`` в первую сотню не попадает."""
    client, said, (merged, _pictures, wider) = _asked(_DUBBED)

    assert client.asked == ["Cars 2006"]
    assert len(merged) == 2, "выдача склеена, а не заменена"
    assert [(p.title, len(p.releases)) for p in wider] == [("Тачки", 2)]
    assert said.text == phrase("reinforce.voice_note", title="Тачки", exact="Cars 2006", now=2)


def test_a_namesake_of_another_year_is_not_brought_in() -> None:
    """🔴 Новых картин круг не открывает вовсе: он пополняет ту, что уже нашлась."""
    client, said, (merged, _pictures, wider) = _asked(
        [row("Тачки 3 / Cars 3 (2017) BDRip 1080p | D", "g", seeders=99)]
    )

    assert client.asked == ["Cars 2006"], "круг был"
    assert merged is _ENGLISH, "а взять из него нечего"
    assert [(p.title, len(p.releases)) for p in wider] == [("Тачки", 1)]
    assert said.notes == []


def test_a_spent_goal_cancels_the_circle_and_says_so() -> None:
    """Круг платит из остатка цели, как и оба соседних добора."""
    client, said, (merged, _pictures, _wider) = _asked(_DUBBED, spare=0.0)

    assert client.asked == []
    assert merged is _ENGLISH
    assert said.text == (
        "not doing top up via «Cars 2006»: the search already spent the goal at 10s"
    )


def test_the_same_line_is_never_asked_twice() -> None:
    """Точная строка совпала с самим запросом - это тот же круг ради той же выдачи."""
    client, said, (merged, _pictures, _wider) = _asked(_DUBBED, query="cars 2006")

    assert client.asked == []
    assert merged is _ENGLISH
    assert said.notes == [], "отказа тут нет - есть отсутствие лишней работы"
