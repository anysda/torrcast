"""Внешний мир прогрева возвращается боевым после каждой пробы.

Стенд заводит его тем же композиционным корнем, каким живёт продукт
(:func:`tests.usecases.warm.world.world`), а корень пишет в слоты модуля - то есть в
состояние ПРОЦЕССА. Не вернуть их значило бы отдать следующей пробе чужую поддельную
среду: та же ошибка, из-за которой один тест портов гасил ленту всему прогону.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from torrcast.adapters.warm_environment import environment
from torrcast.usecases.warm import configure

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _rewired() -> Iterator[None]:
    """Отдать прогреву боевую среду обратно, чем бы его ни снабдила проба."""
    yield
    configure(environment)
