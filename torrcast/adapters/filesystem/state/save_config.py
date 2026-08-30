"""Запись настроек на диск - атомарная, потому что читают их и на ходу.

Зовут её первичная настройка и команды, меняющие адрес приёмника."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from torrcast.adapters.filesystem.state.config_path import config_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.invalid_config_object_error import InvalidConfigObjectError
from torrcast.domain.torrcast_error import TorrcastError

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.domain.config import Config


def _stored(path: Path) -> dict[str, Any]:
    """Файл настроек как он есть; отсутствие файла - пустой словарь.

    🔴 Файл общий: рядом с ключами показа в нём живут ключи телеграм-бота (``token``,
    ``chat_id``, ``proxy``), которых у :class:`Config` нет вовсе. Запись своего
    дата-класса ЦЕЛИКОМ стирала их - вместе с боевым токеном (TC-934).

    Битый файл роняет запись нарочно и тем же словом, что и чтение
    (:func:`~torrcast.adapters.filesystem.state.load_config.load_config`): разобрать
    чужие ключи нечем, а написать поверх - значит стереть их молча. Продукт на битом
    файле и так стоит, поэтому чинит его человек, а не тихая перезапись.
    """
    if not path.exists():
        return {}
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TorrcastError(phrase("main_config.unreadable", path=path, reason=exc)) from exc
    if not isinstance(raw, dict):
        raise InvalidConfigObjectError(path, phrase("main_config.not_an_object", path=path))
    return raw


def save_config(config: Config) -> None:
    """Записать свои ключи атомарно, оставив чужие ключи файла нетронутыми."""
    path = config_path()
    _write_atomic(path, {**_stored(path), **asdict(config)})
