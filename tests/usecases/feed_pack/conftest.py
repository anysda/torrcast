"""Внешний мир ленты показа возвращается боевым после каждой пробы.

Стенд заводит его тем же композиционным корнем, каким живёт продукт
(:func:`tests.usecases.feed_pack.world.tract`), а корень пишет в слоты модуля - то есть
в состояние ПРОЦЕССА. Не вернуть их значило бы отдать следующей пробе чужой поддельный
медиатракт: та же ошибка, из-за которой один тест портов гасил ленту всему прогону.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from torrcast.runtime.wire_feed import wire_feed

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _rewired() -> Iterator[None]:
    """Отдать ленте боевой медиатракт обратно, чем бы её ни снабдила проба."""
    yield
    wire_feed()
