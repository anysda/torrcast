"""Суточное обновление индекса серий IMDb, без шага человека.

Установщик собирает индекс один раз (`install.sh`, ``setup_episodes``), а выгрузка IMDb
обновляется у них ежедневно: новые сезоны и серии карточка видит только из свежей.
Служба живёт неделями, поэтому раз в сутки она сама зовёт сборку отдельным процессом
(:func:`torrcast.adapters.wiki.imdb_episode_index.refresh.refresh`). Неизменившуюся
выгрузку сборка узнаёт по заголовкам ответа и не качает.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

from torrcast.adapters.wiki.imdb_episode_index.refresh import refresh
from torrcast.domain.facts.settings import EPISODES_PATH, EPISODES_URL

#: Сколько ждать между обновлениями и перед первым: старт службы греет полки и справку,
#: и сборка им не соседка; установщик к этому времени индекс уже собрал.
DAY = 24 * 3600.0
FIRST = 600.0


def refresh_episodes(
    rounds: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    build: Callable[[str, Path], bool] = refresh,
) -> None:
    """Завести обновление фоном; ``rounds`` и подделки - только для зеркала."""

    def loop() -> None:
        left = rounds
        sleep(FIRST)
        while left is None or left > 0:
            build(EPISODES_URL, EPISODES_PATH)
            left = None if left is None else left - 1
            sleep(DAY)

    thread = threading.Thread(target=loop, daemon=True, name="refresh-episodes")
    thread.start()
    if rounds is not None:
        thread.join()


__all__ = ["refresh_episodes"]
