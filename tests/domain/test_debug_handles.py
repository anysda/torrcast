"""Зеркало :mod:`torrcast.domain.debug_handles`: имена отладочных ручек показа.

Сторожится не написание строк, а то, что делает ручку ручкой: показ идёт в отдельном
юните, и переменная, которая туда не пробрасывается, не включает ничего - ни следа запаса,
ни диагностического пульта.
"""

from __future__ import annotations

from torrcast.domain.debug_handles import CTL_ENV, TRACE_ENV
from torrcast.domain.unit_naming import _PASS_ENV


def test_both_handles_reach_the_unit_where_the_show_actually_runs() -> None:
    """Ручку выставляют снаружи, а работает она внутри юнита показа.

    Выпади имя из списка пробрасываемого - человек выставил бы переменную и не увидел
    ничего: ни записей о запасе показа, ни исполненной команды пульта, - а разбирался бы
    потом с молчащим инструментом, а не с той поломкой, ради которой его включил.
    """
    assert TRACE_ENV in _PASS_ENV
    assert CTL_ENV in _PASS_ENV


def test_the_handles_are_two_different_switches_and_not_one_under_two_names() -> None:
    """След запаса и пульт - про разное: одно пишет, другое исполняет команды.

    Совпади имена - включение следа заодно отдавало бы приёмнику команды из файла, а это
    уже не наблюдение, а вмешательство в показ.
    """
    assert TRACE_ENV != CTL_ENV
    assert TRACE_ENV.startswith("TORRCAST_")
    assert CTL_ENV.startswith("TORRCAST_")
