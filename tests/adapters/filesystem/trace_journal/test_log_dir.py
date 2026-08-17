"""Каталог ленты: рядом с состоянием, пока его не увели переменной окружения."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state import state_path
from torrcast.adapters.filesystem.trace_journal.log_dir import LOG_ENV, log_dir


def test_the_trace_lies_next_to_the_state_unless_it_is_sent_elsewhere(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """По умолчанию лента живёт рядом с состоянием, а переопределение уводит её целиком.

    Рядом с состоянием - потому что это одно хозяйство одного пользователя: разъедься они,
    и `cast log` читал бы не тот след, который писал показ. Переопределение нужно ровно
    затем, чтобы заведомо тестовый или локальный запуск не мешал свои записи в общую ленту.
    """
    monkeypatch.delenv(LOG_ENV, raising=False)
    assert log_dir() == state_path().parent

    monkeypatch.setenv(LOG_ENV, str(tmp_path / "след"))
    assert log_dir() == tmp_path / "след"


def test_the_name_of_the_override_is_the_one_the_unit_gets_in_its_environment() -> None:
    """Имя переменной - договор двух процессов: команда ставит её, юнит показа читает."""
    assert LOG_ENV == "TORRCAST_LOG"
