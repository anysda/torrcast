"""Проверяет, что контейнер узнаётся по имени файла раздачи, а чужое имя не выдумывается."""

import pytest

from torrcast.adapters.stream_pack.container_of import container_of


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Moana.2.2024.2160p.mkv", "mkv"),
        ("clip.WEBM", "mkv"),
        ("Moana.mp4", "mp4"),
        ("Moana.M4V", "mp4"),
        ("Moana.mov", "mp4"),
        ("Moana.avi", ""),
        ("Moana", ""),
        ("", ""),
    ],
)
def test_the_container_is_read_from_the_name_of_the_release_file(name: str, kind: str) -> None:
    """Подсказка нужна одному месту: карта из кэша прошлой версии контейнера не знает.

    Без неё продолжение по такому фильму грело бы восемь мегабайт головы до конца
    времён. Чужое расширение - пустая строка, а не догадка.
    """
    assert container_of(name) == kind
