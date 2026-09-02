"""Общее для тестов интеграции Home Assistant и их отвод от основного прогона.

Home Assistant в зависимостях torrcast не значится и значиться не будет, поэтому
основной гейт этот каталог не собирает вовсе: без переменной, которую ставит только
`scripts/hass-integration-gate`, каждый файл отсюда отводится ещё до импорта.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

#: Переменная, которой запускатель говорит, что Home Assistant в венве есть.
GATE_VARIABLE = "TORRCAST_HASS_GATE"


def pytest_ignore_collect(collection_path: Path) -> bool | None:
    """Без переменной запускателя каталог не собирается вовсе.

    Отвод сделан хуком, а не маркером: маркер отбирает уже собранное, то есть после
    импорта файла, а импорт тут первым делом тянет Home Assistant, которого в венве
    гейта нет и не будет. Отказ на этом шаге - `ImportError` при сборе, то есть
    красный основной прогон, а не пропущенный тест.
    """
    if os.environ.get(GATE_VARIABLE):
        return None
    return collection_path.is_dir() or collection_path.suffix == ".py"


HOST = "192.0.2.11"
PORT = 8479
BASE = f"http://{HOST}:{PORT}"
DOMAIN = "torrcast"
#: Записанный ответ серве, а не собранный из запроса: подделка обязана быть второй
#: стороной, а не зеркалом. Снимок с живого стенда ложится сюда же, поверх этого файла.
RECORDED = Path(__file__).parent / "fixtures" / "state-playing.json"


def snapshot(**changes: Any) -> dict[str, Any]:
    """Записанный снимок серве с заменёнными полями."""
    recorded: dict[str, Any] = json.loads(RECORDED.read_text(encoding="utf-8"))
    recorded.update(changes)
    return recorded


def mount() -> None:
    """Кладёт `custom_components/` репозитория в путь одноимённого пакета.

    Пакет `custom_components` есть у самого `pytest-homeassistant-custom-component`, и
    он обычный, с `__init__.py`: импорт находит его, а не каталог репозитория, и
    Home Assistant отвечает «Integration not found» на живой интеграции. Дописанный
    путь чинит ровно это и ничего больше - искать интеграцию Home Assistant всё так же
    ходит своим штатным способом.
    """
    import custom_components

    home = str(Path(__file__).resolve().parents[2] / "custom_components")
    if home not in custom_components.__path__:
        custom_components.__path__.append(home)


def sent(call: tuple[Any, ...]) -> Any:
    """Тело запроса из записи подделки: она хранит его строкой либо объектом."""
    body = call[2]
    if isinstance(body, (bytes, str)):
        return json.loads(body)
    return body
