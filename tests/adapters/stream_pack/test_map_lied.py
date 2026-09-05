"""Карта этого файла разошлась с нарезкой: снять ей доверие до конца процесса."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from torrcast.adapters.pack_memory import _MAP_LIED
from torrcast.adapters.stream_pack.map_lied import map_lied

URL = "http://торрент/поток?link=раздача"


@pytest.fixture(autouse=True)
def _own_memory() -> Iterator[None]:
    """Снятое доверие помнится на весь процесс; каждой пробе оно достаётся нетронутым."""
    _MAP_LIED.clear()
    yield
    _MAP_LIED.clear()


def test_the_verdict_is_written_where_the_entry_will_look_for_it() -> None:
    """Приговор ложится в память процесса, а не в память вызвавшего.

    Спрашивает её другой модуль и в другом потоке
    (:func:`torrcast.adapters.stream_pack.map_trusted.map_trusted`), поэтому проба
    смотрит на саму полку: разъехались бы имена - обе половины правила остались бы
    зелёными порознь и мёртвыми вместе.
    """
    map_lied(URL)

    assert URL in _MAP_LIED


def test_the_same_file_named_twice_is_still_one_verdict() -> None:
    """Часы показа зовут уборку каждые две секунды: повтор обязан быть безобиден."""
    map_lied(URL)
    map_lied(URL)

    assert list(_MAP_LIED) == [URL]
