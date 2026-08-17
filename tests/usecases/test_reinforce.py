"""Проверяет, что фасад добора ставит сценарию боевой каталог и боевую справку."""

import torrcast.reinforce  # noqa: F401  - импорт фасада и есть связывание
from torrcast import search
from torrcast.facts import origin
from torrcast.usecases import reinforce


def test_facade_wires_live_catalogue_and_passport() -> None:
    """За портами добора стоят настоящий каталог раздач и настоящая справка.

    Прежняя проверка звала :func:`same_picture` с пустым паспортом и на связывание не
    смотрела вовсе: сценарий с неподключённым каталогом прошёл бы её точно так же.
    """
    assert reinforce._catalogue is search
    assert reinforce._passport_source is origin
