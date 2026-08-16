"""Проверки модели студии озвучки."""

from torrcast.domain.studio import Studio


def test_rank_override_is_kept() -> None:
    assert Studio("двухголосый", ranks="многоголосый").ranks == "многоголосый"
