"""Консоль: ввод, который работает из коробки, и живой прогресс по фазам.

Три жалобы сходятся в этом пакете:

* «консоль не поддерживает кириллицу» — ssh отдаёт pty с выключенным ``IUTF8``: забой
  стирает один байт, а русская буква весит два. Лечится тремя строками termios на входе
  и восстановлением режима на выходе (:func:`terminal`);
* битый ввод не должен доезжать до парсера: одиночные суррогаты чистятся в :func:`clean`
  на **любом** ответе, а не там, где о них вспомнили;
* «повисло или нет?» — на каждую фазу свою строку с бегущим временем (:class:`Progress`).

Отдельное правило вывода: ни ``→``, ни ``⚠``, ни ``▶``, ни ``≥`` наружу не уходит — в
терминале они и не несут смысла, и ломают ширину. Слова несут.

⚠️ Соседи внутри пакета зовут друг друга ЧЕРЕЗ него (``console.stdin_is_tty()``), а не
связанной функцией: подмену «терминала нет» ставят именно на пакет, и связывание при
импорте эту подмену бы потеряло - ровно по той же причине, что и в
:class:`~torrcast.adapters.console.print_console.PrintConsole`.
"""

from torrcast.adapters.console.console.ask import ask
from torrcast.adapters.console.console.ask_line import ask_line
from torrcast.adapters.console.console.clean import clean
from torrcast.adapters.console.console.iutf8 import iutf8
from torrcast.adapters.console.console.progress import Progress
from torrcast.adapters.console.console.stdin_is_tty import stdin_is_tty
from torrcast.adapters.console.console.terminal import terminal

__all__ = ["Progress", "ask", "ask_line", "clean", "iutf8", "stdin_is_tty", "terminal"]
