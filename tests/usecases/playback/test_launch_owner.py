"""Зеркало метки подъёма: свой подъём узнаёт, что его снял чужой запуск."""

from __future__ import annotations

from pathlib import Path

from torrcast.usecases.playback.launch_owner import LaunchOwner


def test_a_launch_owns_its_show_until_another_launch_claims_it(tmp_path: Path) -> None:
    """Вторая метка поверх первой - первый подъём снят, второй свой."""
    mine = LaunchOwner.claim(tmp_path)
    assert mine.taken_over() is False, "свою же метку чужой звать нельзя"

    other = LaunchOwner.claim(tmp_path)

    assert mine.taken_over() is True
    assert other.taken_over() is False


def test_an_unwritable_place_claims_nothing_and_blames_nobody(tmp_path: Path) -> None:
    """Каталог не создать - метки нет, и ожидание идёт прежним путём, а не отменой."""
    blocked = tmp_path / "file"
    blocked.write_text("")

    owner = LaunchOwner.claim(blocked / "hls")

    assert owner.token == ""
    assert owner.taken_over() is False
