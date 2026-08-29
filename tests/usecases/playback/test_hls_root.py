"""Куда класть сегменты показа: явная настройка и переопределение окружением."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain._config_hls import DEFAULT_HLS_DIR
from torrcast.usecases.playback.hls_root import HLS_ENV, hls_root

if TYPE_CHECKING:
    import pytest


def test_an_explicit_place_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Явно заданный каталог (свой ``tmp_path`` теста) сильнее подмены окружением."""
    monkeypatch.setenv(HLS_ENV, "/чужой-сандбокс")

    assert str(hls_root("/свой/tmp_path")) == "/свой/tmp_path"


def test_the_unchanged_default_yields_to_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Умолчание, оставшееся неизменным, уступает подмене - иначе тест уходит в боевое."""
    monkeypatch.setenv(HLS_ENV, "/сандбокс/hls")

    assert str(hls_root(DEFAULT_HLS_DIR)) == "/сандбокс/hls"


def test_without_the_environment_the_default_stays_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Подмены нет - умолчание доезжает до боевого места как было."""
    monkeypatch.delenv(HLS_ENV, raising=False)

    assert str(hls_root(DEFAULT_HLS_DIR)) == DEFAULT_HLS_DIR
