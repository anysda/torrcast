"""Одноразовое слово показу: тот же файл-пульт, в который пишут кнопки бота.

Путь берётся той же формулой, что у читателя
(:meth:`torrcast.adapters.choice_environment._SystemChoiceEnvironment.read_command`), и
запись идёт так же атомарно, как у бота (:meth:`tgbot.telegram_control.TelegramControl.command`):
показ съедает файл целиком на ближайшем опросе, и половина строки была бы командой.
"""

from __future__ import annotations

import os
from pathlib import Path

from torrcast.domain.debug_handles import CTL_ENV

#: Слова, которые понимает показ (:func:`torrcast.usecases.choice._ctl._ctl`). Мост
#: посылает не все: громкость идёт мимо файла, прямо на приёмник (:mod:`hass.volume`),
#: потому что в файле она СДВИГ, а Home Assistant называет уровень.
SEEKBY = "seekby"
TOGGLE = "toggle"


def _ctl_path() -> Path:
    """Файл-пульт этого хозяина: та же формула, что у читателя.

    🔴 Общий с ботом он выходит сам собой, а не по договорённости: оба юнита идут от
    root (``install.sh``, ``write_unit`` не задаёт ``User=``), umask один, и умолчание
    у формулы одно. Своё имя ставит ``TORRCAST_CTL``, и оно же уезжает в юнит показа
    (:data:`torrcast.domain.unit_naming._PASS_ENV`) - то есть подменённый на стенде путь
    доезжает до читателя целиком.
    """
    return Path(os.environ.get(CTL_ENV, f"/tmp/torrcast-telegram-{os.getuid()}.ctl"))


def say(command: str, path: Path | None = None) -> None:
    """Положить показу одно слово; читатель заберёт его на ближайшем опросе."""
    target = _ctl_path() if path is None else path
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(command, encoding="utf-8")
    temporary.replace(target)
