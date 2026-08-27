"""Зеркало :mod:`torrcast.adapters.stream_pack.weigh_keys`: карта для ВЕСА, а не для реза.

Мера тут отрицательная в обе стороны и ровно об одном: два читателя одной полки обязаны
расходиться на записи с вердиктом. Тот, кто ищет, ГДЕ РЕЗАТЬ, обязан промолчать; тот, кто
считает, СКОЛЬКО ЭТО ВЕСИТ, обязан ответить.
"""

from __future__ import annotations

import json
from pathlib import Path

from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.adapters.stream_pack.refuse_keys import refuse_keys
from torrcast.adapters.stream_pack.weigh_keys import weigh_keys
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.warm_open import KEYS_RULES

KEYS = FilmKeys(60.0, [0.0, 2.0, 4.0], [0, 2 << 20, 5 << 20], "mkv")


def test_the_map_a_verdict_refused_is_still_a_byte_index(tmp_path: Path) -> None:
    """🔴 Вердикт отвергает у карты кадры, а не смещения: вес по ней считается дальше.

    Живой замер, ради которого это написано: ровная сетка без профиля тяжести гонит
    КАЖДЫЙ кусок через ужатие на месте, и указатель приёмника идёт 0.40-0.44x вместо
    0.85-0.86x. Профиль строится ровно из этих смещений.
    """
    cache = tmp_path / "фильм.json"
    refuse_keys(cache, "прогон проехал мимо кадра карты", KEYS)

    assert read_keys(cache) is None, "отвергнутая карта вернулась сеткой - вердикт отменён"
    assert weigh_keys(cache) == KEYS, "честный указатель потерян вместе с кадрами"


def test_a_bare_verdict_promises_no_weight(tmp_path: Path) -> None:
    """Вердикт без карты - карты и нет: индекса в файле не оказалось вовсе."""
    cache = tmp_path / "фильм.json"
    refuse_keys(cache, "индекса в контейнере нет")

    assert weigh_keys(cache) is None


def test_a_healthy_map_weighs_by_the_same_reader(tmp_path: Path) -> None:
    """Годная карта читается тем же читателем: вес считается по любой, какая есть."""
    cache = tmp_path / "фильм.json"
    cache.write_text(
        json.dumps(
            {
                "duration": KEYS.duration,
                "keys": KEYS.at,
                "bytes": KEYS.offset,
                "kind": KEYS.kind,
                "rules": KEYS_RULES,
            }
        ),
        "utf-8",
    )

    assert weigh_keys(cache) == KEYS


def test_a_map_without_offsets_weighs_nothing(tmp_path: Path) -> None:
    """Карта прошлой версии смещений не несёт: взвешивать по ней нечем, и это ``None``."""
    cache = tmp_path / "фильм.json"
    cache.write_text(json.dumps({"duration": 60.0, "keys": [0.0, 2.0], "bytes": []}), "utf-8")

    assert weigh_keys(cache) is None


def test_a_ragged_index_is_not_an_index(tmp_path: Path) -> None:
    """Смещений меньше, чем меток: пара «время - смещение» распалась, верить нечему."""
    cache = tmp_path / "фильм.json"
    cache.write_text(json.dumps({"duration": 60.0, "keys": [0.0, 2.0], "bytes": [0]}), "utf-8")

    assert weigh_keys(cache) is None


def test_an_empty_shelf_is_not_a_crash(tmp_path: Path) -> None:
    """Ни файла, ни разбираемой записи - это ``None``, а не беда показа."""
    assert weigh_keys(tmp_path / "нет.json") is None
    (tmp_path / "мусор.json").write_text("не json", "utf-8")
    assert weigh_keys(tmp_path / "мусор.json") is None
