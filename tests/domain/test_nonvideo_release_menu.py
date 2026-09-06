"""Ноты, обои, аудиокниги и игры с .64 не должны становиться картинами меню."""

import pytest

from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.cluster import cluster
from torrcast.domain.raw_result import RawResult


@pytest.mark.parametrize(
    "name",
    [
        "Metallica - King Nothing - Sheet Music/Guitar Tablature",
        "Пираты Карибского моря: На странных берегах: Wallpapers",
        "Коллекция Аудиокниг. Часть 2 [370 книг] (1994-2017) M4B",
        "Браун Дэн - Сборник аудиокниг (2001-2017) (2005-2017) OPUS",
        "Жюль Верн - Cборник аудиокниг (2015) AAC",
        "[CD] Pirates of the Caribbean / Корсары II (2): Пираты Карибского Моря [P] "
        "[RUS / RUS] (2003, RPG) (1.03) [Rebuild, 1.03, Mod]",
        "[DL] Fallout 2 [P] [RUS / RUS] (1998, RPG) [Fallout: Sonora + DLC, Mod]",
        "[PS2] Ratchet: Deadlocked (Gladiator) [RUS/Multi3|NTSC]",
    ],
)
def test_nonvideo_never_becomes_a_menu_picture(name: str) -> None:
    assert cluster(to_releases([RawResult(name, "a" * 40)])) == []


@pytest.mark.parametrize("audio", ["M4B", "OPUS", "AAC", "Sheet Music", "Wallpapers"])
def test_video_with_audio_or_extras_keeps_its_place(audio: str) -> None:
    rows = [RawResult(f"Концерт (2020) WEBRip 1080p + {audio}", "a" * 40)]
    pictures = cluster(to_releases(rows))
    assert len(pictures) == 1
    assert pictures[0].title == "Концерт"
