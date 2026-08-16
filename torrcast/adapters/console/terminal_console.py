"""Читает ответы и пишет сообщения в терминал для сценариев."""

from __future__ import annotations

import sys
import unicodedata
from re import compile
from typing import TextIO

_SURROGATE = compile("[\ud800-\udfff]")
_CONTROL = compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class TerminalConsole:
    """Реализация консольного порта поверх стандартных потоков."""

    def __init__(self, inp: TextIO | None = None, out: TextIO | None = None) -> None:
        self._in = inp if inp is not None else sys.stdin
        self._out = out if out is not None else sys.stdout

    def ask(self, question: str, default: str = "") -> str:
        prompt = f"{question}: "
        if not self._is_tty():
            self.write(f"{prompt}{default or '(терминала нет - беру по умолчанию)'}")
            return self._clean(default).casefold()
        self._out.write(prompt)
        self._out.flush()
        raw = self._in.readline()
        if not raw:
            self._out.write("\n")
            self._out.flush()
            return self._clean(default).casefold()
        return self._clean(raw).casefold() or self._clean(default).casefold()

    def write(self, message: str) -> None:
        self._out.write(message + "\n")
        self._out.flush()

    def _is_tty(self) -> bool:
        try:
            return bool(self._in.isatty())
        except (AttributeError, ValueError):
            return False

    @staticmethod
    def _clean(text: str) -> str:
        clean = _SURROGATE.sub("", text)
        return unicodedata.normalize("NFC", _CONTROL.sub("", clean)).strip()
