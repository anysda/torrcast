"""Тесты парсера имён раздач и нумерации франшиз.

Фикстуры — реальные имена раздач, отобранные из корпуса в 21 540 уникальных имён
(§7, этап 1): ``tests/fixtures/names.txt`` (650 имён, все шаблоны) и
``tests/fixtures/expected.tsv`` (выверенная глазами таблица ожиданий).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import NamedTuple

import pytest

from torrcast.parse import (
    Picture,
    Release,
    cluster,
    franchise_key,
    parse_episode,
    parse_release_name,
    part_number,
    pick_franchise,
    slugify,
    split_franchise_index,
)

FIXTURES = Path(__file__).parent / "fixtures"


class Expected(NamedTuple):
    """Строка выверенной таблицы ожиданий."""

    raw_name: str
    title: str
    original: str
    year: str
    quality: str
    codec: str
    source: str
    hdr: str
    voices: str
    season: str
    episode: str
    kind: str


def _load_expected() -> list[Expected]:
    with (FIXTURES / "expected.tsv").open(encoding="utf-8") as fh:
        rows = [r for r in csv.reader(fh, delimiter="\t") if r and not r[0].startswith("#")]
    return [Expected(*row) for row in rows]


def _load_names() -> list[str]:
    lines = (FIXTURES / "names.txt").read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]


EXPECTED = _load_expected()
NAMES = _load_names()


def test_fixtures_are_present() -> None:
    """Фикстуры не должны молча усохнуть до пары строк."""
    assert len(NAMES) >= 600
    assert len(EXPECTED) >= 40


@pytest.mark.parametrize("row", EXPECTED, ids=lambda r: r.raw_name[:60])
def test_expected_table(row: Expected) -> None:
    """Каждое имя из выверенной таблицы разбирается ровно так, как записано."""
    release = parse_release_name(row.raw_name)

    assert release.title == row.title
    assert (release.original or "") == row.original
    assert str(release.year or "") == row.year
    assert (release.quality or "") == row.quality
    assert (release.codec or "") == row.codec
    assert (release.source or "") == row.source
    assert ("да" if release.hdr else "") == row.hdr
    assert "|".join(release.voices) == row.voices
    assert str(release.season or "") == row.season
    assert str(release.episode or "") == row.episode
    assert release.kind == row.kind


def test_whole_fixture_corpus_parses() -> None:
    """650 реальных имён: парсер не падает и почти всегда достаёт название.

    Цифры повторяют прогон по полному корпусу (``scripts/corpus_report.py``):
    название — практически всегда, год — там, где он в имени вообще есть.
    """
    releases = [parse_release_name(name) for name in NAMES]
    video = [r for r in releases if r.kind != "other"]

    named = [r for r in video if r.title and r.title != "?"]
    assert len(named) / len(video) >= 0.98

    with_year = [r for r in video if any(str(y) in r.raw_name for y in range(1900, 2031))]
    dated = [r for r in with_year if r.year is not None]
    assert len(dated) / len(with_year) >= 0.95


def test_junk_is_not_video() -> None:
    """Музыка, книги и игры не должны попадать в меню фильмов."""
    junk = [
        "(Black Metal) [CD] Perversus Stigmata - Void - 2009, FLAC (image+.cue), lossless",
        "Сергей Александровский - Моя мадам (2026) MP3",
        "Мейер Мэттью - Mad Max and Philosophy [2024, PDF, ENG]",
    ]
    assert all(parse_release_name(name).kind == "other" for name in junk)
    assert parse_release_name("Дюна / Dune (2021) BDRip 1080p").kind == "movie"


def test_parses_typical_russian_release() -> None:
    """Имя раздачи разбирается в название, оригинал, год, качество и кодек."""
    release = parse_release_name("Матрица / The Matrix (1999) BDRip 1080p x264 Дубляж")

    assert release.title == "Матрица"
    assert release.original == "The Matrix"
    assert release.year == 1999
    assert release.quality == "1080p"
    assert release.codec == "H.264"
    assert release.source == "BDRip"
    assert "Дубляж" in release.voices
    assert not release.is_hevc


def test_parses_kinozal_slash_format() -> None:
    """Формат кинозала «Рус / Original / год / озвучки / источник (качество)»."""
    release = parse_release_name(
        "Трансформеры: Месть падших / Transformers: Revenge of the Fallen / 2009 / "
        "ДБ, СТ / 4K, HEVC, HDR, Dolby Vision / Blu-Ray Remux (2160p)"
    )

    assert release.title == "Трансформеры: Месть падших"
    assert release.original == "Transformers: Revenge of the Fallen"
    assert release.year == 2009
    assert release.quality == "2160p"
    assert release.is_hevc
    assert release.hdr
    assert release.voices == ("Дубляж", "Субтитры")


def test_preposition_ot_is_not_a_release_group() -> None:
    """«Вдали от дома» — часть названия, а не хвост «от <релиз-группа>»."""
    release = parse_release_name(
        "Человек-паук: Вдали от дома / Spider-Man: Far from Home (IMAX Edition) / 2019 / "
        "ДБ / 4K, HEVC / WEB-DL (2160p)"
    )

    assert release.title == "Человек-паук: Вдали от дома"
    assert release.original == "Spider-Man: Far from Home"


def test_star_wars_episode_is_a_movie() -> None:
    """«Episode I» в оригинальном названии — не признак сериала."""
    release = parse_release_name(
        "Звёздные войны: Эпизод 1 / Star Wars Episode I - The Phantom Menace / 1999 / "
        "ДБ, ПМ / 4K, HEVC, SDR / WEB-DL (2160p)"
    )

    assert release.kind == "movie"
    assert release.season is None


def test_season_pack_is_not_first_episode() -> None:
    """«S2E1-8 of 8» — пак сезона: сезон есть, номера серии нет."""
    release = parse_release_name(
        "Фоллаут / Fallout / S2E1-8 of 8 (Джонатан Нолан) "
        "[2025, США, фантастика, HEVC, SDR, WEB-DL 2160p] Dub + MVO"
    )

    assert release.kind == "tv"
    assert release.season == 2
    assert release.episode is None


def test_hevc_is_flagged() -> None:
    """HEVC помечается — по умолчанию его никогда не берём (§3 ТЗ)."""
    release = parse_release_name("Дюна / Dune (2021) UHD BDRemux 2160p HEVC Дубляж")

    assert release.quality == "2160p"
    assert release.is_hevc


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Cyberpunk.Edgerunners.s01e05.1080p", (1, 5)),
        ("Stranger.Things.S03E07.720p.HEVC", (3, 7)),
        ("Киберпанк 2x5 WEB-DL", (2, 5)),
        ("Киберпанк 2х5 WEB-DL", (2, 5)),
        ("Киберпанк: Бегущие по краю, 2 сезон 5 серия", (2, 5)),
        ("Киберпанк, 5 серия 2 сезона", (2, 5)),
    ],
)
def test_parses_season_episode(text: str, expected: tuple[int, int]) -> None:
    """sNeM понимается во всех записях из §2.4 ТЗ."""
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


@pytest.mark.parametrize(
    ("title", "key", "part"),
    [
        ("Матрица", "матрица", None),
        ("Матрица: Перезагрузка", "матрица", None),
        ("Тачки 3", "тачки", 3),
        ("Форсаж - 8", "форсаж", 8),
        ("Терминатор 2: Судный день", "терминатор", 2),
        ("Терминатор II", "терминатор", 2),
        ("Форсаж 1-4", "форсаж", None),
    ],
)
def test_franchise_key_and_part_number(title: str, key: str, part: int | None) -> None:
    """Канон франшизы отрезает подзаголовок и номер; диапазон номером не считается."""
    assert franchise_key(title) == key
    assert part_number(title) == part


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


def test_key_of_a_picture_without_a_year_keeps_the_original_title() -> None:
    """Года в раздачах может не быть вовсе: тогда две разные картины с одинаковым русским
    названием разводит оригинал, иначе прогресс у них был бы общий (stage3 вопрос 2).
    """
    invasion = Picture(title="Вторжение", year=None, original="Invasion")
    intruder = Picture(title="Вторжение", year=None, original="The Intruder")

    assert invasion.key == "movie:вторжение-invasion:0"
    assert intruder.key == "movie:вторжение-the-intruder:0"
    # Год известен — ключ ровно тот, что в §4 ТЗ, без довесков.
    assert cluster([_release("Тачки", 2006, original="Cars")])[0].key == "movie:тачки:2006"


def test_matrix_two_is_reloaded() -> None:
    """§2.2 и чек-лист §7.5: «матрица 2» → «Перезагрузка», хотя двойки в названии нет.

    Оба фильма 2003 года — порядок задаёт номер части, подсмотренный в альтернативном
    переводе названия («Матрица 2: Перезагрузка» реально встречается в выдаче).
    """
    releases = [
        _release("Матрица", 1999, original="The Matrix", seeders=139),
        _release("Матрица: Перезагрузка", 2003, original="The Matrix Reloaded", seeders=48),
        _release("Матрица 2: Перезагрузка", 2003, original="The Matrix Reloaded", seeders=1),
        _release("Матрица: Революция", 2003, original="The Matrix Revolutions", seeders=54),
        _release("Матрица 3: Революция", 2003, original="The Matrix Revolutions", seeders=4),
        _release("Матрица: Воскрешение", 2021, original="The Matrix Resurrections", seeders=93),
    ]
    pictures = cluster(releases)

    assert [p.title for p in pick_franchise("матрица 2", pictures)] == ["Матрица: Перезагрузка"]
    assert [p.title for p in pick_franchise("матрица 3", pictures)] == ["Матрица: Революция"]
    assert [p.title for p in pick_franchise("матрица 1", pictures)] == ["Матрица"]
    assert len(pick_franchise("матрица", pictures)) == 4


def test_cars_franchise_is_cross_language() -> None:
    """«Тачки»/«Cars» склеиваются, если оба варианта есть в имени раздачи (§2.2)."""
    releases = [
        _release("Тачки", 2006, original="Cars", seeders=15),
        _release("Тачки 2", 2011, original="Cars 2", seeders=9),
        _release("Тачки 3", 2017, original="Cars 3", seeders=26),
        _release("Cars 3", 2017, seeders=4),  # чисто латинская раздача
    ]
    pictures = cluster(releases)

    assert [p.title for p in pick_franchise("тачки", pictures)] == ["Тачки", "Тачки 2", "Тачки 3"]
    assert [p.title for p in pick_franchise("cars 2", pictures)] == ["Тачки 2"]
    # латинский релиз попал в русский кластер, а не завёл свою картину
    assert len(pictures) == 3
    assert len(pictures[2].releases) == 2


def test_best_release_prefers_seeders_and_avoids_hevc() -> None:
    """Дефолт — самый обсиженный H.264; HEVC уступает даже с бо́льшими сидами (§2.1)."""
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


def _release(
    title: str,
    year: int | None,
    seeders: int = 0,
    codec: str = "H.264",
    original: str | None = None,
) -> Release:
    return Release(
        raw_name=f"{title} ({year})",
        title=title,
        original=original,
        year=year,
        quality="1080p",
        codec=codec,
        seeders=seeders,
    )
