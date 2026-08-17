"""Точка входа ``cast``: сперва собирает приложение, потом отдаёт работу команде.

Console-script указывает сюда, а не сразу в :mod:`torrcast.cli`: команда обязана
получить внешний мир собранным, а собирать его - дело композиционного корня, и только
его (:mod:`torrcast.runtime.wire`).
"""

from collections.abc import Sequence

from torrcast.cli.main import main as run
from torrcast.runtime.wire import wire


def main(argv: Sequence[str] | None = None) -> int:
    """Собрать приложение и выполнить названную аргументами команду."""
    wire()
    return run(argv)
