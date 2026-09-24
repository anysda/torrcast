"""Игры с консолью после года и встречный живой корпус фильмов."""

from pathlib import Path

import pytest

from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.nonvideo_release import _is_nonvideo_release
from torrcast.domain.raw_result import RawResult

_CORPUS = Path(__file__).parents[1] / "fixtures" / "nonvideo_console_titles.tsv"

_LIVE_GAMES = {
    "Тачки 2 / Cars 2: The Video Game (2011) PSP",
    "Гарри Поттер и Дары Смерти - Дилогия [Cobra ODE / E3 ODE PRO] (2010-2011) PS3",
    "Гарри Поттер и Орден Феникса / Harry Potter and the Order of the Phoenix "
    "[Cobra ODE / E3 ODE PRO] (2007) PS3",
    "Гарри Поттер и Принц-Полукровка / Harry Potter and the Half-Blood Prince "
    "[Cobra ODE / E3 ODE PRO] (2009) PS3",
}


def _rows() -> list[tuple[str, bool, str]]:
    lines = _CORPUS.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "query\tnonvideo\ttitle"
    cells = (line.split("\t", 2) for line in lines[1:])
    return [(query, mark == "1", title) for query, mark, title in cells]


@pytest.mark.parametrize(
    "name",
    [
        "Тачки 2 / Cars 2: The Video Game (2011) PSP",
        "Gran Turismo 4 (2004) PS2",
        "Harry Potter and the Order of the Phoenix (2007) PS3",
        "Marvel's Spider-Man (2018) PS4",
        "Mario Kart DS (2005) NDS",
        "Mario Kart 7 (2011) 3DS",
        "Tearaway (2013) PSVita",
        "Tearaway (2013) PS Vita",
        "Cars 2: The Video Game (2011) Wii",
        "Mario Kart 8 (2014) WiiU",
        "Mario Kart 8 Deluxe (2017) Switch",
        "Mario Kart 8 Deluxe (2017) Nintendo Switch",
        "Mario Kart 8 Deluxe (2017) NSW",
        "Forza Horizon 2 (2014) Xbox One",
    ],
)
def test_a_game_marked_by_its_console_after_the_year_is_nonvideo(name: str) -> None:
    assert _is_nonvideo_release(name)


def test_switch_titles_and_console_shaped_release_groups_stay_video() -> None:
    assert not _is_nonvideo_release("Switch (1991)")
    assert not _is_nonvideo_release("Подмена / Switch (1991) BDRip-AVC")
    assert not _is_nonvideo_release("Spider-Man: Into the Spider-Verse (2018) BDRip 1080p-Wii")


def test_live_console_games_never_become_releases() -> None:
    rows = [RawResult(title, f"{number:040x}") for number, title in enumerate(_LIVE_GAMES)]
    assert to_releases(rows) == []


def test_the_live_two_sided_corpus_keeps_every_recorded_verdict() -> None:
    rows = _rows()
    assert len(rows) == 366
    assert sum(expected for _query, expected, _title in rows) == 74
    mismatches = [
        (query, title, expected, _is_nonvideo_release(title))
        for query, expected, title in rows
        if _is_nonvideo_release(title) is not expected
    ]
    assert mismatches == []
    assert {title for _query, expected, title in rows if expected and title in _LIVE_GAMES} == (
        _LIVE_GAMES
    )
