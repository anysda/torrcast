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
from torrcast.domain.owned_config_keys import OWNED_BY_HUMAN
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
    """Записать ключи человека атомарно, оставив прочие ключи файла нетронутыми.

    🔴 TC-669. Пишется не весь дата-класс, а только то, чем человек владеет
    (:data:`~torrcast.domain.owned_config_keys.OWNED_BY_HUMAN`). Запись целиком
    вмораживала в файл ВСЕ умолчания кода - пороги битрейта, окно сегментов, бюджет
    прогрева, - хотя человек не называл ни одного из них: ``cast --tv`` менял один
    адрес и дописывал тридцать чужих чисел. Стоило это дважды. След
    (:func:`~torrcast.adapters.filesystem.state.config_keys.config_keys`) после такой
    записи считал файловым КАЖДЫЙ порог и врал про источник числа, а установка получала
    полный чисел файл, из которого их же и вычищала.

    Чужие ключи файла (``token``, ``chat_id``, ``proxy`` телеграм-бота) при этом
    остаются нетронутыми, как и раньше: файл общий, и запись своего среза целиком
    стёрла бы боевой токен (TC-934).
    """
    path = config_path()
    mine = {key: value for key, value in asdict(config).items() if key in OWNED_BY_HUMAN}
    _write_atomic(path, {**_stored(path), **mine})
