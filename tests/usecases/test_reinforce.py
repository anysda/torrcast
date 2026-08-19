"""Проверяет, что корень ставит добору боевой каталог и боевую справку."""

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.runtime.facts_wiring import FACTS
from torrcast.usecases.reinforce.configure import _catalogue_port, _passport_port


def test_the_root_wires_the_live_catalogue_and_passport() -> None:
    """За портами добора стоят настоящий каталог раздач и настоящая справка.

    Прежняя проверка звала :func:`same_picture` с пустым паспортом и на связывание не
    смотрела вовсе: сценарий с неподключённым каталогом прошёл бы её точно так же.

    ⚠️ Спрашивается слот, а не пакет, и берётся он ИМЕНЕМ ИЗ МОДУЛЯ. У пакета имя
    ``configure`` занято одноимённой единицей: ``from ... reinforce import configure``
    отдаёт функцию, а не модуль слота, и подмена на ней ставится в никуда - молча.

    Сам каталог тоже назван своим файлом, а не пакетом: пакет имён соседей больше не
    раздаёт, и предмет договора живёт в
    :mod:`torrcast.adapters.prowlarr.torrent_catalogue` (TC-685).
    """
    assert _catalogue_port() is torrent_catalogue
    assert _passport_port() == FACTS.passport.of
