"""Зеркало :mod:`torrcast.domain._playing`: начало записи состояния - это та же запись.

Файл разъехался ради потолка раскладки, и мера тут ровно об этом: порядок полей обязан
остаться прежним, потому что им задан порядок ключей в файле состояния, а умолчания
паспорта обязаны по-прежнему значить «не спрашивали», а не измеренный ноль.
"""

from __future__ import annotations

from dataclasses import asdict, fields

from torrcast.domain._playing import _Playing
from torrcast.domain.entry import Entry


def test_the_record_keeps_the_order_of_its_keys_on_disk() -> None:
    """Поля показа стоят первыми и в том же порядке: файл состояния пишется этим порядком."""
    named = [item.name for item in fields(Entry)]

    assert named[: len(fields(_Playing))] == [item.name for item in fields(_Playing)]
    assert named[:3] == ["title", "magnet", "kind"]
    assert named[-3:] == ["query", "done", "updated"]


def test_a_fresh_record_asks_for_nothing_but_the_picture_and_the_torrent() -> None:
    """Остальное имеет умолчания: запись заводит показ, а не анкета."""
    entry = Entry(title="Дюна", magnet="magnet:?xt=1")

    assert asdict(entry)["title"] == "Дюна"
    assert entry.kind == "movie"


def test_the_passport_defaults_mean_not_asked_and_not_measured_zero() -> None:
    """Ноль тут - «паспорт не спрашивали», и путать его с измеренным нулём нельзя.

    Спутай - и запись, обошедшая отбор, уехала бы на ТВ с чужим решением о перекоде.
    """
    empty = Entry(title="Дюна", magnet="m")

    assert (empty.frame, empty.depth, empty.vbps) == (0, 0, 0.0)
    assert (empty.codec, empty.quality) == ("", "")
    assert empty.hdr is False


def test_the_live_show_marks_start_empty_and_belong_to_the_current_file() -> None:
    """Хэш раздачи, прогрев и темнота относятся к тому файлу, который играет сейчас."""
    entry = Entry(title="Сериал", magnet="m", kind="tv", torrent="a1", warm=90.0, dark=17.0)

    moved = entry.advance()

    assert (entry.torrent, entry.warm, entry.dark) == ("a1", 90.0, 17.0)
    assert (moved.warm, moved.dark, moved.dark_why) == (0.0, 0.0, "")
    assert moved.torrent == "a1", "раздача та же - её держит тот же живой показ"
