"""Зеркало :mod:`torrcast.adapters.stream_pack.read_keys`: что снимается с полки карт.

Мера про снисходительность чтения: кэш прошлой версии годен для сетки, битый файл не
роняет старт, а сама карта отмечается спрошенной - по этой отметке полка и живёт.
"""

import json
from pathlib import Path

from torrcast.adapters.stream_pack.read_keys import read_keys


def test_a_saved_map_comes_back_whole(tmp_path: Path) -> None:
    """С полки возвращаются и времена, и смещения, и контейнер: по ним греют и режут."""
    cache = tmp_path / "карта.json"
    cache.write_text(
        json.dumps({"duration": 60.0, "keys": [0.0, 2.0], "bytes": [0, 4096], "kind": "mkv"}),
        "utf-8",
    )
    ready = read_keys(cache)
    assert ready is not None
    assert (ready.duration, ready.at, ready.offset, ready.kind) == (
        60.0,
        [0.0, 2.0],
        [0, 4096],
        "mkv",
    )


def test_the_shelf_lives_by_the_time_of_asking(tmp_path: Path) -> None:
    """Вытеснение идёт по обращению, а не по возрасту: иначе выбрасывалось бы то,
    ради чего кэш и заведён - карта фильма, который смотрят каждый вечер.
    """
    cache = tmp_path / "карта.json"
    cache.write_text(json.dumps({"duration": 1.0, "keys": [0.0], "bytes": [0]}), "utf-8")
    import os

    os.utime(cache, (1, 1))
    read_keys(cache)
    assert cache.stat().st_mtime > 1, "чтение не отметило карту как спрошенную"


def test_an_old_cache_is_still_good_for_the_grid(tmp_path: Path) -> None:
    """Кэш прошлой версии смещений и контейнера не знал - и всё же годен: сетку он строит."""
    cache = tmp_path / "старая.json"
    cache.write_text(json.dumps({"duration": 60.0, "keys": [0.0, 2.0]}), "utf-8")
    ready = read_keys(cache)
    assert ready is not None and ready.offset == [] and ready.kind == ""


def test_junk_on_the_shelf_is_not_a_map(tmp_path: Path) -> None:
    """Битый файл на полке не роняет старт: карты нет - снимем заново."""
    assert read_keys(tmp_path / "нет-такого.json") is None
    broken = tmp_path / "мусор.json"
    broken.write_text("{не json", "utf-8")
    assert read_keys(broken) is None
    empty = tmp_path / "пусто.json"
    empty.write_text(json.dumps({"keys": [0.0]}), "utf-8")
    assert read_keys(empty) is None, "карта без длительности - не карта"
