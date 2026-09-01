"""Системное окружение сценария выбора: консоль, терминал, файл-команда и след."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from torrcast.adapters.console.console import stdin_is_tty as _tty
from torrcast.adapters.console.console.ask import ask
from torrcast.adapters.console.live_menu import LiveMenu
from torrcast.adapters.filesystem.release_pins import pins
from torrcast.adapters.filesystem.trace_journal.emit import emit
from torrcast.domain.debug_handles import CTL_ENV
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.shorten import shorten
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.rank_settings import ALIVE_SEEDERS
from torrcast.ports.menu_paint import MenuPaint

#: Правила соседних сценариев, которых адаптеру не назвать импортом: ранжирование, добор
#: и справка лежат слоем выше. Кладёт их сюда композиционный корень
#: (:mod:`torrcast.runtime.wire`) - до его слова у окружения их нет. Читаются они на
#: каждом обращении, поэтому подмена одного имени на стенде остаётся той же силы.
_passport: Callable[..., Origin]
_cut: Callable[[str, int], str]
_bitrate_of: Callable[..., float | None]
_hevc_hope: Callable[..., bool]
_is_candidate: Callable[..., bool]
_is_dated: Callable[..., bool]
_timed: Callable[..., Any]


def _configure_choice_environment(
    passport: Callable[..., Origin],
    cut: Callable[[str, int], str],
    bitrate_of: Callable[..., float | None],
    hevc_hope: Callable[..., bool],
    is_candidate: Callable[..., bool],
    is_dated: Callable[..., bool],
    timed: Callable[..., Any],
) -> None:
    """Назначить окружению выбора правила, лежащие слоем выше адаптеров."""
    global _passport, _cut, _bitrate_of, _hevc_hope, _is_candidate, _is_dated, _timed
    _passport = passport
    _cut = cut
    _bitrate_of = bitrate_of
    _hevc_hope = hevc_hope
    _is_candidate = is_candidate
    _is_dated = is_dated
    _timed = timed


class _SystemChoiceEnvironment:
    """Связывает порт выбора с прежними реализациями приложения."""

    @property
    def alive_seeders(self) -> int:
        return ALIVE_SEEDERS

    @property
    def ctl_env(self) -> str:
        return CTL_ENV

    @property
    def not_found_error(self) -> type[Exception]:
        return NotFoundError

    def read_command(self) -> str | None:
        name = os.environ.get(self.ctl_env, f"/tmp/torrcast-telegram-{os.getuid()}.ctl")
        path = Path(name)
        try:
            line = path.read_text("utf-8").strip()
        except OSError:
            return None
        path.unlink(missing_ok=True)
        return line

    @staticmethod
    def recalled_pick(query: str, number: int) -> tuple[str, str]:
        return pins.recalled_picture(query, number)

    @staticmethod
    def remember_pick(query: str, shown: list[tuple[str, str]]) -> None:
        pins.remember_menu(query, shown)

    def write(self, line: str) -> None:
        print(line, flush=True)

    @staticmethod
    def stdin_is_tty() -> bool:
        return _tty.stdin_is_tty()

    def ask(self, question: str, count: int, default: int | None = 1) -> int:
        return ask(question, count, default)

    def menu(self) -> MenuPaint:
        """Показ меню на весь один вопрос: своё состояние экрана у каждого меню."""
        return LiveMenu()

    @staticmethod
    def columns() -> int:
        return shutil.get_terminal_size((80, 24)).columns

    @staticmethod
    def fact() -> Fact:
        return Fact()

    @staticmethod
    def empty_origin() -> Origin:
        return Origin()

    @staticmethod
    def origin(title: str, series: bool) -> Origin:
        return _passport(title, series=series)

    @staticmethod
    def shorten(text: str) -> str:
        return shorten(text)

    @staticmethod
    def emit(event: str, action: str, **facts: object) -> None:
        emit(event, action, **facts)

    @staticmethod
    def cut(text: str, limit: int) -> str:
        return _cut(text, limit)

    @staticmethod
    def bitrate_of(release: Any, duration: float) -> float | None:
        return _bitrate_of(release, duration)

    @staticmethod
    def hevc_hope(release: Any, last: bool) -> bool:
        return _hevc_hope(release, last)

    @staticmethod
    def is_candidate(release: Any, *args: Any, **kwargs: Any) -> bool:
        return _is_candidate(release, *args, **kwargs)

    @staticmethod
    def is_dated(release: Any, runtime: float) -> bool:
        return _is_dated(release, runtime)

    @staticmethod
    def timed(*args: Any) -> Any:
        return _timed(*args)


environment = _SystemChoiceEnvironment()
