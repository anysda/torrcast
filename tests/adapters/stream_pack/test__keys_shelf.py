"""Проверяет полку карт: адрес карты в кэше и чтение снятого, включая кэш прошлой версии."""

import json
from pathlib import Path

import pytest

from torrcast.adapters.stream_pack._keys_shelf import _keys_cache, _read_keys

URL = "http://127.0.0.1:8090/stream?link=0123456789abcdef&index=1"


def test_the_address_of_a_map_is_the_url_of_its_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ключ полки - сам URL: в нём hash раздачи и номер файла, то есть содержимое.

    Полка нужна не ради трафика (4 МБ), а ради времени: первое чтение хвоста стоит
    13.8 с на «Моане» 2016 и 24.4 с на «Моане 2».
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    where = _keys_cache(URL)
    assert where.parent == tmp_path / "keys"
    assert where.suffix == ".json"
    assert where == _keys_cache(URL), "один файл - один адрес"
    assert where != _keys_cache(URL.replace("index=1", "index=2")), "другой файл - другая карта"


def test_a_saved_map_comes_back_whole(tmp_path: Path) -> None:
    """С полки возвращаются и времена, и смещения, и контейнер: по ним греют и режут."""
    cache = tmp_path / "карта.json"
    cache.write_text(
        json.dumps({"duration": 60.0, "keys": [0.0, 2.0], "bytes": [0, 4096], "kind": "mkv"}),
        "utf-8",
    )
    ready = _read_keys(cache)
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
    _read_keys(cache)
    assert cache.stat().st_mtime > 1, "чтение не отметило карту как спрошенную"


def test_an_old_cache_is_still_good_for_the_grid(tmp_path: Path) -> None:
    """Кэш прошлой версии смещений и контейнера не знал - и всё же годен: сетку он строит."""
    cache = tmp_path / "старая.json"
    cache.write_text(json.dumps({"duration": 60.0, "keys": [0.0, 2.0]}), "utf-8")
    ready = _read_keys(cache)
    assert ready is not None and ready.offset == [] and ready.kind == ""


def test_junk_on_the_shelf_is_not_a_map(tmp_path: Path) -> None:
    """Битый файл на полке не роняет старт: карты нет - снимем заново."""
    assert _read_keys(tmp_path / "нет-такого.json") is None
    broken = tmp_path / "мусор.json"
    broken.write_text("{не json", "utf-8")
    assert _read_keys(broken) is None
    empty = tmp_path / "пусто.json"
    empty.write_text(json.dumps({"keys": [0.0]}), "utf-8")
    assert _read_keys(empty) is None, "карта без длительности - не карта"
