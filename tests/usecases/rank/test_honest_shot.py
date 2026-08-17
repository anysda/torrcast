"""Запасной подтвердил своё имя: кадр из ffprobe не ниже заявленной ступени."""

from __future__ import annotations

from tests.usecases.rank.releases import media, rel
from torrcast.usecases.rank.honest_shot import honest_shot


def test_a_name_confirmed_by_the_stream_is_honest() -> None:
    assert honest_shot(rel(quality="1080p"), media())
    assert not honest_shot(rel(quality="1080p"), media(height=574, width=1150))


def test_a_silent_name_is_enough_when_hd_is_inside() -> None:
    assert honest_shot(rel(quality=None), media(height=720, width=1280))
    assert not honest_shot(rel(quality=None), media(height=574, width=1150))


def test_a_silent_passport_confirms_nothing() -> None:
    assert not honest_shot(rel(quality="1080p"), media(height=0, width=0))
