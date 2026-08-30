"""Закрытое хранение настройки Telegram с переопределяемым путём."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

CONFIG_ENV = "TORRCAST_TELEGRAM_CONFIG"
DEFAULT_CONFIG = "/etc/torrcast/config.json"


@dataclass(slots=True)
class Config:
    """Данные Bot API, которые мастер проверяет перед сохранением."""

    token: str = ""
    chat_id: str = ""
    proxy: str = ""

    @staticmethod
    def path() -> Path:
        """Назвать боевой либо переопределённый тестом путь."""
        return Path(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG))

    @classmethod
    def _stored(cls) -> dict[str, Any]:
        """Файл как он есть; отсутствие файла - пустой словарь.

        🔴 Файл общий с продуктом: рядом с тремя ключами бота в нём живут ключи показа
        (``tv``, ``hls_*``, ``warm*`` и прочие), которых мастер не знает. Запись своего
        дата-класса ЦЕЛИКОМ стирала их все (TC-934).

        Битый файл роняет запись нарочно: разобрать чужие ключи нечем, а написать поверх
        значит стереть настройку продукта молча. Читает такой файл и :meth:`load` -
        тем же исключением.
        """
        path = cls.path()
        if not path.exists():
            return {}
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"битая настройка {path}: ожидался объект JSON")
        return raw

    @classmethod
    def _write(cls, payload: dict[str, Any]) -> None:
        """Атомарно записать весь файл с режимом 0600: читают настройку на ходу."""
        path = cls.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)

    @classmethod
    def load(cls) -> Config:
        """Прочитать настройку, а отсутствие считать пустой настройкой."""
        raw = cls._stored()
        return cls(
            str(raw.get("token", "")), str(raw.get("chat_id", "")), str(raw.get("proxy", ""))
        )

    def save(self) -> None:
        """Атомарно записать свои три ключа, не тронув чужих, с режимом 0600."""
        self._write({**self._stored(), **asdict(self)})

    @classmethod
    def remove(cls) -> bool:
        """Убрать свои ключи и ответить, была ли настройка.

        Убираются ровно свои: файл общий, и снятие бота не имеет права уносить с собой
        настройку показа. Файла не остаётся только тогда, когда в нём и не было ничего,
        кроме ключей бота.
        """
        stored = cls._stored()
        mine = {item.name for item in fields(cls)}
        rest = {key: value for key, value in stored.items() if key not in mine}
        if len(rest) == len(stored):
            return False
        if rest:
            cls._write(rest)
        else:
            cls.path().unlink()
        return True
