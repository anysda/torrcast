"""Консоль: ввод, который работает из коробки, и живой прогресс по фазам.

Три жалобы сходятся в этом модуле:

* «консоль не поддерживает кириллицу» — ssh отдаёт pty с выключенным ``IUTF8``: забой
  стирает один байт, а русская буква весит два. Лечится тремя строками termios на входе
  и восстановлением режима на выходе (:func:`terminal`);
* битый ввод не должен доезжать до парсера: одиночные суррогаты чистятся в :func:`clean`
  на **любом** ответе, а не там, где о них вспомнили;
* «повисло или нет?» — на каждую фазу свою строку с бегущим временем (:class:`Progress`).

Отдельное правило вывода: ни ``→``, ни ``⚠``, ни ``▶``, ни ``≥`` наружу не уходит — в
терминале они и не несут смысла, и ломают ширину. Слова несут.
"""

from __future__ import annotations

import contextlib
import re
import sys
import threading
import time
import unicodedata
from collections.abc import Iterator
from typing import Any, Final, TextIO

__all__ = ["Progress", "ask", "ask_line", "clean", "iutf8", "stdin_is_tty", "terminal"]

#: Одиночные суррогаты: так выглядит байтовый мусор, доехавший до строки Python.
_SURROGATE: Final = re.compile("[\ud800-\udfff]")
#: Управляющие символы, которым в ответе человека делать нечего (кроме табуляции).
_CONTROL: Final = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
#: Как часто перерисовывается строка прогресса на живом терминале, секунды.
_TICK: Final = 0.5


def clean(text: str) -> str:
    """Ответ человека → пригодная строка: без суррогатов, без управляющих, в NFC.

    Битый ввод не должен доезжать до парсера ни при каких обстоятельствах: pty без
    ``IUTF8`` отдаёт половинки русских букв, а их Python держит одиночными суррогатами.
    Такую строку нельзя ни записать в state, ни отправить в поиск — она рвётся на
    ``encode``. Поэтому чистим на входе, а не там, где рванёт.
    """
    return unicodedata.normalize("NFC", _CONTROL.sub("", _SURROGATE.sub("", text))).strip()


def iutf8() -> int:
    """Бит ``IUTF8`` во флагах ввода pty. Отдельной функцией — mypy не знает его на всех
    платформах, а нам он нужен ровно на Linux.
    """
    import termios

    return int(getattr(termios, "IUTF8", 0o40000))


def stdin_is_tty() -> bool:
    """Есть ли живой терминал на входе. Отдельной функцией — чтобы тесты могли соврать."""
    try:
        return bool(sys.stdin.isatty())
    except ValueError:  # закрытый stdin (так бывает в юните)
        return False


@contextlib.contextmanager
def terminal() -> Iterator[None]:
    """Включить ``IUTF8`` на stdin и вернуть режим как было.

    Без него ssh-сессия ведёт себя так: русская буква занимает два байта, а
    забой стирает один — на экране остаётся половина символа, и в строку уезжает мусор.
    Флаг ставится ядром на драйвер pty, поэтому чинит и эхо, и забой разом.

    Без терминала (юнит, пайп, тесты) — честный no-op, а не попытка чинить трубу.
    """
    if not stdin_is_tty():
        yield
        return
    import termios

    try:
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
    except (termios.error, ValueError, OSError):  # не pty либо stdin уже не наш
        yield
        return
    mode = list(saved)
    mode[0] = int(mode[0]) | iutf8()
    try:
        termios.tcsetattr(fd, termios.TCSANOW, mode)
        yield
    finally:
        with contextlib.suppress(termios.error, ValueError, OSError):
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def ask_line(question: str, default: str = "") -> str:
    """Свободный ответ. Enter — дефолт; терминала нет — тоже дефолт, и **без ожидания**.

    Вечное ожидание на пайпе (наблюдалось 180 с) — это не «строгость», а зависший
    сценарий: спросить всё равно некого.
    """
    prompt = f"{question}: "
    if not stdin_is_tty():
        print(f"{prompt}{default or '(терминала нет - беру по умолчанию)'}", flush=True)
        return clean(default).casefold()
    try:
        raw = input(prompt)
    except EOFError:
        print(flush=True)
        return clean(default).casefold()
    answer = clean(raw).casefold()
    return answer or clean(default).casefold()


def ask(question: str, count: int, default: int | None = 1) -> int:
    """Вопрос с номерами: принимает и цифру, и пустой Enter - когда дефолт есть.

    ``default=None`` - дефолта нет нарочно: любой автовыбор тут был бы подменой картины
    (:func:`~torrcast.cli.part_one_swap`), и номер обязан назвать сам человек. Пустой
    Enter такой ответом не считается - вопрос повторяется.
    """
    prompt = f"{question} [{default}]" if default is not None else question
    while True:
        answer = ask_line(prompt)
        if not answer and default is not None:
            return default
        if answer.isdigit() and 1 <= int(answer) <= count:
            return int(answer)
        print(f"нужен номер от 1 до {count}")
        if not stdin_is_tty():  # спросить некого - вторым кругом висеть не будем
            if default is None:
                raise EOFError(f"нужен номер от 1 до {count}, а терминала нет")
            return default


class Progress:
    """Живой прогресс по фазам с бегущим временем.

    ``поиск… 2 с`` → ``метаданные (DHT)… 4 с`` → ``дорожки… 11 с`` → ``упаковка… 3 с`` →
    ``жду телевизор… 2 с``. Пользователь всегда видит, на чём стоим, и не гадает, повисло
    ли: молчание дольше пары секунд неотличимо от зависания.

    На живом терминале строка перерисовывается на месте (``\\r``) фоновым тиком; без
    терминала (юнит, пайп, тесты) каждая фаза печатается одной строкой с итоговым
    временем — журнал остаётся читаемым, а лишнего мусора в нём нет.
    """

    def __init__(self, out: TextIO | None = None, tick: float = _TICK) -> None:
        self.out = out if out is not None else sys.stdout
        self.tick = tick
        self.live = self._isatty()
        self._lock = threading.RLock()
        self._text = ""
        self._since = 0.0
        self._width = 0
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def phase(self, text: str) -> None:
        """Начать фазу. Та же фаза второй раз — не мигаем и не сбрасываем часы."""
        with self._lock:
            if text == self._text:
                return
            self._close_line()
            self._text, self._since = text, time.monotonic()
            if not text:
                return
            if not self.live:
                return
            self._draw()
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()

    def note(self, text: str) -> None:
        """Сказать что-то посреди фазы, не потеряв строку прогресса.

        Та же строка уходит и в недельный след: заметка - это решение показа (добор,
        склейка картин, честный отказ), и знать о нём при разборе сеанса надо. Отдельных
        вызовов журнала в местах решений это не заводит - их подбирает сам ``note``.
        """
        from torrcast import trace

        trace.emit("note", "note", text=text)
        with self._lock:
            keep, since = self._text, self._since
            self._erase()
            self._text = ""
            self._say(text)
            if keep:
                self._text, self._since = keep, since
                if self.live:
                    self._draw()

    def stop(self) -> None:
        """Погасить прогресс: строка фазы закрывается, тик останавливается."""
        with self._lock:
            self._close_line()
            self._text = ""
        self._wake.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.0)
        self._wake.clear()

    def __enter__(self) -> Progress:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.stop()

    def _run(self) -> None:
        while not self._wake.wait(self.tick):
            with self._lock:
                # ⚠️ Не выходим из потока на пустой фазе: между фазами `_text` пуст, а
                # `phase()` заводит поток только пока его нет вовсе. Поток, ушедший на
                # первом же `phase("")`, уносил с собой бегущее время всех следующих фаз -
                # и на экране висело замершее «метаданные (DHT)... 0 с» ровно там, где
                # должен идти живой прогресс.
                if self._text:
                    self._draw()

    def _draw(self) -> None:
        line = f"{self._text}... {time.monotonic() - self._since:.0f} с"
        self.out.write("\r" + line + " " * max(0, self._width - len(line)))
        self.out.flush()
        self._width = len(line)

    def _erase(self) -> None:
        if self.live and self._width:
            self.out.write("\r" + " " * self._width + "\r")
            self.out.flush()
        self._width = 0

    def _close_line(self) -> None:
        """Закрыть строку фазы её итоговым временем — оно и есть замер."""
        if not self._text:
            return
        spent = time.monotonic() - self._since
        self._erase()
        self._say(f"{self._text}... {spent:.1f} с")

    def _say(self, text: str) -> None:
        self.out.write(text + "\n")
        self.out.flush()

    def _isatty(self) -> bool:
        try:
            return bool(self.out.isatty())
        except (AttributeError, ValueError):
            return False
