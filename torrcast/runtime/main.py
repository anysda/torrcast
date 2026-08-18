"""Точка входа ``cast``: сперва собирает приложение, потом отдаёт работу команде.

Console-script указывает сюда, а не сразу в :mod:`torrcast.cli`: команда обязана
получить внешний мир собранным, а собирать его - дело композиционного корня, и только
его (:mod:`torrcast.runtime.wire`).
"""

from collections.abc import Callable, Sequence

from torrcast.cli.main import main as run
from torrcast.runtime.wire import wire


def main(
    argv: Sequence[str] | None = None,
    *,
    assemble: Callable[[], None] = wire,
    command: Callable[[Sequence[str] | None], int] = run,
) -> int:
    """Собрать приложение и выполнить названную аргументами команду.

    Сборка и команда названы параметрами, а не именами модуля: порядок этих двух
    действий и есть весь смысл точки входа, и меряется он подставленной парой, а не
    подменой атрибутов. Боевой паре тут стоять умолчанием - зовёт точку входа
    console-script, которому передавать нечего.
    """
    assemble()
    return command(argv)
