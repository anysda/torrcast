"""Написанные ключи настроек: то же значение из файла и из умолчания различимо."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.config_keys import config_keys


def test_only_the_keys_actually_written_are_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ответ - ровно то, что стоит в файле: умолчания в него не подмешиваются.

    Спрашивают это ради следа: одинаковое число могло прийти из файла стенда или из
    умолчания, а задним числом по одному значению их не отличить.
    """
    path = tmp_path / "config.json"
    path.write_text('{"tv": "10.0.0.50", "receiver": "mock"}', encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    assert config_keys() == frozenset({"tv", "receiver"})


def test_a_key_that_is_not_a_setting_is_not_counted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Чужой ключ в файле настройкой не становится: список полей ведёт домен."""
    path = tmp_path / "config.json"
    path.write_text('{"tv": "10.0.0.50", "выдумка": 1}', encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    assert config_keys() == frozenset({"tv"})


def test_a_missing_or_broken_file_has_no_written_keys_at_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ни файла, ни разбора - значит написанных ключей нет; ошибку назовёт чтение."""
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "нет.json"))
    assert config_keys() == frozenset()

    path = tmp_path / "config.json"
    path.write_text("{не json", encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))
    assert config_keys() == frozenset()
