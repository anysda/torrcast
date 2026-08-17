"""Проверяет, что фасад добора ставит сценарию боевой каталог и боевую справку."""

import torrcast.reinforce  # noqa: F401  - импорт фасада и есть связывание
from torrcast import search
from torrcast.facts import origin
from torrcast.usecases.reinforce.configure import _catalogue_port, _passport_port


def test_facade_wires_live_catalogue_and_passport() -> None:
    """За портами добора стоят настоящий каталог раздач и настоящая справка.

    Прежняя проверка звала :func:`same_picture` с пустым паспортом и на связывание не
    смотрела вовсе: сценарий с неподключённым каталогом прошёл бы её точно так же.

    ⚠️ Спрашивается слот, а не пакет, и берётся он ИМЕНЕМ ИЗ МОДУЛЯ. У пакета имя
    ``configure`` занято одноимённой единицей: ``from ... reinforce import configure``
    отдаёт функцию, а не модуль слота, и подмена на ней ставится в никуда - молча.
    """
    assert _catalogue_port() is search
    assert _passport_port() is origin
