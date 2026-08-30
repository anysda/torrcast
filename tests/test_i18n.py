"""Проверки выбора языка Telegram."""

from pytest import MonkeyPatch

from tgbot.i18n import i18n


def test_english_is_default_and_russian_is_explicit() -> None:
    assert i18n("invalid_choice") == "Unknown menu step."
    assert i18n("invalid_choice", "ru") == "Нет такого шага меню."


def test_the_environment_cannot_choose_the_default(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_LANGUAGE", "ru")

    assert i18n("invalid_choice") == "Unknown menu step."
