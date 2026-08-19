"""Живой прогресс по фазам с бегущим временем: видно, на чём стоим и сколько.

Заводит его корень команды на весь разговор; заметки отсюда уходят и в недельный след."""

from __future__ import annotations

import sys
import threading
import time
from typing import Any, Final, TextIO

from torrcast.adapters.filesystem.trace_journal.emit import emit

#: Как часто перерисовывается строка прогресса на живом терминале, секунды.
_TICK: Final = 0.5


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
        emit("note", "note", text=text)
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
