"""Зеркально проверяет отладочную ручку таблицы релизов."""

from torrcast.usecases.releases_command import _cmd_releases


def test_releases_command_is_importable() -> None:
    assert _cmd_releases is not None
