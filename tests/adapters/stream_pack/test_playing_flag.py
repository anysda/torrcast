"""Проверяет путь флажка «картинка на экране»: имя одно на весь показ."""

from pathlib import Path

from torrcast.adapters.stream_pack.playing_flag import playing_flag
from torrcast.domain.hls_settings import PLAYING_FLAG


def test_the_flag_lies_in_the_pack_directory_under_its_agreed_name() -> None:
    """Имя флажка - договор двух сторон: его ставит показ, а спрашивают щупы и сторож.

    Разъедься имена - и «картинка была» перестало бы доказываться вовсе, молча.
    """
    assert playing_flag(Path("/tmp/пак")) == Path("/tmp/пак") / PLAYING_FLAG
