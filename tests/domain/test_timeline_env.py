"""Зеркало :mod:`torrcast.domain.timeline_env`: чем включается секундомер критического пути.

Имя переменной само по себе - опечатка и ничего больше. Сторожится связь: показ идёт в
отдельном юните, и переменная, которая туда не пробрасывается, не включает ничего.
"""

from __future__ import annotations

from torrcast.domain.timeline_env import TIMELINE_ENV
from torrcast.domain.unit_naming import _PASS_ENV


def test_the_stopwatch_switch_reaches_the_unit_where_the_show_actually_runs() -> None:
    """Секундомер меряет путь ЮНИТА, поэтому его переменная обязана доехать до юнита.

    Показ живёт не в том процессе, который зовёт `cast`. Выпади имя из списка
    пробрасываемого - лента меток осталась бы пустой, а секундомер молча мерил бы пустую
    команду вместо старта показа.
    """
    assert TIMELINE_ENV in _PASS_ENV


def test_the_switch_lives_in_our_own_namespace_and_cannot_collide_with_a_foreign_one() -> None:
    """Переменная общая с окружением машины, поэтому имя обязано быть нашим.

    Возьми она короткое общее слово - чужая переменная включала бы наш секундомер или, что
    хуже, наш секундомер писал бы ленту по чужому пути.
    """
    assert TIMELINE_ENV.startswith("TORRCAST_")
