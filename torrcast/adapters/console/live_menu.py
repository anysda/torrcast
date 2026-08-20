"""Меню в терминале: печатается разом, а его строка дописывается на месте.

Собирает его окружение выбора (:mod:`torrcast.adapters.choice_environment`), по одному на меню."""

from __future__ import annotations

import shutil
import sys
import threading
from typing import TYPE_CHECKING, TextIO, cast

if TYPE_CHECKING:
    from types import TracebackType


def _span(line: str, width: int) -> int:
    """Сколько строк экрана занимает напечатанное: длинная строка переносится по краю."""
    return max(1, -(-len(line) // max(1, width)))


class LiveMenu:
    """Список на экране, чью строку можно переписать, пока человек читает и отвечает.

    Переписывается она курсором, а не повторной печатью: курсор запоминается (``ESC 7``),
    поднимается на нужное число строк, строка печатается заново до конца (``ESC [ K``) - и
    курсор возвращается туда, где стоял (``ESC 8``). Возврат тут главное: человек в этот
    момент набирает ответ, и его буквы обязаны остаться на своём месте. Вся
    последовательность уходит ОДНОЙ записью - чтобы буква, набранная ровно в эту секунду,
    не легла в её середину.

    Сколько строк подниматься - вопрос счёта, и считать его должен тот, кто печатает.
    Между списком и курсором успевают лечь строка про Enter, замечание про часть франшизы,
    ответ вопроса на непонятный номер: пока меню на экране, поток вывода подменяется
    счётчиком (:class:`_Tally`), и любая чужая печать - хоть ``print`` из соседнего
    модуля - считается сама. Приглашение вопроса счёта не меняет: оно без перевода
    строки, и курсор остаётся на той же строке экрана.

    Переписывать мы отказываемся дважды, и оба раза молча: строка, ставшая ВЫШЕ прежней
    (не влезла в ширину и перенеслась), сдвинула бы всё, что под ней; строка, уехавшая за
    верх экрана, не поднимается вовсе - курсор упрётся в первую строку и затрёт чужое.
    Меню без украшений - законный исход, а испорченный экран - нет.

    Без терминала (пайп, файл, юнит) не переписывается ничего: ``live`` отвечает «нет»,
    печать остаётся обычной, и ни одной управляющей последовательности в потоке нет.
    """

    def __init__(self, out: TextIO | None = None) -> None:
        self.out = out if out is not None else sys.stdout
        self.live = self._isatty()
        self.lock = threading.RLock()
        self._rows: list[int] = []
        self._below = 0
        self._column = 0
        self._width = 80
        self._height = 24
        self._saved: TextIO | None = None

    def show(self, lines: list[str]) -> None:
        """Напечатать список разом и начать считать всё, что ляжет ниже него."""
        size = shutil.get_terminal_size((80, 24))
        with self.lock:
            self._width, self._height = size.columns, size.lines
            self._rows = [_span(line, self._width) for line in lines]
            self._below, self._column = 0, 0
            if self.live and self._saved is None:
                self._saved = sys.stdout
                sys.stdout = cast(TextIO, _Tally(self._saved, self))
            self.out.write("\n".join(lines) + "\n")
            self.out.flush()

    def redraw(self, index: int, line: str) -> None:
        """Переписать строку списка на её месте; нельзя - не писать ничего."""
        with self.lock:
            if self._saved is None or not 0 <= index < len(self._rows):
                return
            if _span(line, self._width) != self._rows[index]:
                return
            up = self._below + sum(self._rows[index:])
            if up >= self._height:
                return
            self.out.write(f"\0337\033[{up}A\r{line}\033[K\0338")
            self.out.flush()

    def close(self) -> None:
        """Вернуть поток вывода как было: меню отвечено, переписывать больше нечего."""
        with self.lock:
            if self._saved is not None:
                sys.stdout, self._saved = self._saved, None

    def count(self, text: str) -> None:
        """Учесть чужую печать: сколько строк экрана она уже заняла ниже списка."""
        pieces = text.split("\n")
        for number, piece in enumerate(pieces):
            self._column += len(piece)
            while self._column > self._width:
                self._below += 1
                self._column -= self._width
            if number < len(pieces) - 1:
                self._below += 1
                self._column = 0

    def __enter__(self) -> LiveMenu:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.close()

    def _isatty(self) -> bool:
        try:
            return bool(self.out.isatty())
        except (AttributeError, ValueError):
            return False


class _Tally:
    """Поток вывода, который по дороге считает строки для :class:`LiveMenu`.

    Считает и пишет он под одним замком с перерисовкой: иначе меню успело бы поднять
    курсор на строку, которую печать ещё не вывела, и переписало бы соседнюю.
    """

    def __init__(self, out: TextIO, menu: LiveMenu) -> None:
        self._out = out
        self._menu = menu

    def write(self, text: str) -> int:
        with self._menu.lock:
            self._menu.count(text)
            return self._out.write(text)

    def __getattr__(self, name: str) -> object:
        return getattr(self._out, name)
