"""Проверяет снятие флажка картинки: следующий показ обязан доказать её заново."""

from pathlib import Path

from torrcast.adapters.stream_pack.forget_playing import forget_playing
from torrcast.adapters.stream_pack.mark_playing import mark_playing
from torrcast.adapters.stream_pack.playing_flag import playing_flag


def test_the_mark_of_the_previous_show_is_taken_away(tmp_path: Path) -> None:
    """Флажок прошлого показа картинку нового не доказывает - и остаться не должен."""
    mark_playing(tmp_path)
    forget_playing(tmp_path)
    assert not playing_flag(tmp_path).exists()


def test_there_is_nothing_to_take_away_and_that_is_fine(tmp_path: Path) -> None:
    """Флажка не было - не беда: снимать нечего, а падать тут нельзя."""
    forget_playing(tmp_path)
    forget_playing(tmp_path / "нет-такого")
