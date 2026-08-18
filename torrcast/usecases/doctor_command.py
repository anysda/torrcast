"""Команда ``cast doctor``: самопроверка окружения по-русски и общий вердикт.
Зовёт её :func:`torrcast.cli.main.main`, сами проверки живут в :mod:`torrcast.usecases.doctor`.
"""

from __future__ import annotations

__all__ = ["EXIT_INFRA", "EXIT_OK", "_cmd_doctor"]

from collections.abc import Callable

from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_OK
from torrcast.ports.health_config import HealthConfig
from torrcast.usecases.doctor import checkup

#: Чем команда читает настройки. Кладёт это композиционный корень
#: (:func:`torrcast.runtime.wire.wire`) - тем же способом, каким среду проб получает
#: :func:`torrcast.usecases.doctor._configure`. До его слова команда настроек не знает:
#: файл конфига - внешний мир, а сценарию туда ходить нечем.
_settings: Callable[[], HealthConfig]


def _configure(settings: Callable[[], HealthConfig]) -> None:
    """Принять чтение настроек от композиции: без него команде нечего проверять."""
    global _settings
    _settings = settings


def _cmd_doctor() -> int:
    """``cast doctor`` — самопроверка окружения по-русски.

    Один вызов отвечает на все вопросы, которые иначе приходится проверять руками: терминал и
    локаль (кириллица в вопросах), Prowlarr и TorrServer (есть чем искать и чем
    раздавать), адрес ТВ и его порт 8009 (есть кому играть), ffmpeg с ``readrate``.
    """
    bad = 0
    for line, ok in checkup(_settings()):
        print(line)
        bad += 0 if ok else 1
    print()
    print("всё в порядке" if not bad else f"проблем: {bad} - смотри строки «плохо» выше")
    return EXIT_OK if not bad else EXIT_INFRA
