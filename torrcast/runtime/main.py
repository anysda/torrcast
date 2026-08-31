"""Точка входа ``cast``: сперва собирает приложение, потом отдаёт работу команде.

Console-script указывает сюда, а не сразу в :mod:`torrcast.cli`: команда обязана
получить внешний мир собранным, а собирать его - дело композиционного корня, и только
его (:mod:`torrcast.runtime.wire`).
"""

import sys
from collections.abc import Callable, Sequence

from torrcast.cli.main import main as run
from torrcast.domain.exit_codes import EXIT_INFRA
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal.slot import journal
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

    🔴 TC-929, заход 4. Ограда тут своя, а не общая с :func:`torrcast.cli.answered.
    answered`: та оборачивает только ``command`` и о сборке не знает вовсе, поэтому битый
    конфиг или неведомый язык (:func:`torrcast.domain.catalogs.tongue._choose_tongue`)
    раньше улетали трейсбеком мимо неё. Отказ сборки - всегда инфра: до всякой команды
    нечем ещё сказать «не нашли» или «отменено», поэтому код тут один, а не тот же
    разбор по роду исключения, что и внутри ``answered``.
    """
    try:
        assemble()
    except TorrcastError as exc:
        journal().emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        # Ярлык ленты, не жалоба: тот же машинный смысл, что у `result` внутри
        # :func:`torrcast.cli.answered.answered`, и остаётся английским словом по той же
        # причине - `cast log` читает поле как есть при любом языке настройки.
        journal().emit("command", "finished", result="assembly_failure", code=EXIT_INFRA)
        journal().shutdown()
        return EXIT_INFRA
    return command(argv)
