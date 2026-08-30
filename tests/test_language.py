"""Зеркало языка бота: он берётся из настройки продукта и спрашивается заново."""

from __future__ import annotations

from pathlib import Path

import pytest

from tgbot.language import language
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.config import Config


def test_the_language_of_the_bot_is_the_setting_of_the_product() -> None:
    save_config(Config(tv="10.0.0.50", language="ru"))

    assert language() == "ru"


def test_a_setting_changed_under_a_live_process_is_seen_at_once() -> None:
    """Бот живёт долго: прочитай он язык однажды, `cast --ru` из чата не подействовал бы."""
    save_config(Config(tv="10.0.0.50", language="en"))
    assert language() == "en"

    save_config(Config(tv="10.0.0.50", language="ru"))

    assert language() == "ru"


def test_a_missing_setting_is_english_and_a_broken_one_does_not_kill_the_polling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Битая настройка - не повод уронить опрос: отказ человеку назовёт сама команда."""
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "нет.json"))
    assert language() == "en"

    broken = tmp_path / "битый.json"
    broken.write_text('{"language": ', encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(broken))

    assert language() == "en"
