"""Закрытое хранение настройки Telegram с переопределяемым путём."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

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
    def load(cls) -> Config:
        """Прочитать настройку, а отсутствие считать пустой настройкой."""
        path = cls.path()
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            str(raw.get("token", "")), str(raw.get("chat_id", "")), str(raw.get("proxy", ""))
        )

    def save(self) -> None:
        """Атомарно записать проверенную настройку с режимом 0600."""
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)

    @classmethod
    def remove(cls) -> bool:
        """Удалить настройку и ответить, существовала ли она."""
        path = cls.path()
        if not path.exists():
            return False
        path.unlink()
        return True
