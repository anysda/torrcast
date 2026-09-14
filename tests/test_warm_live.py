"""Показ берёт только живой круг: поднятый с диска показывается карточке, но не играется."""

from __future__ import annotations

from pathlib import Path

from tests.test_warm_cache import _PLAN, _SHOWN, _TOLD, _Circle, _restarted, _sync
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover.told_circle import ToldCircle
from torrcast.usecases.discover.told_indexer import Told


def _on_disk(tmp_path: Path, circle: _Circle, told: list[Told] = _TOLD) -> None:
    _restarted(tmp_path, circle, _sync, told)[0].take("Interstellar")


def test_a_screen_circle_from_disk_taken_by_a_card_is_refreshed_once(tmp_path: Path) -> None:
    """🔴 Экран согрел плитку с диска, карточка взяла её готовой, и обновления не было."""
    circle = _Circle(answer=ToldCircle([_PLAN], _TOLD))
    _on_disk(tmp_path, circle)
    cache, _ = _restarted(tmp_path, circle, _sync)
    cache.ask(["Interstellar"])

    assert cache.take("Interstellar") == [_PLAN]
    assert cache.take("Interstellar") == [_PLAN]
    assert circle.asked == ["Interstellar", "Interstellar"]


def test_the_show_does_not_play_from_a_circle_revived_from_disk(tmp_path: Path) -> None:
    """🔴 Строка серии играла пул с диска: раздачи закладки в нём не было, первая не качалась."""
    circle = _Circle(answer=ToldCircle([_PLAN], _TOLD))
    _on_disk(tmp_path, circle)
    cache, _ = _restarted(tmp_path, circle, _sync)
    cache.ask(["Interstellar"])
    assert cache.ready("Interstellar") == [_PLAN]
    circle.answer = ToldCircle([_SHOWN], _TOLD)

    assert cache.take_live("Interstellar") == [_SHOWN]
    assert circle.asked == ["Interstellar", "Interstellar"]


def test_the_show_takes_the_circle_the_card_just_counted_without_a_second_trip(
    tmp_path: Path,
) -> None:
    circle = _Circle()
    cache, _ = _restarted(tmp_path, circle, _sync)
    cache.take("Interstellar")

    assert cache.take_live(" Interstellar") == [_PLAN]
    assert circle.asked == ["Interstellar"]


def test_a_poorer_live_refresh_is_what_the_show_plays_while_the_card_keeps_the_full_one(
    tmp_path: Path,
) -> None:
    """Обеднённый живой круг не вытесняет карточку, но показ играет его, а не запись диска."""
    full: list[Told] = [
        ("search", "Interstellar", 0.0, (), [RawResult("Interstellar", "a", indexer="JacRed")]),
        ("search", "Interstellar", 0.0, (), [RawResult("Interstellar", "b", indexer="RuTor")]),
    ]
    circle = _Circle(answer=ToldCircle([_PLAN], full))
    _on_disk(tmp_path, circle, full)
    circle.answer = ToldCircle([_SHOWN], full[1:])
    cache, _ = _restarted(tmp_path, circle, _sync, full)

    assert cache.take("Interstellar") == [_PLAN]
    assert cache.take_live("Interstellar") == [_SHOWN]
    assert circle.asked == ["Interstellar", "Interstellar"]
