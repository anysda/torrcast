"""Тесты парсера имён раздач и нумерации франшиз.

Фикстуры пока рукописные, по образцу типовых русских раздач. На этапе 1 (§7 ТЗ)
сюда приезжает корпус реальной выдачи трекеров.
"""

from __future__ import annotations

import pytest

from torrcast.parse import (
    Release,
    cluster,
    parse_episode,
    parse_release_name,
    slugify,
    split_franchise_index,
)


def test_parses_typical_russian_release() -> None:
    """Имя раздачи разбирается в название, оригинал, год, качество и кодек."""
    release = parse_release_name("Матрица / The Matrix (1999) BDRip 1080p x264 Дубляж")

    assert release.title == "Матрица"
    assert release.original == "The Matrix"
    assert release.year == 1999
    assert release.quality == "1080p"
    assert release.codec == "H.264"
    assert "Дубляж" in release.voices
    assert not release.is_hevc


def test_hevc_is_flagged() -> None:
    """HEVC помечается — по умолчанию его никогда не берём (§3 ТЗ)."""
    release = parse_release_name("Дюна / Dune (2021) UHD BDRemux 2160p HEVC Дубляж")

    assert release.quality == "2160p"
    assert release.is_hevc


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Cyberpunk.Edgerunners.s01e05.1080p", (1, 5)),
        ("Киберпанк 2x5 WEB-DL", (2, 5)),
        ("Киберпанк: Бегущие по краю, 2 сезон 5 серия", (2, 5)),
    ],
)
def test_parses_season_episode(text: str, expected: tuple[int, int]) -> None:
    """sNeM понимается во всех трёх записях из §2.4 ТЗ."""
    episode = parse_episode(text)

    assert episode is not None
    assert (episode.season, episode.episode) == expected


def test_plain_name_has_no_episode() -> None:
    """Фильм без sNeM эпизодом не считается."""
    assert parse_episode("Матрица / The Matrix (1999) BDRip 1080p") is None


def test_franchise_index_is_split_off_but_year_is_not() -> None:
    """«матрица 2» — номер во франшизе, «матрица 1999» — не номер (§2.2 ТЗ)."""
    assert split_franchise_index("матрица 2") == ("матрица", 2)
    assert split_franchise_index("тачки") == ("тачки", None)
    assert split_franchise_index("матрица 1999") == ("матрица 1999", None)


def test_cluster_orders_franchise_by_year() -> None:
    """Франшиза = кластеры по названию, отсортированные по году: индекс = номер."""
    releases = [
        _release("Тачки", 2017, seeders=10),
        _release("Тачки", 2006, seeders=200),
        _release("Тачки", 2011, seeders=50),
        _release("Тачки", 2006, seeders=120),
    ]

    pictures = cluster(releases)

    assert [p.year for p in pictures] == [2006, 2011, 2017]
    assert len(pictures[0].releases) == 2
    assert pictures[0].key == "movie:тачки:2006"


def test_best_release_prefers_seeders_and_avoids_hevc() -> None:
    """Дефолт — самый обсиженный H.264; HEVC уступает даже с бо́льшими сидами."""
    picture = cluster(
        [
            _release("Тачки", 2006, seeders=500, codec="HEVC"),
            _release("Тачки", 2006, seeders=200),
            _release("Тачки", 2006, seeders=90),
        ]
    )[0]

    best = picture.best_release

    assert best is not None
    assert best.seeders == 200
    assert not best.is_hevc


def test_slugify_is_stable_for_state_keys() -> None:
    """Ключ состояния не зависит от регистра, ё и пунктуации (§4 ТЗ)."""
    assert slugify("Киберпанк: Бегущие по краю") == "киберпанк-бегущие-по-краю"
    assert slugify("Ёлки  2") == slugify("елки 2")


def _release(title: str, year: int, seeders: int = 0, codec: str = "H.264") -> Release:
    return Release(
        raw_name=f"{title} ({year})",
        title=title,
        year=year,
        quality="1080p",
        codec=codec,
        seeders=seeders,
    )
