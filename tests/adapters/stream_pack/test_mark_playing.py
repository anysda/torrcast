"""Проверяет отметку «картинка на экране»: она появляется и не роняет показ."""

from pathlib import Path

import pytest

from torrcast.adapters.stream_pack.mark_playing import mark_playing
from torrcast.adapters.stream_pack.playing_flag import playing_flag


def test_the_show_that_saw_a_picture_leaves_a_mark(tmp_path: Path) -> None:
    """С этой секунды на экране есть изображение, и доказывает это файл, а не память."""
    mark_playing(tmp_path)
    assert playing_flag(tmp_path).exists()


def test_a_directory_that_is_gone_does_not_kill_the_show(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Каталог вычистили окном - показ от этого не падает: отметка не главнее картинки.

    Но и молчать тут нельзя: не легло единственное доказательство картинки, по которому
    ``cast`` отличает показ от неудачного старта, и без строки в журнале разбираться в
    погашенном показе было бы не по чему (TC-884).
    """
    gone = tmp_path / "нет-такого"

    mark_playing(gone)  # без исключения

    said = capsys.readouterr().out
    assert str(playing_flag(gone)) in said, "названо ровно то, что не легло"
    assert "playing flag did not land" in said
