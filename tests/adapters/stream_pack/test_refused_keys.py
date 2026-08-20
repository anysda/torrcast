"""Зеркало :mod:`torrcast.adapters.stream_pack.refused_keys`: что снимается с полки отказов.

Мера про три вещи: отказ живёт на месте карты, помнится ограниченный срок, и срок этот
не продлевается обращением - иначе у самого частого фильма память стала бы вечной.
"""

import json
import os
import time
from pathlib import Path

from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.adapters.stream_pack.refused_keys import refused_keys

DAY = 24 * 60 * 60.0


def _refusal(cache: Path, said: str = "индекс Cues врёт", ago: float = 0.0) -> Path:
    cache.write_text(json.dumps({"refused": said, "when": time.time() - ago}), "utf-8")
    return cache


def test_a_fresh_refusal_comes_back_in_its_own_words(tmp_path: Path) -> None:
    """Вердикт возвращается тем же текстом: его говорят человеку вслух при ровной сетке."""
    cache = _refusal(tmp_path / "фильм.json")
    assert refused_keys(cache, DAY) == "индекс Cues врёт"


def test_a_refusal_older_than_the_term_is_forgotten(tmp_path: Path) -> None:
    """Срок вышел - файлу дают новый шанс: вердикт выносим мы, и ошибиться можем мы.

    Вечная память была бы хуже её отсутствия: фильм с починенным индексом навсегда
    остался бы на ровной сетке.
    """
    cache = _refusal(tmp_path / "фильм.json", ago=DAY + 60)
    assert refused_keys(cache, DAY) is None


def test_asking_again_does_not_renew_the_term(tmp_path: Path) -> None:
    """Обращение отмечается, но срок считается по времени вердикта, а не по файлу.

    Считай мы срок по времени файла - каждый старт продлевал бы память, и вечной она
    стала бы ровно у того фильма, который смотрят чаще всех.
    """
    cache = _refusal(tmp_path / "фильм.json", ago=DAY - 1)
    os.utime(cache, (1, 1))
    assert refused_keys(cache, DAY) == "индекс Cues врёт"
    assert cache.stat().st_mtime > 1, "отказ не отметился спрошенным - полка вытеснит его первым"
    assert refused_keys(cache, DAY - 2) is None, "отметка обращения продлила срок вердикта"


def test_a_map_is_not_a_refusal_and_a_refusal_is_not_a_map(tmp_path: Path) -> None:
    """Полка одна на оба ответа, и путать их нельзя ни в ту, ни в другую сторону."""
    carte = tmp_path / "карта.json"
    body = {"duration": 60.0, "keys": [0.0, 2.0], "bytes": [0, 4096]}
    carte.write_text(json.dumps(body), "utf-8")
    assert refused_keys(carte, DAY) is None, "карта прочиталась как отказ"
    assert read_keys(_refusal(tmp_path / "отказ.json")) is None, "отказ прочитался как карта"


def test_junk_and_emptiness_are_not_a_refusal(tmp_path: Path) -> None:
    """Битый файл на полке не отменяет снятие карты: вердикта нет - пойдём читать индекс."""
    assert refused_keys(tmp_path / "нет-такого.json", DAY) is None
    broken = tmp_path / "мусор.json"
    broken.write_text("{не json", "utf-8")
    assert refused_keys(broken, DAY) is None
    timeless = tmp_path / "безвремени.json"
    timeless.write_text(json.dumps({"refused": "индекс врёт"}), "utf-8")
    assert refused_keys(timeless, DAY) is None, "вердикт без времени нечем состарить"
