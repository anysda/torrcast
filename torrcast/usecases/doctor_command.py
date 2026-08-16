"""Команда ``cast doctor``: самопроверка окружения по-русски и общий вердикт.
Зовёт её :func:`torrcast.commands.main`, сами проверки живут в :mod:`torrcast.doctor`.
"""

from __future__ import annotations

__all__ = ["EXIT_INFRA", "EXIT_OK", "_cmd_doctor"]

from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_OK
from torrcast.ports.module import module


def _cmd_doctor() -> int:
    """``cast doctor`` — самопроверка окружения по-русски.

    Один вызов отвечает на все вопросы, которые иначе приходится проверять руками: терминал и
    локаль (кириллица в вопросах), Prowlarr и TorrServer (есть чем искать и чем
    раздавать), адрес ТВ и его порт 8009 (есть кому играть), ffmpeg с ``readrate``.
    """
    checkup = module("torrcast.doctor").checkup
    load_config = module("torrcast.state").load_config

    bad = 0
    for line, ok in checkup(load_config()):
        print(line)
        bad += 0 if ok else 1
    print()
    print("всё в порядке" if not bad else f"проблем: {bad} - смотри строки «плохо» выше")
    return EXIT_OK if not bad else EXIT_INFRA
