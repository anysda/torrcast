"""Зеркало :mod:`torrcast.adapters.stream_pack.read_keys`: что снимается с полки карт.

Мера про снисходительность чтения и её границу: недостающие ряды внутри карты читаются
мягко, битый файл не роняет старт, карта отмечается спрошенной - а вот карта, снятая
ЧУЖИМИ ПРАВИЛАМИ, с полки не возвращается вовсе.
"""

import json
from pathlib import Path
from typing import Any

from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.domain.warm_open import KEYS_RULES


def _shelve(cache: Path, **body: Any) -> Path:
    """Карта на полке, снятая нынешними правилами: номер правил ставит сам писатель."""
    cache.write_text(json.dumps({"rules": KEYS_RULES, **body}), "utf-8")
    return cache


def test_a_saved_map_comes_back_whole(tmp_path: Path) -> None:
    """С полки возвращаются и времена, и смещения, и контейнер: по ним греют и режут."""
    cache = _shelve(
        tmp_path / "карта.json", duration=60.0, keys=[0.0, 2.0], bytes=[0, 4096], kind="mkv"
    )
    ready = read_keys(cache)
    assert ready is not None
    assert (ready.duration, ready.at, ready.offset, ready.kind) == (
        60.0,
        [0.0, 2.0],
        [0, 4096],
        "mkv",
    )


def test_the_seek_time_survives_the_shelf(tmp_path: Path) -> None:
    """Исковое время (``via``) доживает до чтения: без него бисект пошёл бы по метке показа."""
    cache = _shelve(
        tmp_path / "карта.json",
        duration=60.0,
        keys=[0.0834, 2.0854],
        bytes=[0, 4096],
        kind="mp4",
        via=[0.0, 2.002],
    )
    ready = read_keys(cache)
    assert ready is not None and list(ready.via) == [0.0, 2.002]

    bare = _shelve(tmp_path / "безвиа.json", duration=60.0, keys=[0.0, 2.0], bytes=[0, 4096])
    ready = read_keys(bare)
    assert ready is not None and ready.via == (), "ряда нет - исковое время это сама метка"


def test_the_shelf_lives_by_the_time_of_asking(tmp_path: Path) -> None:
    """Вытеснение идёт по обращению, а не по возрасту: иначе выбрасывалось бы то,
    ради чего кэш и заведён - карта фильма, который смотрят каждый вечер.
    """
    cache = _shelve(tmp_path / "карта.json", duration=1.0, keys=[0.0], bytes=[0])
    import os

    os.utime(cache, (1, 1))
    read_keys(cache)
    assert cache.stat().st_mtime > 1, "чтение не отметило карту как спрошенную"


def test_a_map_taken_by_other_rules_does_not_come_back(tmp_path: Path) -> None:
    """🔴 Полка живёт дольше правил, и вечная карта уже стоила зрителю сеанса.

    У отказа срок есть - «нет», сказанное прежней проверкой, само уходит с полки. У
    принятой карты срока не было никакого: снятая один раз, она возвращалась вечно и
    заново не судилась НИКОГДА. Ровно так «Матрица» 1999 (8065 точек Cues на 830
    настоящих опорных кадров) доставалась показу с полки после того, как живой разбор
    начал отвергать её каждый раз, - и сетка строилась по ней.

    Мера отрицательная в обе стороны: карта нынешних правил возвращается, карта прежних -
    нет, и разница ровно в номере правил, а не в содержимом.
    """
    body = {"duration": 60.0, "keys": [0.0, 2.0], "bytes": [0, 4096], "kind": "mkv"}
    fresh = tmp_path / "нынешняя.json"
    fresh.write_text(json.dumps({**body, "rules": KEYS_RULES}), "utf-8")
    assert read_keys(fresh) is not None, "карта нынешних правил обязана читаться"

    for stamp in ({}, {"rules": KEYS_RULES - 1}, {"rules": KEYS_RULES + 1}, {"rules": "нет"}):
        old = tmp_path / "прежняя.json"
        old.write_text(json.dumps({**body, **stamp}), "utf-8")
        assert read_keys(old) is None, f"карта чужих правил вернулась с полки: {stamp}"


def test_junk_on_the_shelf_is_not_a_map(tmp_path: Path) -> None:
    """Битый файл на полке не роняет старт: карты нет - снимем заново."""
    assert read_keys(tmp_path / "нет-такого.json") is None
    broken = tmp_path / "мусор.json"
    broken.write_text("{не json", "utf-8")
    assert read_keys(broken) is None
    empty = _shelve(tmp_path / "пусто.json", keys=[0.0])
    assert read_keys(empty) is None, "карта без длительности - не карта"
