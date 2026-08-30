"""Проверки выбора языка Telegram."""

from pytest import MonkeyPatch

from tgbot.i18n import LANGUAGE_ENV, i18n


def test_english_is_default_and_environment_is_the_tc929_seam(monkeypatch: MonkeyPatch) -> None:
    assert i18n("invalid_choice") == "Unknown menu step."
    monkeypatch.setenv(LANGUAGE_ENV, "ru")
    assert i18n("invalid_choice") == "Нет такого шага меню."
