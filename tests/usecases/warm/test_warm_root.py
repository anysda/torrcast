"""Куда греть: настройка, переопределение окружением и умолчание."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.warm_settings import WARM_DIR
from torrcast.usecases.warm.settings import WARM_ENV
from torrcast.usecases.warm.warm_root import warm_root

if TYPE_CHECKING:
    import pytest


def test_the_configured_place_wins_over_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Настроенный каталог и есть ответ, пока окружение молчит."""
    monkeypatch.delenv(WARM_ENV, raising=False)

    assert str(warm_root("/место/прогрева")) == "/место/прогрева"


def test_the_environment_overrides_the_configured_place(monkeypatch: pytest.MonkeyPatch) -> None:
    """``TORRCAST_WARM`` сильнее настройки: тестовый прогон не пишет в боевое хранилище."""
    monkeypatch.setenv(WARM_ENV, "/своё")

    assert str(warm_root("/боевое")) == "/своё"


def test_an_empty_setting_falls_back_to_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустая настройка - не «греть в текущий каталог», а умолчание."""
    monkeypatch.delenv(WARM_ENV, raising=False)

    assert str(warm_root("")) == WARM_DIR
