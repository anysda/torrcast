"""Зеркало студий записи: имена из состояния обратно в знакомые студии."""

from __future__ import annotations

from torrcast.domain.studios_named import studios_named


def test_the_names_come_back_as_studios_in_their_own_order() -> None:
    """Порядок несёт смысл: по нему голые дорожки пака узнают свою студию."""
    found = studios_named(["Good People", "The Kitchen Russia"])

    assert [studio.name for studio in found] == ["Good People", "The Kitchen Russia"]


def test_an_unknown_name_drops_out_and_nothing_is_doubled() -> None:
    """Студия с несколькими ключами таблицы приходит один раз, чужое имя - ни разу."""
    found = studios_named(["Неизвестная студия", "The Kitchen Russia"])

    assert [studio.name for studio in found] == ["The Kitchen Russia"]
