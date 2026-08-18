"""Зеркало честных строк о сериалах, выпавших из меню: сезона нет, а раздачи есть."""

from __future__ import annotations

from tests.usecases.discover.world import franchise, row
from torrcast.domain.episode import Episode
from torrcast.usecases.discover.season_gaps import season_gaps

_KITCHEN = [
    row("Кухня 6 / Kuhnya 6 (2017) WEB-DL 1080p | 6 сезон, 1-20 из 20", "a"),
    row("Кухня 6 / Kuhnya 6 (2017) SATRip | 6 сезон [1-20 из 20]", "b"),
]


def test_a_series_dropped_from_the_menu_gets_a_line_about_its_seasons() -> None:
    """🔴 Молчаливых отказов не бывает: строка говорит, сколько раздач и какие сезоны."""
    found = franchise("кухня", _KITCHEN)

    lines = season_gaps(found, set(), Episode(1, 1))

    assert len(lines) == 1
    assert "раздач 2" in lines[0]
    assert "сезона 1 среди них нет - названы 6" in lines[0]


def test_a_picture_that_reached_the_menu_says_nothing() -> None:
    """Картина в меню - о ней человек и так прочитает списком."""
    found = franchise("кухня", _KITCHEN)

    assert season_gaps(found, {found[0].key}, Episode(1, 1)) == []


def test_names_silent_about_seasons_are_not_a_refusal() -> None:
    """Молчание имени - «может быть», а не «нет»: врать про такую картину нельзя."""
    silent = franchise("психо", [row("Психо / Psycho (1960) BDRip 1080p")])

    assert season_gaps(silent, set(), Episode(1, 1)) == []


def test_without_an_asked_episode_the_first_season_is_the_question() -> None:
    """Серию не называли - спрашивают первый сезон, о нём строка и говорит."""
    lines = season_gaps(franchise("кухня", _KITCHEN), set(), None)

    assert lines and "сезона 1" in lines[0]
