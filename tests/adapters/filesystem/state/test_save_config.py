"""Запись настроек: файл появляется вместе с каталогом и читается обратно тем же."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.config import Config


def test_what_was_saved_is_what_is_read_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Запись и чтение - одна раскладка: разойдись они, настройка молча теряется."""
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))

    save_config(Config(tv="10.0.0.50"))

    assert load_config().tv == "10.0.0.50"


def test_the_directory_is_made_on_the_way_because_the_first_run_has_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Первичная настройка идёт до того, как каталог настроек кто-либо завёл."""
    path = tmp_path / "ещё-нет" / "config.json"
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    save_config(Config(tv="10.0.0.50"))

    assert path.exists()


def test_nothing_temporary_is_left_next_to_the_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Запись атомарная, но мусор после себя она оставлять не имеет права."""
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))

    save_config(Config(tv="10.0.0.50"))

    assert [path.name for path in tmp_path.iterdir()] == ["config.json"]
