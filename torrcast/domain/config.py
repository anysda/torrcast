"""Настройки показа как значение: что задал человек и чем это дополнено по умолчанию.

Файл настроек читает и пишет адаптер (:mod:`torrcast.adapters.filesystem.state`), а
правила и сценарии получают уже готовое значение.
"""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain._config_recode import _ConfigRecode
from torrcast.domain.json_model import json_model
from torrcast.domain.json_value import JsonValue
from torrcast.domain.warm_settings import WARM_BUDGET, WARM_DIR


@dataclass(slots=True)
class Config(_ConfigRecode):
    """Настройки. Обязателен только ``tv``; остальное имеет рабочие дефолты."""

    #: Прогревать весь фильм на диск фоном (:mod:`torrcast.usecases.warm`), чтобы показ переживал
    #: обрыв связи. ``false`` - показ живёт только окном в tmpfs, как раньше.
    warm: bool = True
    #: Где лежит прогретое. **Диск, не tmpfs**: целый фильм в память не влезает.
    warm_dir: str = WARM_DIR
    #: Бюджет диска под всё прогретое, ГБ (:data:`~torrcast.domain.warm_settings.WARM_BUDGET`).
    warm_budget_gb: float = WARM_BUDGET / 1e9
    #: Во сколько раз быстрее реального времени идёт прогрев
    #: (:data:`torrcast.usecases.warm.WARM_RATE`).
    warm_rate: float = 4.0

    @classmethod
    def from_json(cls, data: dict[str, JsonValue]) -> Config:
        """Собрать конфиг из словаря, молча игнорируя незнакомые ключи."""
        return json_model(cls, data, cls.__dataclass_fields__)
