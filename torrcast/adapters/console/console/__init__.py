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

Внешнего мира у диалога ровно два: «есть ли живой терминал» и «чем прочитать строку».
Оба названы параметрами вопросов (``tty``, ``read``) и конструктором консоли команд
(:class:`~torrcast.adapters.console.print_console.PrintConsole`) - подставляет их тот, кто
спрашивает. ``None`` значит «взять живые»: консоль зовут из десятка мест, и передавать
туда нечего. Живой ответ про терминал соседи по-прежнему берут ЧЕРЕЗ пакет
(``console.stdin_is_tty()``), потому что общий стенд команды показа притворяется
терминалом подменой этого имени.
"""

from torrcast.adapters.console.console.ask import ask
from torrcast.adapters.console.console.ask_line import ask_line
from torrcast.adapters.console.console.clean import clean
from torrcast.adapters.console.console.iutf8 import iutf8
from torrcast.adapters.console.console.progress import Progress
from torrcast.adapters.console.console.stdin_is_tty import stdin_is_tty
from torrcast.adapters.console.console.terminal import terminal

__all__ = ["Progress", "ask", "ask_line", "clean", "iutf8", "stdin_is_tty", "terminal"]
