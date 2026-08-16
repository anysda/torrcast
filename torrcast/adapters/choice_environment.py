"""Системное окружение сценария выбора."""

# mypy: disable-error-code="no-any-return,no-untyped-def"

import os
import shutil
from importlib import import_module
from pathlib import Path
from typing import Any


class _SystemChoiceEnvironment:
    """Связывает порт выбора с прежними реализациями приложения."""

    @property
    def alive_seeders(self) -> int:
        return import_module("torrcast.commands").ALIVE_SEEDERS

    @property
    def ctl_env(self) -> str:
        return import_module("torrcast.commands").CTL_ENV

    @property
    def not_found_error(self) -> type[Exception]:
        return import_module("torrcast").NotFoundError

    def read_command(self) -> str | None:
        name = os.environ.get(self.ctl_env)
        if not name:
            return None
        path = Path(name)
        try:
            line = path.read_text("utf-8").strip()
        except OSError:
            return None
        path.unlink(missing_ok=True)
        return line

    @staticmethod
    def write(line: str) -> None:
        print(line, flush=True)

    @staticmethod
    def stdin_is_tty() -> bool:
        return import_module("torrcast.console").stdin_is_tty()

    @staticmethod
    def ask(question: str, count: int, default: int | None = 1) -> int:
        return import_module("torrcast.console").ask(question, count, default)

    @staticmethod
    def columns() -> int:
        return shutil.get_terminal_size((80, 24)).columns

    @staticmethod
    def fact():
        return import_module("torrcast.facts").Fact()

    @staticmethod
    def empty_origin():
        return import_module("torrcast.facts").Origin()

    @staticmethod
    def origin(title: str, series: bool):
        return import_module("torrcast.choice").origin(title, series=series)

    @staticmethod
    def shorten(text: str) -> str:
        return import_module("torrcast.facts").shorten(text)

    @staticmethod
    def emit(event: str, action: str, **facts: object) -> None:
        import_module("torrcast.trace").emit(event, action, **facts)

    @staticmethod
    def cut(text: str, limit: int) -> str:
        return import_module("torrcast.ranking")._cut(text, limit)

    @staticmethod
    def bitrate_of(release: Any, duration: float) -> float | None:
        return import_module("torrcast.ranking").bitrate_of(release, duration)

    @staticmethod
    def hevc_hope(release: Any, last: bool) -> bool:
        return import_module("torrcast.ranking").hevc_hope(release, last)

    @staticmethod
    def is_candidate(release: Any, *args: Any, **kwargs: Any) -> bool:
        return import_module("torrcast.ranking").is_candidate(release, *args, **kwargs)

    @staticmethod
    def is_dated(release: Any, runtime: float) -> bool:
        return import_module("torrcast.ranking").is_dated(release, runtime)

    @staticmethod
    def timed(*args: Any) -> Any:
        return import_module("torrcast.reinforce")._timed(*args)


environment = _SystemChoiceEnvironment()
