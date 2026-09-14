"""Зеркало свежего языка продукта из файла настройки."""

from __future__ import annotations

from pathlib import Path

import pytest

import torrcast.adapters.filesystem.state.chosen_language as chosen_language_module
from torrcast.adapters.filesystem.state.chosen_language import chosen_language
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.config import Config


def test_the_current_setting_is_read_on_every_call() -> None:
    save_config(Config(language="en"))
    assert chosen_language() == "en"

    save_config(Config(language="ru"))

    assert chosen_language() == "ru"


def test_a_broken_setting_falls_back_to_english(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text('{"language": ', encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(broken))

    assert chosen_language() == "en"


def test_an_unchanged_setting_is_not_read_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Надпись спрашивает язык на каждом зове, и круг поиска читал файл ~1300 раз."""
    save_config(Config(language="ru"))
    assert chosen_language() == "ru"

    def unread() -> Config:
        raise AssertionError("файл не менялся, а его читают снова")

    monkeypatch.setattr(chosen_language_module, "load_config", unread)

    assert chosen_language() == "ru"
