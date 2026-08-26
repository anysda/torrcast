"""Зеркало :mod:`torrcast.adapters.stream_pack.refuse_keys`: как вердикт ложится на полку.

Мера про три вещи: вердикт ложится НА МЕСТО карты, читается обратно своими же словами и
кладётся атомарно - через черновик, а не поверх чужой записи.
"""

from __future__ import annotations

import json
from pathlib import Path

from torrcast.adapters.stream_pack.read_keys import read_keys
from torrcast.adapters.stream_pack.refuse_keys import refuse_keys
from torrcast.adapters.stream_pack.refused_keys import refused_keys
from torrcast.domain.warm_open import KEYS_RULES

DAY = 24 * 60 * 60.0


def test_the_verdict_lands_where_the_map_would_have(tmp_path: Path) -> None:
    """Имя на полке одно: файл говорит либо «вот карта», либо «карты не будет»."""
    cache = tmp_path / "фильм.json"
    refuse_keys(cache, "индекс Cues врёт")

    assert refused_keys(cache, DAY) == "индекс Cues врёт"
    assert read_keys(cache) is None, "вердикт прочитался как карта"


def test_a_verdict_replaces_the_map_that_lay_there(tmp_path: Path) -> None:
    """🔴 Полка помнит карту дольше, чем сеанс помнит, что она соврала.

    Ровно поэтому вердикт обязан ЛЕЧЬ НА МЕСТО карты, а не рядом: иначе следующий показ
    того же фильма взял бы ту же карту и построил бы по ней ту же сетку.
    """
    cache = tmp_path / "фильм.json"
    cache.write_text(
        json.dumps(
            {"duration": 60.0, "keys": [0.0, 2.0], "bytes": [0, 4096], "rules": KEYS_RULES}
        ),
        "utf-8",
    )
    assert read_keys(cache) is not None, "карта не легла - мерить нечего"

    refuse_keys(cache, "сетка по карте разошлась с прогоном")

    assert read_keys(cache) is None, "карта пережила вердикт"
    assert refused_keys(cache, DAY) == "сетка по карте разошлась с прогоном"


def test_the_verdict_leaves_no_draft_behind(tmp_path: Path) -> None:
    """Своё имя писателя не должно превратиться в свой же мусор на полке."""
    refuse_keys(tmp_path / "фильм.json", "индекса в файле нет")

    assert [p.name for p in tmp_path.iterdir()] == ["фильм.json"]


def test_a_shelf_that_cannot_be_written_is_not_a_crash(tmp_path: Path) -> None:
    """Полка только для чтения - это не беда показа: вердикт просто не запомнится."""
    closed = tmp_path / "закрыто"
    closed.mkdir(mode=0o500)
    try:
        refuse_keys(closed / "фильм.json", "индекс Cues врёт")
    finally:
        closed.chmod(0o700)
