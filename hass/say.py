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
    """Положить показу одно слово; читатель заберёт его на ближайшем опросе.

    🔴 Перемотка складывается с ещё не съеденной: показ читает файл раз в круг опроса, и
    три нажатия подряд перезаписывали друг друга - 3x60 давали +60, в журнале юнита одна
    строка (TC-1169, живой приёмник 06-10-2026). Несъеденное слово забирается
    переименованием, как у читателя: съел он его раньше - сдвиг уже исполнен.

    Складываются только сдвиги одного знака. Смена знака ложится следующим сдвигом той же
    строки (``seekby -240 60``): показ режет их по одному (:func:`torrcast.domain.seek_place.
    seek_place`), как и ползунок карточки, а сумма -180 от 100 ставила показ на 0 при 60
    на карточке.
    """
    target = _ctl_path() if path is None else path
    word, _, by = command.partition(" ")
    if word == SEEKBY:
        steps = _pending_seekby(target)
        if steps and (steps[-1] < 0.0) == (float(by) < 0.0):
            steps[-1] += float(by)
        else:
            steps.append(float(by))
        command = " ".join([SEEKBY, *(f"{step:g}" for step in steps)])
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(command, encoding="utf-8")
    temporary.replace(target)


def _pending_seekby(target: Path) -> list[float]:
    """Сдвиги несъеденной перемотки, забранные из файла; другое слово не трогается."""
    try:
        word, _, by = target.read_text(encoding="utf-8").strip().partition(" ")
        if word != SEEKBY:
            return []
        mine = target.with_suffix(target.suffix + ".merge")
        os.replace(target, mine)
        word, _, by = mine.read_text(encoding="utf-8").strip().partition(" ")
        mine.unlink(missing_ok=True)
        return [float(step) for step in by.split()] if word == SEEKBY else []
    except (OSError, ValueError):
        return []
