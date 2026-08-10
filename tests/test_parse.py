"""Тесты парсера имён раздач и нумерации франшиз.

Фикстуры — реальные имена раздач, отобранные из корпуса в 21 540 уникальных имён:
``tests/fixtures/names.txt`` (650 имён, все шаблоны) и
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
    alt_query,
    cluster,
    franchise_key,
    franchise_name,
    in_digits,
    menu_order,
    other_words,
    outside_numbering,
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


def test_a_collection_label_does_not_take_the_original_with_it() -> None:
    """🔴 TC-282. Метка сборника режет своё русское имя, но не оригинал за слэшем.

    «Матрица: Трилогия / The Matrix: Trilogy» разбиралась в «Матрицу» с ПУСТЫМ
    оригиналом: рез по слову «трилогия» съедал всё после него вместе со слэшем и
    латинским названием. Без оригинала такая раздача не сшивается с картиной и не даёт
    имени для добора вторым языком.
    """
    pack = parse_release_name("Матрица: Трилогия / The Matrix: Trilogy (1999-2003) BDRip 1080p")

    assert pack.title == "Матрица"
    assert pack.original == "The Matrix: Trilogy"

    box = parse_release_name("Безумный Макс: Коллекция / Mad Max: Collection (1979-2024) BDRip")
    assert box.title == "Безумный Макс"
    assert box.original == "Mad Max"


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
    """HEVC помечается — по умолчанию его никогда не берём."""
    release = parse_release_name("Дюна / Dune (2021) UHD BDRemux 2160p HEVC Дубляж")

    assert release.quality == "2160p"
    assert release.is_hevc


@pytest.mark.parametrize(
    "name",
    [
        "Престиж / The Prestige (2006) BDRip 1080p Dubbed",
        "Драйв / Drive (2011) WEB-DL 1080p Movie Dubbing",
        "Брат 2 / Brat 2 (2000) BDRip 1080p Лицензия",
        "Форсаж / The Fast and the Furious (2001) WEB-DL 1080p iTunes",
    ],
)
def test_dub_markers_in_name(name: str) -> None:
    """Маркеры дубляжа в имени читаются так же, как в подписях дорожек."""
    release = parse_release_name(name)

    assert "Дубляж" in release.voices
    assert release.dubbed


@pytest.mark.parametrize(
    "name",
    [
        "The Prestige (2006) BDRip 1080p undubbed",
        "Drive (2011) WEB-DL 1080p no dub",
    ],
)
def test_no_dub_negation_is_not_dubbed(name: str) -> None:
    """«undubbed» и «no dub» - это отсутствие дубляжа, а не его маркер."""
    release = parse_release_name(name)

    assert "Дубляж" not in release.voices
    assert not release.dubbed


@pytest.mark.parametrize(
    "name",
    [
        "Dune (2021) 720p CAMRip [Malaysian Bahasa Melayu - Dub] Dual-Audio",
        "Dune (2021) 720p CAMRip [Thai - Dub] Dual-Audio x264",
    ],
)
def test_a_named_foreign_dub_does_not_promise_russian(name: str) -> None:
    """Встреченные в опорном корпусе языки перед ``Dub`` означают чужую дорожку."""
    assert not parse_release_name(name).dubbed


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
    """sNeM понимается во всех ходовых записях: и латиницей, и словами по-русски."""
    episode = parse_episode(text)

    assert episode is not None
    assert (episode.season, episode.episode) == expected


def test_plain_name_has_no_episode() -> None:
    """Фильм без sNeM эпизодом не считается."""
    assert parse_episode("Матрица / The Matrix (1999) BDRip 1080p") is None


def test_franchise_index_is_split_off_but_year_is_not() -> None:
    """«матрица 2» — номер во франшизе, «матрица 1999» — не номер, а год."""
    assert split_franchise_index("матрица 2") == ("матрица", 2)
    assert split_franchise_index("тачки") == ("тачки", None)
    assert split_franchise_index("матрица 1999") == ("матрица 1999", None)


@pytest.mark.parametrize(
    "query",
    [
        "Kill Bill: Vol. 1",
        "Kill Bill Vol 2",
        "Гарри Поттер и Дары Смерти: Часть 2",
        "Дюна: Часть 2",
    ],
)
def test_number_after_a_marker_word_stays_in_the_title(query: str) -> None:
    """Цифра после «Vol.»/«Part»/«Часть» — часть НАЗВАНИЯ, а не номер части франшизы.

    «Kill Bill: Vol. 1» уходил в индексер обрубком ``Kill Bill: Vol.``: живой круг по
    четырём индексерам отдавал на него 126 строк, из которых 58 были про ВТОРОЙ том, а
    оторванная единица тратилась как номер части — и отбор садился на латинского
    отщепенца «Kill Bill Volume 1» в две раздачи. Полное имя даёт 99 строк, но 67 из них
    про первый том против прежних 63.
    """
    assert split_franchise_index(query) == (query, None)


@pytest.mark.parametrize(
    ("query", "name", "index"),
    [("тачки 3", "тачки", 3), ("моана 2", "моана", 2), ("терминатор 2", "терминатор", 2)],
)
def test_plain_franchise_number_is_still_a_number(query: str, name: str, index: int) -> None:
    """Ограждение к тесту выше: обычный номер части резать как резали."""
    assert split_franchise_index(query) == (name, index)


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
    названием разводит оригинал, иначе прогресс у них был бы общий.
    """
    invasion = Picture(title="Вторжение", year=None, original="Invasion")
    intruder = Picture(title="Вторжение", year=None, original="The Intruder")

    assert invasion.key == "movie:вторжение-invasion:0"
    assert intruder.key == "movie:вторжение-the-intruder:0"
    # Год известен - ключ ровно канонический, без довесков.
    assert cluster([_release("Тачки", 2006, original="Cars")])[0].key == "movie:тачки:2006"


def test_matrix_two_is_reloaded() -> None:
    """«матрица 2» → «Перезагрузка», хотя двойки в названии нет.

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


def test_a_game_does_not_stand_in_for_a_missing_part() -> None:
    """Номера во франшизе нет - и подставлять на его место нечего (TC-320).

    Имена дословные, с живой выдачи. Игра «Матрица: Путь Нео» приезжает одной раздачей
    и по хронологии встаёт следом за «Революцией»: на живой выдаче она уезжала в меню
    единственной строкой запроса «матрица 5», тут - «матрица 4». Соседний номер отдавал
    «Воскрешение» - тоже не ту картину, которую человек назвал.
    """
    pictures = cluster(
        [
            parse_release_name(name)
            for name in (
                "Матрица / The Matrix (1999) WEB-DL 720p от SuperMin | D | Open Matte",
                "Матрица: Перезагрузка / The Matrix Reloaded (2003) BDRemux 1080p | Dub",
                "Матрица 2: Перезагрузка / The Matrix Reloaded (2003) WEB-DL 2160p | Dub",
                "Матрица: Революция / The Matrix Revolutions (2003) BDRemux 1080p | Dub",
                "Матрица 3: Революция / The Matrix Revolutions (2003) BDRip | Dub",
                "Матрица: Путь Нео / The Matrix: Path of Neo  (2005) PC | RePack-Yaroslav98",
                "Матрица: Воскрешение / The Matrix Resurrections (2021) WEB-DL 1080p | D",
            )
        ]
    )

    assert [p.title for p in pictures if p.kind == "other"] == ["Матрица: Путь Нео"]
    assert pick_franchise("матрица 4", pictures) == [], "игра местом в линейке не считается"
    assert pick_franchise("матрица 5", pictures) == [], "пятой части во франшизе нет"
    # Названные каталогом номера отвечают как прежде, первое место линейки свободно.
    assert [p.title for p in pick_franchise("матрица 1", pictures)] == ["Матрица"]
    assert [p.title for p in pick_franchise("матрица 2", pictures)] == ["Матрица: Перезагрузка"]
    assert [p.title for p in pick_franchise("матрица 3", pictures)] == ["Матрица: Революция"]
    # Без номера части франшиза показывается как была: не-видео из каталога не исчезает.
    whole = [p.title for p in pick_franchise("матрица", pictures)]
    assert "Матрица: Путь Нео" in whole and "Матрица: Воскрешение" in whole


def test_a_yearless_fan_edit_does_not_outweigh_the_living_part() -> None:
    """Явный номер без года не перевешивает живую настоящую часть (TC-335).

    Имена дословные, с сохранённой выдачи. «Матрица 4 / Matrix 4 - As It Should Be» -
    фанатская перемонтажка: номер в имени явный, а года каталог ей назвать не смог
    (диапазон «(2021/2022)»). Рядом лежит «Матрица: Воскрешение» - настоящая четвёртая
    часть, номером каталог её не подписал, - и прежний разбор отдавал запрос «матрица 4»
    сборке на двух раздачах: явный номер был сильнее всех прочих признаков.
    """
    pictures = cluster(
        [
            parse_release_name(name)
            for name in (
                "Матрица / The Matrix (1999) WEB-DL 720p от SuperMin | D | Open Matte",
                "Матрица: Перезагрузка / The Matrix Reloaded (2003) BDRemux 1080p | Dub",
                "Матрица 2: Перезагрузка / The Matrix Reloaded (2003) WEB-DL 2160p | Dub",
                "Матрица: Революция / The Matrix Revolutions (2003) BDRemux 1080p | Dub",
                "Матрица 3: Революция / The Matrix Revolutions (2003) BDRip | Dub",
                "Матрица: Воскрешение / The Matrix Resurrections (2021) WEB-DL 1080p | D",
                "Матрица: Воскрешение / The Matrix Resurrections (2021) BDRip-AV1 1080p "
                "от SuperMin | D",
                "Матрица: Воскрешение / The Matrix Resurrections (2021) BDRemux 1080p | Dub",
                "Матрица 4  / Matrix 4 - As It Should Be (2021/2022) HDRip-AVC | P | "
                "Фанатская версия",
                "Матрица 4 / Matrix 4 - As It Should Be (2021/2022) HDRip 1080p | P | "
                "Фанатская версия",
            )
        ]
    )

    found = [p.title for p in pick_franchise("матрица 4", pictures)]
    assert found == ["Матрица: Воскрешение"], "безгодовая сборка живой части не соперник"
    # Названные каталогом номера с годом отвечают как прежде - явный номер не ослаблен.
    assert [p.title for p in pick_franchise("матрица 2", pictures)] == ["Матрица: Перезагрузка"]
    assert [p.title for p in pick_franchise("матрица 3", pictures)] == ["Матрица: Революция"]
    # Живой части рядом нет - безгодовый носитель остаётся единственным, кого каталог
    # назвал этим номером, и честно показывается.
    lonely = [p for p in pictures if p.title != "Матрица: Воскрешение"]
    assert [p.title for p in pick_franchise("матрица 4", lonely)] == ["Матрица 4"]


def test_cars_franchise_is_cross_language() -> None:
    """«Тачки»/«Cars» склеиваются, если оба варианта есть в имени раздачи."""
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


#: Живая выдача по «гарри поттер дары смерти»: 139 раздач, и нужная часть среди них есть.
#: Ключ франшизы у каталога с союзом («гарри-поттер-и-дары-смерти»), а человек союз не
#: набирает - подстрокой такое не совпадает ни в одну сторону.
HARRY = (
    ("Гарри Поттер и Дары смерти: Часть 1", 2010, "Harry Potter and the Deathly Hallows Part 1"),
    ("Гарри Поттер и Дары Смерти: Часть II", 2011, "Harry Potter and the Deathly Hallows Part 2"),
    ("Гарри Поттер и Дары смерти в 3Д", 2010, None),
    ("Гарри Поттер. Полная коллекция", 2001, None),
)


def _harry() -> list[Picture]:
    return cluster(
        [_release(title, year, seeders=10, original=original) for title, year, original in HARRY]
    )


def test_part_number_selects_inside_the_franchise_not_the_anthology() -> None:
    """«гарри поттер дары смерти 2» → часть 2011 года, а не сборник франшизы.

    Номер - это выбор картины внутри франшизы, и франшиза берётся та, которую назвали.
    Раньше запрос без союза «и» не совпадал с ключом каталога, падал на грубое «ключ
    входит в запрос», ловил там всю «гарри поттер» и отсчитывал номер по ней - то есть
    приносил антологию.
    """
    pictures = _harry()

    assert [p.year for p in pick_franchise("гарри поттер дары смерти 2", pictures)] == [2011]
    assert [p.year for p in pick_franchise("гарри поттер дары смерти 1", pictures)] == [2010]


def test_word_order_in_the_query_is_not_the_users_problem() -> None:
    """«бульвар сансет» находит «Сансет бульвар»: те же слова, другой порядок."""
    pictures = cluster([_release("Сансет бульвар", 1950, seeders=4, original="Sunset Blvd")])

    assert [p.title for p in pick_franchise("бульвар сансет", pictures)] == ["Сансет бульвар"]


def test_other_words_speaks_up_only_when_the_words_were_other() -> None:
    """Честная строка печатается на перестановке и молчит на прямом попадании."""
    picture = cluster([_release("Сансет бульвар", 1950, original="Sunset Blvd")])[0]

    assert other_words("бульвар сансет", picture) == "Сансет бульвар"
    assert other_words("сансет бульвар", picture) == ""
    assert other_words("sunset blvd", picture) == ""
    assert other_words("бульвар сансет", None) == ""


def test_matching_by_words_stays_narrow() -> None:
    """Слова сверяются целиком, поэтому чужое кино по ним не приезжает.

    «дети мужчин» - это ``Children of Men``, и в каталоге под таким именем не лежит
    ничего. Рядом лежат «Мужчины, женщины и дети», и на нестрогом сравнении запрос уехал
    бы туда: слово «мужчин» похоже на «мужчины» ровно настолько, чтобы обмануть.
    """
    pictures = cluster(
        [
            _release("Мужчины, женщины и дети", 2014, seeders=19),
            _release("Наследственный признак", 1975, seeders=3),
        ]
    )

    assert pick_franchise("дети мужчин", pictures) == []
    assert pick_franchise("наследственное", pictures) == []


def test_a_title_remembered_in_another_form_is_still_found() -> None:
    """🔴 TC-247. «Робот мечты» - это «Мечты робота»: те же слова, другой порядок и форма.

    Порядок слов человек путает вместе с окончаниями, и буква в букву такие имена не
    сходятся ничем: подстроки нет ни в одну сторону, а «робот» не равно «робота». Восемь
    строк выдачи при этом лежат прямо в руках.

    Рядом нарочно положен однофамилец - «Робот» 2010 года. Его имя ВХОДИТ в запрос
    подстрокой, и без сверки по словам запрос уезжал именно к нему: молча, чужой картиной,
    под знакомым именем.
    """
    pictures = cluster(
        [
            _release("Мечты робота", 2023, seeders=40),
            _release("Робот", 2010, seeders=90),
        ]
    )

    assert [p.title for p in pick_franchise("робот мечты", pictures)] == ["Мечты робота"]


def test_another_form_on_the_same_place_is_a_namesake_and_not_the_picture() -> None:
    """🔴 Окончание прощается только ПЕРЕСТАВЛЕННОМУ слову, а стоящему на месте - нет.

    «Кольца власти» - сериал 2022 года, «Кольцо власти» - фильм 2007-го, и различает их
    ровно одна буква окончания, стоящая на своём месте. Прости её - и запрос молча уехал
    бы в чужое кино, лежащее в той же выдаче.
    """
    pictures = cluster([_release("Кольцо власти: Мировое супергосударство", 2007, seeders=1)])

    assert pick_franchise("кольца власти", pictures) == []


def test_a_name_written_by_ear_finds_the_picture() -> None:
    """🔴 TC-247. «Ксена» и «Зена» - одна и та же ``Xena``, перенесённая по-разному.

    Латинская ``x`` звучит в русском то как «кс», то как «з», и обе записи живые. Каталог
    подписал картину одной из них, спросили другой - и как строки они не сходятся ничем.

    Ручается за пару не догадка, а сама строка каталога: сверка идёт через оригинал,
    названный раздачей. Нет его - нет и пары.
    """
    pictures = cluster(
        [_release("Зена - королева воинов", 1995, seeders=30, original="Xena: Warrior Princess")]
    )

    assert [p.title for p in pick_franchise("ксена", pictures)] == ["Зена - королева воинов"]

    lonely = cluster([_release("Зена - королева воинов", 1995, seeders=30)])
    assert pick_franchise("ксена", lonely) == [], "оригинала в раздаче нет - ручаться нечем"


def test_words_of_both_names_at_once_find_the_picture() -> None:
    """🔴 TC-247. Имя франшизы взято с латинской обложки, подзаголовок - из русской озвучки.

    «Gundam 0080 Карманная война» - это «Мобильный воин ГАНДАМ 0080: Карманная война».
    Порознь имена запрос не содержат: «карманной войны» нет в оригинале, а ``Gundam`` нет
    в русском написании - «ГАНДАМ» это ``gandam``.

    Отдаётся именно эта картина, а не вся франшиза: соседний «Ответный удар Чара» лежит в
    той же серии, и показать его вместо спрошенного значило бы подменить кино.
    """
    pictures = cluster(
        [
            _release(
                "Мобильный воин ГАНДАМ 0080: Карманная война",
                1989,
                seeders=12,
                original="Mobile Suit Gundam 0080: War in the Pocket",
            ),
            _release(
                "Мобильный воин ГАНДАМ: Ответный удар Чара",
                1988,
                seeders=50,
                original="Mobile Suit Gundam: Char's Counterattack",
            ),
        ]
    )

    found = pick_franchise("gundam 0080 карманная война", pictures)

    assert [p.title for p in found] == ["Мобильный воин ГАНДАМ 0080: Карманная война"]


def test_a_subtitle_is_a_name_too() -> None:
    """🔴 Человек зовёт картину подзаголовком - «Кольца власти», а не «Властелин колец».

    Каталог подписывает сериал полным именем, ключ франшизы подзаголовок режет, и запрос
    падал в пустоту при 39 живых раздачах в той же выдаче: cast печатал «ничего не
    нашлось» там, где лежало 28 раздач до 91 сида.

    Отдаётся именно эта КАРТИНА, а не вся её франшиза: подставить «Властелина колец»
    вместо «Колец власти» значило бы показать другое кино.
    """
    pictures = cluster(
        [
            _release("Властелин колец: Кольца власти", 2022, seeders=91),
            _release("Властелин колец: Братство кольца", 2001, seeders=98),
            _release("Кольцо власти: Мировое супергосударство", 2007, seeders=1),
        ]
    )

    assert [p.title for p in pick_franchise("кольца власти", pictures)] == [
        "Властелин колец: Кольца власти"
    ]
    # Однофамилец мимо: подзаголовок сверяется целиком, «кольца» - это не «кольцо».
    assert [p.year for p in pick_franchise("кольцо власти", pictures)] == [2007]
    # Имя франшизы по-прежнему приводит франшизу целиком.
    assert len(pick_franchise("властелин колец", pictures)) == 2


def test_a_namesake_stub_does_not_take_the_subtitle_query_for_itself() -> None:
    """🔴 TC-246. «Космическая одиссея» - это и ключ огрызка, и подзаголовок классики.

    Подзаголовок читался только тогда, когда по ключу не нашлось НИЧЕГО, а по ключу
    находилась картина 1987 года с единственной мёртвой раздачей. «2001: Космическая
    одиссея» лежала в той же выдаче двумя десятками раздач, но её ключ - ``2001``, и до
    меню она не доезжала вовсе: человек читал «рой мёртв» при 80 строках в пуле.

    В меню теперь обе, и выбор между ними - работа меню, а не порядка проверок здесь.
    """
    pictures = cluster(
        [
            _release(
                "2001: Космическая одиссея", 1968, seeders=49, original="2001: A Space Odyssey"
            ),
            _release("Космическая одиссея", 1987, seeders=0),
        ]
    )

    found = pick_franchise("космическая одиссея", pictures)

    assert [p.year for p in found] == [1987, 1968], "огрызок остаётся, классика добавлена"


def test_a_subtitle_never_widens_a_query_that_named_a_part_number() -> None:
    """Ограждение к правке выше: номер части отсчитывается по линейке франшизы.

    Картина из чужой франшизы, добавленная в линейку, сдвинула бы нумерацию - и «2»
    означало бы не ту часть, которую человек назвал.
    """
    pictures = cluster(
        [
            _release("Матрица", 1999, seeders=90),
            _release("Матрица: Перезагрузка", 2003, seeders=80),
            _release("Перезагрузка", 2021, seeders=1),
        ]
    )

    assert [p.year for p in pick_franchise("матрица 2", pictures)] == [2003]


def test_a_subtitle_is_read_in_the_original_title_as_well() -> None:
    """Половина каталога подписана только латиницей - подзаголовок ищется и в оригинале."""
    pictures = cluster([_release("Rings of Power", 2022, original="LOTR: The Rings of Power")])

    assert [p.title for p in pick_franchise("the rings of power", pictures)] == ["Rings of Power"]


def test_a_single_word_never_goes_through_the_word_match() -> None:
    """Одного слова для перестановки мало: оно и так ищется подстрокой."""
    pictures = cluster([_release("Психо", 1960, original="Psycho")])

    assert [p.title for p in pick_franchise("психо", pictures)] == ["Психо"]
    assert pick_franchise("сансет", pictures) == []


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
    """Ключ состояния не зависит от регистра, ё и пунктуации."""
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


#: Дословные имена с живой выдачи Knaben - именно на них разбор и спотыкался.
MOANA_2 = (
    "Moana 2 (2024) 1080p BRRip 5.1 x264 -YTS",
    "Moana 2 2024 1080p BluRay DD  7 1 X265-Ralphy",
    "Moana Sing-Along 2017 MULTI 1080p DSNP WEB-DL DDP5 1 x264-AndreMor",
    "Моана 2 / Moana 2 (2024) WEB-DL 1080p от селезень | D, P | Пифагор",
)
#: А это настоящие сериалы: их сериальность обязана пережить ту же правку.
SERIES = (
    "Te Ao With Moana S07E18 720p WEB-DL AAC2 0 H 264-NTb",
    "Hawaii Five-0 2010 S03E03 Lana I Ka Moana 1080p AMZN WEB-DL DD 5 1 H 264-pl",
    "Киберпанк: Бегущие по краю (1 сезон: 1-10 серии из 10) 2022 WEB-DL 1080p x264",
    "The Last of Us S01-S02 1080p WEB-DL x265",
)


@pytest.mark.parametrize("name", MOANA_2)
def test_a_codec_token_never_turns_a_film_into_a_series(name: str) -> None:
    """«Moana 2 (2024)» определялась сериалом — и это ловилось на живых раздачах.

    Виноват был не номер в названии, а ``x264`` рядом с любой цифрой: «DDP5 1 x264»
    читалось как ``s1e264``. Кодек о сериях не говорит ничего — и в разборе
    сериальности его больше нет.
    """
    release = parse_release_name(name)
    assert release.kind == "movie", name
    assert (release.season, release.episode) == (None, None)


@pytest.mark.parametrize("name", SERIES)
def test_real_series_stay_series(name: str) -> None:
    """Точечная починка не должна ослепить разбор настоящих сериалов."""
    assert parse_release_name(name).kind == "tv", name


#: Одна серия, подписанная фансабом: так их и кладут SubsPlease, Erai-raws, ASW,
#: LoliHouse, shincaps. Имена дословные, с живой выдачи Nyaa.
FANSUB = (
    ("[Erai-raws] Gintama: 3-nen Z-gumi Ginpachi-sensei - 11 [1080p CR WEB-DL AVC AAC]", 11),
    ("[ASW] Gintama - 3-nen Z-gumi Ginpachi-sensei - 12 [1080p HEVC x265 10Bit][AAC]", 12),
    ("[SubsPlease] Gintama - 3-nen Z-gumi Ginpachi-sensei - 11 (720p) [719CF203].mkv", 11),
    ("[shincaps] Haikyuu!! - 03 (ANIMAX Asia 1920x1080 H264 MP2).ts", 3),
)


@pytest.mark.parametrize(("name", "episode"), FANSUB)
def test_a_fansub_number_is_an_episode_not_a_title(name: str, episode: int) -> None:
    """«Название - 11» у аниме — это ОДИННАДЦАТАЯ СЕРИЯ, а не другое кино.

    Номер оставался в названии, и кластер заводил под каждую серию свою «картину» в
    две-три раздачи. На живом каталоге «Gintama» (162 раздачи, 68 живых) это давало 27
    картин вместо 17, а дефолтом вставала «Гинтама: Любовные Благовония» — одна раздача,
    ноль живых.
    """
    release = parse_release_name(name)

    assert release.episode == episode, name
    assert release.kind == "tv", name
    assert not release.title.rstrip(" .").endswith(str(episode)), release.title


def test_a_fansub_series_is_one_picture_not_one_per_episode() -> None:
    """Все серии тайтла — одна картина; на этом и садился дефолт (TC-151)."""
    names = [name for name, _ in FANSUB[:3]]

    pictures = cluster([parse_release_name(name) for name in names])

    assert len(pictures) == 1
    assert len(pictures[0].releases) == 3


#: Номер части у кино выглядит так же - и обязан остаться номером части.
NOT_FANSUB = (
    "[Rutor] Форсаж - 8 (2017) BDRip 1080p",
    "Форсаж - 8 / The Fate of the Furious (2017) BDRip 1080p",
    "[Kinozal] Убить Билла: Фильм 2 (2004) BDRip 720p",
)


@pytest.mark.parametrize("name", NOT_FANSUB)
def test_a_movie_part_number_is_not_an_episode(name: str) -> None:
    """Ограждение: год в имени запрещает читать хвостовую цифру как номер серии."""
    release = parse_release_name(name)

    assert release.kind == "movie", name
    assert release.episode is None, name


def test_moana_franchise_is_shown_in_both_languages() -> None:
    """«Moana» и «Моана 2» — одна франшиза, как бы её ни спросили."""
    releases = [
        _release("Moana", 2016, seeders=22),
        _release("Моана 2", 2024, seeders=140, original="Moana 2"),
    ]
    pictures = cluster(releases)
    for query in ("moana", "моана"):
        found = pick_franchise(query, pictures)
        assert [p.year for p in found] == [2016, 2024], query


def test_a_franchise_of_twins_costs_one_pass_not_a_square(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сборка франшизы из двух языков линейна по числу картин, а не квадратична.

    Каждая картина с оригинальным названием даёт свой ключ-близнец, и пересчёт «кого уже
    взяли» по всему списку на каждого из них стоил прохода на близнеца. Живая выдача
    Knaben - сотни релизов, и платить за это квадратом не за что.
    """
    import builtins

    from torrcast.parse import _both_languages

    size = 200
    groups = {"дюна": [_picture("Дюна", 2021)]}
    aliases = {}
    for number in range(size):  # каждая часть подписана своей латиницей: свой ключ-близнец
        twin = f"dune-{number}"
        groups[twin] = [_picture(f"Дюна {number}", 1900 + number, original=f"Dune {number}")]
        aliases[twin] = "дюна"

    counted = 0
    real_id = builtins.id

    def counting_id(obj: object) -> int:
        nonlocal counted
        counted += 1
        return real_id(obj)

    monkeypatch.setattr(builtins, "id", counting_id)
    found = _both_languages(groups, aliases, "дюна")
    monkeypatch.undo()

    assert len(found) == size + 1, "все близнецы обязаны попасть во франшизу"
    assert [p.year for p in found][:2] == [1900, 1901], "порядок франшизы прежний - по годам"
    assert counted < 6 * size, f"проход по списку на каждого близнеца: {counted} на {size} картин"


def _picture(title: str, year: int, original: str | None = None) -> Picture:
    return Picture(title=title, year=year, original=original, releases=[])


#: Имена, у которых старьё написано на лбу: кодек MPEG-4, контейнер или SD-источник.
DATED_NAMES = (
    "Матрица / The Matrix (1999) DVDRip XviD AC3 Дубляж",
    "Терминатор 2 / Terminator 2 (1991) DivX 700MB",
    "Moana.2.2024.WEB-DLRip.ELEKTRI4KA.avi",
    "Кино / Movie (2003) SATRip",
    "Кино / Movie (2003) VHSRip -> DVD",
    "Кино / Movie (2003) TVRip",
    "Кино / Movie (2003) DVDScr",
)
#: А это не старьё, хотя рядом стоят похожие буквы.
FRESH_NAMES = (
    "Моана 2 / Moana 2 [2024, WEB-DL 1080p] Dub",
    "Матрица / The Matrix [1999, BDRip-AVC] MVO",
    "Интерстеллар / Interstellar [2014, MPEG-4 AVC, BDRemux 1080p]",
    "Аватар / Avatar [2009, США, HDTVRip 720p][AVC]",
)


@pytest.mark.parametrize("name", DATED_NAMES)
def test_obvious_old_junk_is_marked_dated(name: str) -> None:
    """Явные признаки старья читаются из имени и до всякого ffprobe."""
    assert parse_release_name(name).dated, name


@pytest.mark.parametrize("name", FRESH_NAMES)
def test_a_fresh_release_is_not_marked_dated(name: str) -> None:
    """Свежая раздача старьём не объявляется — иначе меню перевернётся с ног на голову."""
    assert not parse_release_name(name).dated, name


#: Раздача сама называет себя приложением к картине - все имена из сохранённых выдач.
EXTRAS_NAMES = (
    "Тачки 2 / Cars 2 [2011, мультфильм, комедия, приключения, HDRip] фильм о фильме",
    "Тачки 2 / Cars 2 (2011) HDRip 720р-Трейлер",
    "Оно / It [2017, Ужасы | Триллер, BDRip 720p] дополнительные материалы",
    "Тачки 3 [Бонус-Диск] / Cars 3 [Bonus Disc] [2017, Мультфильм, BDRip 720]",
    "Интерстеллар / Interstellar (2014) DCPRip-Тизер",
    "РобоКоп / RoboCop (2014) BDRip 720p от Azazel | Дополнительные материалы | L1",
)
#: А это картины, хотя те же слова в именах есть: слово стоит в СОБСТВЕННОМ названии
#: картины либо после плюса - «картина И приложение к ней».
NOT_EXTRAS_NAMES = (
    "Твин Пикс: Вырезанные сцены / Twin Peaks: The Missing Pieces (2014) BDRip 720p",
    "Интервью / The Interview (2014) HDRip 700MB",
    "Форсаж. Евротур / Bonus Trip (2024) WEB-DL 1080p",
    "Тачки + Бонус / Cars (2006) BDRip 1080p от HD Club",
    "Пацаны / The Boys [S01-05 + Extra] (2019-2026) WEB-DL-AVC | КПК",
    "Чернобыль. Зона отчуждения [S01-02 + Финал + Фильм о фильме] (2014-2019) WEB-DL-AVC",
    "Атака титанов / Shingeki no Kyojin [01-80 + 3 extra] (2009-2016)",
    "Whiplash / Одержимость (2014) + Extras (1080p BluRay x264 AAC)",
    "Матрица / The Matrix (1999) BDRip 1080p",
    # Документальная картина о съёмках, у которой это и есть собственное имя: в каталоге
    # она стоит отдельной картиной, и спросивший её по имени обязан её получить.
    "Бесконечность - не предел / To Infinity and Beyond. The Making of Toy Story (1996) DVDRip",
)


@pytest.mark.parametrize("name", EXTRAS_NAMES)
def test_a_release_that_calls_itself_a_bonus_is_marked_extras(name: str) -> None:
    """🔴 TC-290. Приложение к картине читается из имени и до всякого веса."""
    assert parse_release_name(name).extras, name


@pytest.mark.parametrize("name", NOT_EXTRAS_NAMES)
def test_the_picture_itself_is_never_marked_extras(name: str) -> None:
    """Ограждение: слово в имени самой картины и форма «картина + приложение» - не метка.

    Ошибиться тут дороже, чем пропустить: метка уводит раздачу под картину в порядке
    отбора, и повесить её на саму картину значило бы наказать ту, за которой и пришли.
    """
    assert not parse_release_name(name).extras, name


def test_mpeg4_avc_is_h264_and_not_mpeg4() -> None:
    """⚠️ «MPEG-4 AVC» на rutracker означает H.264: порядок проверок в разборе кодека
    держит именно этот случай, иначе годный BDRemux уехал бы в старьё.
    """
    assert parse_release_name("Кино [2014, MPEG-4 AVC, BDRemux 1080p]").codec == "H.264"
    assert parse_release_name("Кино [2003, DVDRip, MPEG-4]").codec == "MPEG-4"


def test_xvid_is_never_a_prime_release() -> None:
    """XviD/DivX — тот же MPEG-4: ресивер его не играет, и первым сортом он не бывает.

    Раньше кодек не читался вовсе, и «XviD HDRip» проходил в кандидаты по источнику:
    HDRip есть в списке HD-мастеров, а кодек молчал.
    """
    xvid = parse_release_name("Кино / Movie [2003, HDRip] XviD MVO")
    assert xvid.codec == "MPEG-4" and not xvid.prime


def test_the_menu_numbers_the_franchise_by_part_not_by_year() -> None:
    """Номер пункта = номер части: спин-офф 2008 года не встаёт между первой и второй.

    Живая франшиза «Тачки»: у первой части номера нет вовсе, у спин-оффа «Мультачки» -
    тоже, и по хронологии он оказывался вторым пунктом, оттесняя «Тачки 2» на третий.
    Человек читает номер пункта как номер части и им же отвечает.
    """
    pictures = cluster(
        [
            _release("Тачки", 2006, original="Cars", seeders=15),
            _release("Тачки: Мультачки. Байки Мэтра", 2008, seeders=3),
            _release("Тачки 2", 2011, original="Cars 2", seeders=9),
            _release("Тачки 3", 2017, original="Cars 3", seeders=26),
        ]
    )
    whole = pick_franchise("тачки", pictures)

    assert [p.title for p in menu_order(whole)] == [
        "Тачки",
        "Тачки 2",
        "Тачки 3",
        "Тачки: Мультачки. Байки Мэтра",
    ]
    # Уехавшему вниз пункту меню подписывает причину, остальным - нечего.
    assert outside_numbering(whole) == {"movie:тачки-мультачки-байки-мэтра:2008"}


def test_a_franchise_without_part_numbers_keeps_its_chronology() -> None:
    """«Матрица» номеров частей не называет - выдумывать линейку и подписи не из чего."""
    pictures = cluster(
        [
            _release("Матрица", 1999, seeders=90),
            _release("Матрица: Перезагрузка", 2003, seeders=50),
            _release("Матрица: Революция", 2003, seeders=40),
            _release("Матрица: Воскрешение", 2021, seeders=20),
        ]
    )
    whole = pick_franchise("матрица", pictures)

    assert [p.title for p in menu_order(whole)] == [p.title for p in whole]
    assert outside_numbering(whole) == set()


def test_plain_franchise_name_reaches_its_films_without_non_video() -> None:
    """Голое имя франшизы раскрывает фильмы с продолжением имени, но не игру."""
    releases = [
        Release(
            raw_name="Гарри Поттер: Чемпионат мира по квиддичу (2003) PC RePack",
            title="Гарри Поттер: Чемпионат мира по квиддичу",
            year=2003,
            kind="other",
        ),
        _release("Гарри Поттер: История магии", 2017),
        _release("Гарри Поттер и философский камень", 2001, seeders=20),
        _release("Гарри Поттер и Тайная комната", 2002, seeders=18),
    ]

    menu = menu_order(pick_franchise("гарри поттер", cluster(releases)))

    assert [(p.title, p.kind) for p in menu] == [
        ("Гарри Поттер и философский камень", "movie"),
        ("Гарри Поттер и Тайная комната", "movie"),
        ("Гарри Поттер: История магии", "movie"),
    ]


def test_an_explicit_first_part_leaves_no_free_slot_for_a_nameless_one() -> None:
    """Номер ``1`` назван вслух - значит безномерная картина первой частью не считается."""
    pictures = cluster(
        [
            _release("Дюна: Часть первая", 2021, seeders=30),
            _release("Дюна 1", 1984, seeders=10),
            _release("Дюна 2", 2024, seeders=40),
        ]
    )
    whole = pick_franchise("дюна", pictures)
    ordered = menu_order(whole)

    assert [p.year for p in ordered] == [1984, 2024, 2021]
    assert outside_numbering(whole) == {ordered[-1].key}


def test_a_collection_release_does_not_become_a_menu_line() -> None:
    """🔴 TC-327. Раздача-сборник в меню не пункт: за ней стоит пачка картин, а не картина.

    Имя сборника обрезается по слову «Трилогия»/«Коллекция» до голого имени франшизы, а
    диапазон лет в скобке схлопывается в первый год - и гейт года такую кучку не разводит.
    В живой выдаче по «хоббит» из-за этого стояло «Хоббит (2001)» одной раздачей на 165 ГБ:
    две трилогии сразу, картины с таким именем и годом не существует вовсе.
    """
    names = [
        "Хоббит: Нежданное путешествие / The Hobbit: An Unexpected Journey (2012) BDRip 1080p",
        "Хоббит: Пустошь Смауга / The Hobbit: The Desolation of Smaug (2013) BDRip 1080p",
        "Хоббит: Битва пяти воинств / The Hobbit: The Battle of the Five Armies (2014) BDRip",
        "Хоббит: Трилогия / The Hobbit: Trilogy (2012-2014) BDRip 1080p",
        "Хоббит / Властелин колец: Коллекция / The Hobbit / The Lord of the rings: Collection"
        " (2001-2014) BDRip 1080p",
    ]
    pictures = cluster([parse_release_name(name) for name in names])

    assert [(p.title, p.year) for p in pictures if p.collection] == [
        ("Хоббит", 2001),
        ("Хоббит", 2012),
    ], "каталог сборники знает - в меню их не пускает отдельная ступень"
    assert [(p.title, p.year) for p in menu_order(pick_franchise("хоббит", pictures))] == [
        ("Хоббит: Нежданное путешествие", 2012),
        ("Хоббит: Пустошь Смауга", 2013),
        ("Хоббит: Битва пяти воинств", 2014),
    ]


def test_a_bilingual_list_of_films_is_a_collection() -> None:
    """Несколько русских и латинских имён через слэш перечисляют разные картины."""
    pack = parse_release_name(
        "Хоббит/Нежданное путешествие/Пустошь Смауга/The Hobbit/"
        "An Unexpected Journey/The Desolation of Smaug "
        "[2012-3, США, Новая Зеландия, фэнтези, 3 DVD5] Dub"
    )
    one_picture = parse_release_name(
        "Унесённые призраками / Sen to Chihiro no Kamikakushi / Spirited Away (2001) BDRip 1080p"
    )
    many_names_one_picture = parse_release_name(
        "Клинок, рассекающий демонов: Деревня кузнецов / "
        "Kimetsu no Yaiba: Katanakaji no Sato Hen / Demon Slayer: Swordsmith Village Arc / "
        "Blade of Demon Destruction / Истребитель демонов [TV] [S3] [2023] BDRip"
    )

    assert pack.collection is True
    assert one_picture.collection is False
    assert many_names_one_picture.collection is False


def test_a_movie_trilogy_label_marks_a_collection() -> None:
    """Слово «Кинотрилогия» прямо называет пачку фильмов и не становится пунктом меню."""
    releases = [
        parse_release_name(
            "Властелин колец: Кинотрилогия / The Lord of the Rings: "
            "The Motion Picture Trilogy (2001-2003) BDRip 1080p"
        ),
        parse_release_name(
            "Властелин колец: Братство кольца / The Lord of the Rings: "
            "The Fellowship of the Ring (2001) BDRip 1080p"
        ),
    ]

    pictures = cluster(releases)
    assert [p.title for p in menu_order(pick_franchise("властелин колец", pictures))] == [
        "Властелин колец: Братство кольца"
    ]


def test_a_season_pack_stays_a_picture_and_a_lone_collection_stays_in_the_menu() -> None:
    """🔴 TC-327, обе ограды разом: сборник не мусор, и сезон-пак не сборник.

    Сезон-пак «Клиника [S01-09]» - обычная раздача сериала, лежит в одной кучке с
    остальными и остаётся картиной. А если, кроме сборников, не нашлось ничего, они и
    показываются: выбирать всё равно не из чего, а пустое меню значит «ничего не нашлось»
    при живой выдаче в руках.
    """
    series = cluster(
        [
            parse_release_name("Клиника / Scrubs [S01-09] (2001-2010) WEB-DL 1080p"),
            parse_release_name("Клиника / Scrubs [S07] (2008) WEB-DL 1080p"),
        ]
    )

    assert [(p.title, p.kind, p.collection) for p in series] == [("Клиника", "tv", False)]
    assert len(menu_order(pick_franchise("клиника", series))) == 1

    lonely = cluster(
        [parse_release_name("Хоббит: Трилогия / The Hobbit: Trilogy (2012-2014) BDRip 1080p")]
    )

    assert [(p.title, p.year) for p in menu_order(pick_franchise("хоббит", lonely))] == [
        ("Хоббит", 2012)
    ]


def test_latin_and_russian_names_of_one_picture_are_one_picture() -> None:
    """«Врата Штейна» (русская озвучка, 2011) и ``Steins;Gate`` (года в именах нет) - одна
    картина: имена сведены оригиналом из самой выдачи, а безымянный год спорить не может.

    Пока их было две, запрос латиницей русскую озвучку не видел в принципе: пул латиницей
    богатый, второго захода не будет, а склеивать было нечем.
    """
    releases = [
        _release("Врата Штейна", 2011, original="Steins;Gate", seeders=86),
        _release("Steins;Gate", None, seeders=179),
        _release("Steins;Gate", None, seeders=140),
    ]

    pictures = cluster(releases)

    assert len(pictures) == 1
    assert (pictures[0].title, pictures[0].year) == ("Врата Штейна", 2011)
    assert len(pictures[0].releases) == 3
    assert pictures[0].also == "Steins;Gate"
    assert pick_franchise("steins gate", pictures) == pictures


def test_one_year_apart_is_the_same_picture() -> None:
    """Год производства и год проката каталог путает постоянно: 1966 и 1967 у «Кавказской
    пленницы» - одна и та же картина, а не две хилые.
    """
    releases = [
        _release("Кавказская пленница, или Новые приключения Шурика", 1966, seeders=14),
        _release("Кавказская пленница, или Новые приключения Шурика", 1967, seeders=4),
    ]

    pictures = cluster(releases)

    assert len(pictures) == 1
    assert len(pictures[0].releases) == 2
    assert pictures[0].also == ""  # имя одно, говорить не о чем


def test_a_glued_film_wears_the_year_of_the_majority_and_a_series_the_earliest() -> None:
    """🔴 TC-328 и TC-201 одним тестом: у кино год по большинству, у сериала - самый ранний.

    «Титаник» стоял в меню как «Титаник (1996)» из-за трёх раздач из 68 с этим годом:
    ранний год у кино - это описка каталога (год производства против года проката), а не
    начало чего-либо. Год человек читает глазами, чтобы отличить оригинал от ремейка, и
    врущий год подрывает ровно этот приём.

    У сериала правило обратное и остаётся прежним: сезоны датированы каждый своим годом,
    самый обсиженный - не первый, а справку открывает год НАЧАЛА показа.
    """
    titanic = cluster(
        [_release("Титаник", 1996, seeders=3)] * 3 + [_release("Титаник", 1997, seeders=9)] * 65
    )

    assert [(p.title, p.year, len(p.releases)) for p in titanic] == [("Титаник", 1997, 68)]

    def season(year: int, number: int) -> Release:
        return Release(
            raw_name=f"Доктор Кто / Doctor Who [S{number:02d}] ({year}) WEB-DL 1080p",
            title="Доктор Кто",
            original="Doctor Who",
            year=year,
            kind="tv",
            season=number,
        )

    series = cluster([season(2005, 1), season(2006, 2), season(2006, 3), season(2006, 4)])

    assert [(p.title, p.year, p.kind) for p in series] == [("Доктор Кто", 2005, "tv")]


def test_remake_is_not_glued_to_the_original() -> None:
    """Ремейк носит имя оригинала, и склеить их значило бы молча подсунуть чужой фильм."""
    releases = [
        _release("Психо", 1960, original="Psycho", seeders=40),
        _release("Психо", 1998, original="Psycho", seeders=5),
    ]

    pictures = cluster(releases)

    assert [(p.title, p.year) for p in pictures] == [("Психо", 1960), ("Психо", 1998)]


def test_picture_without_a_year_stays_alone_between_two_namesakes() -> None:
    """Под одним именем две картины разных лет - безымянная не достаётся ни одной из них:
    выбирать наугад между оригиналом и ремейком нельзя.
    """
    releases = [
        _release("Психо", 1960, original="Psycho", seeders=40),
        _release("Психо", 1998, original="Psycho", seeders=5),
        _release("Psycho", None, seeders=12),
    ]

    pictures = cluster(releases)

    assert [(p.title, p.year, len(p.releases)) for p in pictures] == [
        ("Психо", 1960, 1),
        ("Психо", 1998, 1),
        ("Psycho", None, 1),
    ]


def test_a_channel_in_front_is_not_the_name_of_the_picture() -> None:
    """🔴 TC-297. «BBC. Живая планета» - это «Живая планета», а не картина канала BBC."""
    assert franchise_key("BBC. Живая планета") == "живая-планета"
    assert franchise_name("BBC. The Living Planet") == "The Living Planet"
    assert franchise_name("Discovery. Смертельный улов") == "Смертельный улов"
    assert franchise_name("BBC: Планета Земля 3") == "Планета Земля"
    assert franchise_name("BBC Proms") == "BBC Proms", "без знака это первое слово названия"


def test_the_second_query_takes_the_title_and_not_the_channel() -> None:
    """Добор идёт оригинальным названием, а не маркой вещателя.

    По строке ``BBC`` приезжает какое угодно кино, кроме спрошенного, и человек читал
    честное «по BBC приехала другая картина» при живой раздаче в той же выдаче.
    """
    releases = [
        parse_release_name("BBC. Живая планета / BBC. The Living Planet  (1984) DVDRip | P1"),
        parse_release_name(
            "BBC. Океаны: Наша Голубая Планета / BBC. Oceans: Our Blue Planet "
            "[2018, документальный, UHD BDRemux 2160p] Original Eng + Sub (Rus, Eng)"
        ),
    ]

    found = pick_franchise("живая планета", cluster(releases))

    assert [p.title for p in found] == ["BBC. Живая планета"]
    assert alt_query("живая планета", releases) == "The Living Planet"


def test_two_original_names_are_still_one_picture() -> None:
    """🔴 TC-308. Международное имя и родное - одна картина, а не две.

    «Унесённые призраками» приезжают строками с ТРЕМЯ именами разом; в паспорт попадает
    японское, а полсотни латинских раздач подписаны английским. Пока имена сверялись как
    строки, в меню стояли две картины 2001 года: у одной русский звук, у другой английский,
    и от того, каким именем спросили, зависело, какую человек увидит.
    """
    pictures = cluster(
        [
            parse_release_name(
                "Унесённые призраками / Sen to Chihiro no Kamikakushi / Spirited Away "
                "(2001) BDRip 1080p | D"
            ),
            parse_release_name("Spirited.Away.2001.1080p.BluRay.x264-GRP"),
            parse_release_name("Spirited.Away.2001.720p.BluRay.x264-CTU"),
        ]
    )

    assert len(pictures) == 1
    assert (pictures[0].title, pictures[0].original) == (
        "Унесённые призраками",
        "Sen to Chihiro no Kamikakushi",
    )
    assert pictures[0].also == "Spirited Away", "второе имя названо вслух, а не проглочено"
    assert len(pictures[0].releases) == 3


def test_a_third_name_does_not_move_a_picture_that_names_itself() -> None:
    """Третья подпись сводит только с ОДИНОКИМ именем - каталог его не спарил ни с чем.

    Пара имён в заголовке уже сказала, как картина зовётся, и третья подпись чужого
    заголовка её не отменяет. Год тут одинаковый нарочно: держит картины врозь именно это
    правило, а не гейт года.
    """
    pictures = cluster(
        [
            parse_release_name("Ночная смена / Night Shift / Призраки (2019) BDRip 1080p"),
            parse_release_name("Призраки / Ghosts (2019) WEB-DL 1080p"),
        ]
    )

    assert [(p.title, p.original) for p in pictures] == [
        ("Ночная смена", "Night Shift"),
        ("Призраки", "Ghosts"),
    ]


def test_glue_keeps_parts_of_a_franchise_apart() -> None:
    """Склейка сверяет ПОЛНОЕ имя, а не франшизу: «Тачки 2» и «Тачки 3» - разные картины."""
    releases = [
        _release("Тачки 2", 2011, original="Cars 2", seeders=126),
        _release("Cars 3", None, seeders=30),
        _release("Тачки 3", 2017, original="Cars 3", seeders=121),
    ]

    pictures = cluster(releases)

    assert [(p.title, p.year, len(p.releases)) for p in pictures] == [
        ("Тачки 2", 2011, 1),
        ("Тачки 3", 2017, 2),
    ]


def test_glue_keeps_a_named_parody_apart_from_the_original() -> None:
    """Явно названная пародия - другая картина, даже если оригинальное имя общее."""
    pictures = cluster(
        [
            parse_release_name(
                "Властелин колец: Возвращение короля / "
                "The Lord of the Rings: The Return of the King (2003) BDRip 1080p Dub"
            ),
            parse_release_name(
                "Властелин Колец: Возвращение Бомжа / "
                "The Lord of the Rings: The Return of the King "
                "[2004, фэнтези, приключения, пародия, DVDRip]"
            ),
        ]
    )

    assert [(p.title, p.year) for p in pictures] == [
        ("Властелин колец: Возвращение короля", 2003),
        ("Властелин Колец: Возвращение Бомжа", 2004),
    ]


def test_a_goblin_voice_is_not_mistaken_for_a_parody() -> None:
    """Имя дорожки не меняет картину: обычная альтернативная озвучка остаётся в пуле."""
    pictures = cluster(
        [
            parse_release_name("Матрица / The Matrix (1999) BDRip 1080p Dub"),
            parse_release_name("Матрица / The Matrix (1999) BDRip AVO (Гоблин)"),
        ]
    )

    assert len(pictures) == 1
    assert len(pictures[0].releases) == 2


def test_a_parody_studio_label_before_the_original_prevents_glue() -> None:
    """Студийная подпись в русском имени отделяет пародийную трилогию от сборника."""
    pictures = cluster(
        [
            parse_release_name(
                "Властелин колец: Кинотрилогия / "
                "The Lord of the Rings: The Motion Picture Trilogy (2001-2003) BDRip"
            ),
            parse_release_name(
                "Властелин Колец: Братва и кольцо | Две сорванные башни | "
                "Возвращение Бомжа (Гоблин) / The Lord of the Rings: "
                "The Motion Picture Trilogy [2002, 2003, 2004, комедия, BDRip]"
            ),
        ]
    )

    assert [p.title for p in pictures] == [
        "Властелин колец",
        "Властелин Колец: Братва и кольцо",
    ]


def test_number_in_words_and_in_digits_is_one_picture() -> None:
    """«12 обезьян» и «Двенадцать обезьян» - один фильм 1995 года, а не две картины.

    Замер на живой выдаче: 29 раздач лежат под именем цифрой (до 105 сидов), одна -
    прописью. Пока имена сверялись как строки, запрос прописью получал ровно её.
    """
    releases = [
        _release("12 обезьян", 1995, seeders=105),
        _release("12 обезьян", 1995, seeders=64),
        _release("Двенадцать обезьян", 1995, seeders=4),
    ]

    pictures = cluster(releases)

    assert [(p.title, p.year, len(p.releases)) for p in pictures] == [("12 обезьян", 1995, 3)]


def test_query_in_words_finds_the_picture_named_in_digits() -> None:
    """Спросили прописью, каталог подписал цифрой - картина всё равно находится."""
    releases = [
        _release("12 обезьян", 1995, seeders=105),
        _release("Двенадцать обезьян", 1995, seeders=4),
    ]

    found = pick_franchise("Двенадцать обезьян", cluster(releases))

    assert [(p.title, len(p.releases)) for p in found] == [("12 обезьян", 2)]


def test_number_bridge_does_not_glue_a_remake() -> None:
    """Гейт года сильнее числительного: одноимённый ремейк остаётся отдельной картиной."""
    releases = [
        _release("12 разгневанных мужчин", 1957, seeders=40),
        _release("Двенадцать разгневанных мужчин", 1997, seeders=7),
    ]

    pictures = cluster(releases)

    assert [(p.title, p.year) for p in pictures] == [
        ("12 разгневанных мужчин", 1957),
        ("Двенадцать разгневанных мужчин", 1997),
    ]


def test_in_digits_touches_only_whole_words() -> None:
    """Замена пословная: «двенадцать» - число, «двенадцатая» и «семья» - нет."""
    assert in_digits("двенадцать-обезьян") == "12-обезьян"
    assert in_digits("twelve-monkeys") == "12-monkeys"
    assert in_digits("двенадцатая-ночь") == "двенадцатая-ночь"
    assert in_digits("семья-сопрано") == "семья-сопрано"


def test_series_and_movie_of_the_same_name_are_not_glued() -> None:
    """У аниме сериал и полнометражка подписаны одинаково, а картины это разные."""
    series = Release(
        raw_name="Steins;Gate (2011)",
        title="Steins;Gate",
        year=None,
        quality="1080p",
        codec="H.264",
        seeders=179,
        seasons=(1,),
        kind="tv",
    )
    movie = _release("Врата Штейна", 2011, original="Steins;Gate", seeders=19)

    pictures = cluster([series, movie])

    assert {p.kind for p in pictures} == {"tv", "movie"}
    assert len(pictures) == 2


def test_short_name_finds_the_classic_not_the_remake() -> None:
    """«кавказская пленница» - это фильм Гайдая, а ремейк 2014 года стоит рядом, а не вместо.

    Подзаголовок советское кино вводит словом «или», и без этого разреза короткий запрос
    точно попадал в ключ ремейка: 22 раздачи классики лежали в той же выдаче незамеченными.
    """
    releases = [
        _release("Кавказская пленница, или Новые приключения Шурика", 1967, seeders=14),
        _release("Кавказская пленница!", 2014, seeders=1),
    ]

    found = pick_franchise("кавказская пленница", cluster(releases))

    assert [(p.title, p.year) for p in found] == [
        ("Кавказская пленница, или Новые приключения Шурика", 1967),
        ("Кавказская пленница!", 2014),
    ]


def test_latin_full_name_beats_soundtrack_scrap() -> None:
    """TC-153: латинское имя картины сводится с русским на привязке, а не вторым кругом.

    Живая выдача по «Kill Bill: Vol. 1» - 96 раздач. Картина «Убить Билла» (2003, 58
    раздач) подписана строками ``Убить Билла / Kill Bill: Vol. 1``, то есть каталог сам
    ручается за пару, но в указатель псевдонимов попадал только КОРЕНЬ ``kill-bill``:
    двоеточие с номером части режет :func:`franchise_key`. Точное же ``kill-bill-vol-1``
    доставалось сборнику саундтреков «VA - Убить Билла - 1» - одной раздаче без единого
    живого сида, - потому что у него номер части стоит без двоеточия и не режется.
    Запрос латиницей попадал точным совпадением в этот огрызок: 96 раздач схлопывались
    до одной мёртвой, и картину спасал только второй круг по русскому имени.
    """
    releases = [
        *(
            _release("Убить Билла", 2003, original="Kill Bill: Vol. 1", seeders=n)
            for n in (110, 82, 41, 13)
        ),
        *(
            _release("Убить Билла 2", 2004, original="Kill Bill: Vol. 2", seeders=n)
            for n in (130, 12)
        ),
        _release("VA - Убить Билла - 1", 2007, original="Kill Bill Vol.1", seeders=1),
    ]
    pictures = cluster(releases)

    found = pick_franchise("Kill Bill: Vol. 1", pictures)
    assert [p.title for p in found] == ["Убить Билла", "Убить Билла 2"]
    assert sum(len(p.releases) for p in found) == 6, "вся франшиза, а не огрызок в одну раздачу"
    # Корень франшизы работает ровно как работал: добавленное имя лишь длиннее.
    assert [p.title for p in pick_franchise("Kill Bill", pictures)] == [
        "Убить Билла",
        "Убить Билла 2",
    ]


def test_full_latin_name_does_not_merge_namesakes() -> None:
    """TC-153: длинное имя РАЗВОДИТ однофамильцев, которых корень франшизы сводил.

    Гейт против подмены здесь держится на том, что добавленное в указатель имя ДЛИННЕЕ
    уже лежавшего там корня: «Хищник» ``Predator: Origins`` и «Добыча» ``Predator: Prey``
    делят корень ``predator``, и по корню запрос достаётся тому, у кого раздач больше.
    Полное имя каждую уводит к своей картине - дороги однофамильцам это не открывает,
    а закрывает.
    """
    releases = [
        *(_release("Хищник", 2018, original="Predator: Origins", seeders=n) for n in (50, 40, 30)),
        _release("Добыча", 2022, original="Predator: Prey", seeders=9),
    ]
    pictures = cluster(releases)

    assert [p.title for p in pick_franchise("Predator: Prey", pictures)] == ["Добыча"]
    assert [p.title for p in pick_franchise("Predator: Origins", pictures)] == ["Хищник"]


def test_the_number_sign_is_punctuation_and_not_two_latin_letters() -> None:
    """🔴 TC-192. «Легенда №17» и запрос «легенда 17» - одна и та же картина.

    Номер каталог вводит знаком «№», а человек его не набирает вовсе. Знак этот Unicode
    раскладывает в две ЛАТИНСКИЕ буквы (``NFKC``: ``№`` → ``No``), и картина получала имя
    «Легенда No17» с ключом ``легенда-no17``: с ``легенда-17`` он не сходится ни строкой,
    ни словами, ни цифрами. Дальше семнадцать съедал разбор номера части - франшиза
    «легенда», семнадцатой части в ней нет и быть не может, - и человек читал «номера 17
    нет» при живой картине в девять десятков сидов. Тот же шов резал «Палату №6».
    """
    assert slugify("Легенда №17") == slugify("Легенда 17") == "легенда-17"
    assert parse_release_name("Легенда №17 (2013) BDRip 1080p").title == "Легенда 17"
    assert parse_release_name("Палата №6 (2009) DVDRip").title == "Палата 6"

    pictures = cluster(
        [
            _release("Легенда 17", 2013, seeders=90),
            _release("Легенда", 2015, original="Legend", seeders=30),
        ]
    )
    assert [(p.title, p.year) for p in pick_franchise("легенда 17", pictures)] == [
        ("Легенда 17", 2013)
    ]
    # Имя без номера остаётся именем франшизы - обе картины, как и было.
    assert len(pick_franchise("легенда", pictures)) == 2


def test_a_tank_model_is_not_the_thirty_fourth_part_of_a_franchise() -> None:
    """🔴 TC-192. «Т-34» - марка танка, а не тридцать четвёртая часть серии «Т».

    Хвостовое число резалось как номер части, и от названия оставалась ОДНА БУКВА: ключ
    франшизы ``т``, номер части 34. Соседями картине в такой франшизе становится любой
    другой однобуквенный огрызок, а номер пункта меню человек читает как номер части.
    Франшизы из одной буквы не бывает - на этом правило и стоит.

    Строка «т 34», набранная через пробел, приходит к той же картине: номера 34 во
    франшизе нет, а вся строка целиком - имя, которым каталог картину и подписал.
    """
    assert part_number("Т-34") is None
    assert franchise_key("Т-34") == "т-34"
    pictures = cluster(
        [
            _release("Т-34", 2018, original="T-34", seeders=120),
            _release("Т-34", 2018, original="T-34", seeders=60),
        ]
    )
    for query in ("т-34", "т 34", "T-34"):
        assert [p.title for p in pick_franchise(query, pictures)] == ["Т-34"], query


def test_a_number_the_franchise_never_had_is_still_an_honest_empty_answer() -> None:
    """Ограждение к возврату «цифра была частью имени»: где номер - номер, там он и есть.

    Возврат к целой строке разрешён только при ПОЛНОМ совпадении с именем из каталога.
    Иначе «матрица 7» находила бы франшизу вхождением и вместо честного «номера 7 нет»
    выкладывала всю линейку - то есть отвечала бы на вопрос, которого не задавали.
    """
    pictures = cluster(
        [
            _release("Матрица", 1999, original="The Matrix", seeders=139),
            _release("Матрица: Перезагрузка", 2003, original="The Matrix Reloaded", seeders=48),
        ]
    )
    assert pick_franchise("матрица 7", pictures) == [], "седьмой «Матрицы» нет - и врать нечем"
    assert [p.title for p in pick_franchise("матрица 2", pictures)] == ["Матрица: Перезагрузка"]


def test_brother_two_is_the_year_two_thousand_and_not_a_fresh_namesake() -> None:
    """🔴 TC-192. «Брат 2» - фильм 2000 года, а не свежая тёзка первой части.

    В выдаче рядом лежат три картины под двумя именами, и в меню они отличаются одним
    годом в скобках. Номер части, названный вслух самим каталогом, сильнее позиции в
    хронологии (:func:`~torrcast.parse._numbered`) - им картина и выбирается; год же
    выбранной картины сверяет со справкой уже гейт года (TC-199/TC-200), потому что имя
    раздачи врёт и про него.
    """
    pictures = cluster(
        [
            _release("Брат", 1997, original="Brat", seeders=90),
            _release("Брат 2", 2000, original="Brat 2", seeders=80),
            _release("Брат", 2025, seeders=400),
        ]
    )
    assert [(p.title, p.year) for p in pick_franchise("брат 2", pictures)] == [("Брат 2", 2000)]
    assert [(p.title, p.year) for p in pick_franchise("брат", pictures)] == [
        ("Брат", 1997),
        ("Брат 2", 2000),
        ("Брат", 2025),
    ]


def test_seasons_named_reads_only_what_names_said() -> None:
    """TC-154: сезоны картины - это то, что назвали ИМЕНА раздач, и ничего сверх.

    «Гинтама» (2018) переживает привязку с 41 раздачей и 33 живыми, а на `s1e1` не даёт
    ни одного кандидата: все её раздачи подписаны сезонами 5-10, первого нет ни в одной.
    Молчащая о сезоне раздача сюда не попадает - она накрывает любой сезон, и называть
    её сезон было бы выдумкой.
    """
    from torrcast.parse import seasons_named

    picture = Picture(
        title="Гинтама",
        year=2018,
        kind="tv",
        releases=[
            parse_release_name("Gintama S06E06 Inside the Palace 1080p CR WEB-DL H 264-Kitsune"),
            parse_release_name("Gintama S10E22 Specter 1080p CR WEB-DL DDP2 0 H 264-Kitsune"),
            parse_release_name("[Sylvar] Gintama Season 8 (BD Remux 1080p x264 8-bit FLAC)"),
        ],
    )
    assert seasons_named(picture) == (6, 8, 10)
    assert 1 not in seasons_named(picture)

    silent = Picture(
        title="Gintama: 3-nen Z-gumi Ginpachi-sensei",
        year=None,
        kind="tv",
        releases=[parse_release_name("Gintama 3-nen Z-gumi Ginpachi-sensei 1080p BDRip x264")],
    )
    assert seasons_named(silent) == (), "имя о сезоне молчит - выдумывать нечего"


#: «Дюна» Джона Харрисона (2000) - реальные имена из выдачи домашних индексеров. Все шесть
#: подписаны одним русским именем, одним оригиналом и одним годом, а седьмое имя называет
#: серии - и уезжает в картину типа «сериал». Двух картин с ОДНИМ именем, годом и
#: оригиналом хватает, чтобы порядок в меню было нечем развязать.
_DUNE_2000 = (
    "Дюна / Frank Herbert's Dune (Джон Харрисон / John Harrison) [2000, США, Канада,"
    " Германия, Италия, Фантастика, драма, BDRip 720p] MVO + Original Eng (3 серии из 3-XX)",
    "Дюна / Frank Herbert's Dune (Джон Харрисон / John Harrison) [2000, США, Германия,"
    " Канада, Италия, фантастика, драма, приключения, DVDRip] DVO Видеосервис",
    "Дюна / Frank Herbert's Dune (Джон Харрисон / John Harrison) [2000, США, Германия,"
    " Канада, Италия, Фантастика, DVDRip - AVC]",
    "Дюна / Frank Herbert's Dune (Джон Харрисон / John Harrison) [2000, США, Канада,"
    " Германия, Италия, фантастика, фэнтези, драма, приключения, DVDRip] MVO",
    "Дюна / Frank Herbert's Dune (Джон Харрисон / John Harrison) [2000, США, Канада,"
    " Германия, Италия, Фантастика, драма, DVDRip]",
    "Дюна / Frank Herbert's Dune / S1E1-3 (3) (Джон Харрисон / John Harrison) [2000,"
    " Германия, США, Канада, Италия, фантастика, фэнтези, драма, приключения, DVD9]",
)

#: «Армитаж: Двойная матрица» (2002) - тот же фильм, но каталог пишет оригинал двумя
#: способами поровну. Каноническое имя картины считается большинством, а большинства нет.
_ARMITAGE = (
    "Армитаж: Двойная матрица / Armitage III: Dual Matrix (Акияма Кацухито /"
    " Akiyama Katsuhito) [move] [RUS(int)] [2002, приключения, фантастика, боевик,"
    " киберпанк, DVDRip]",
    "Армитаж: Двойная матрица / Armitage: Dual-Matrix (Акияма Кацухито) [2002,"
    " приключения, фантастика, боевик, киберпанк, DVD5]",
    "Армитаж: Двойная матрица / Armitage III: Dual Matrix [Movie] [RUS(int),ENG,JAP+Sub]"
    " [2002, приключения, фантастика, боевик, киберпанк, DVDRip]",
    "Армитаж: Двойная Матрица / Armitage: Dual-Matrix (2002) DVDRip-AVC | P",
    "Армитаж: Двойная матрица / Armitage: Dual Matrix (2002) WEBRip-HEVC 1080p | MC Entertainment",
)


@pytest.mark.parametrize("names", [_DUNE_2000, _ARMITAGE])
def test_the_picture_does_not_depend_on_who_answered_first(names: tuple[str, ...]) -> None:
    """🔴 Одна и та же выдача, разложенная в другом порядке, даёт ту же картину.

    Порядок раздач в списке - это порядок, в котором ответили индексеры, и картину он
    решать не вправе. Развязки ничьих в самих сортировках (TC-227) для этого мало:
    словарь синонимов и канон оригинала берут первую попавшуюся строку, а каноническое
    имя картины считается большинством, и при равном счёте побеждает тот, кто пришёл
    раньше. Замерено на сырых пулах (99 запросов, по 10 перетасовок): картина ехала у 59
    запросов, верхний релиз картины с тем же именем и годом - у 25.

    Живые случаи в фикстурах: у «Дюны» 2000 года местами менялись фильм и сериал -
    одноимённые, одногодки, с одним оригиналом, - и первым пунктом меню оказывалось то
    одно, то другое; у «Армитажа» плавал сам оригинал картины.
    """
    releases = [parse_release_name(name) for name in names]

    first = [(p.title, p.year, p.kind, p.original, len(p.releases)) for p in cluster(releases)]
    for shift in range(1, len(releases)):
        rotated = releases[shift:] + releases[:shift]
        again = [(p.title, p.year, p.kind, p.original, len(p.releases)) for p in cluster(rotated)]
        assert again == first, f"порядок прихода сдвинут на {shift} - картина другая"


#: 🔴 TC-244. Имена с живой выдачи: картину знают НЕ первым именем заголовка, а третьим.
#: Числом в комментарии - сколько строк выдачи стояло за этой раздачей на замере.
_THIRD_NAME = (
    ("Одна из многих / Из многих / Плюрибус / Pluribus (Сезон 1) WEB-DL 1080p", "плюрибус"),
    (
        "Птицы 2 / Марш пингвинов / La marche de l'empereur (2005) BDRip 1080p",
        "марш пингвинов",
    ),
    ("А в душе я танцую / Внутри себя я танцую (2004) BDRip 1080p", "внутри себя я танцую"),
    ("Каждый за себя / Загадка Каспара Хаузера (1974) DVDRip", "загадка каспара хаузера"),
)


@pytest.mark.parametrize(("name", "asked"), _THIRD_NAME)
def test_a_third_name_in_the_heading_finds_the_picture(name: str, asked: str) -> None:
    """🔴 TC-244. Псевдоним из заголовка находит картину в её же выдаче.

    Четыре промаха класса «не нашли» - и там это весь ответ: раздачи уже приехали, просто
    подписаны перечислением имён, а разбор читал из него первое имя и оригинал. «Плюрибус»
    (10 строк), «Марш пингвинов» (5), «Внутри себя я танцую» (13), «Загадка Каспара
    Хаузера» (1) падали в пустоту при живых раздачах в первой же выдаче.
    """
    release = parse_release_name(name)
    pictures = cluster([release])

    assert pick_franchise(asked, pictures) == pictures, f"«{asked}» обязано найтись своей выдачей"
    assert slugify(asked) not in {slugify(release.title), slugify(release.original or "")}, (
        "проверка имеет смысл, только если это имя не первое и не оригинал"
    )


def test_a_third_name_never_becomes_the_name_of_the_picture() -> None:
    """Псевдоним нужен поиску, а не меню: имя картины считает каталог, как и считал."""
    picture = cluster([parse_release_name(_THIRD_NAME[0][0])])[0]

    assert picture.title == "Одна из многих", "в меню - имя каталога, а не псевдоним"
    assert picture.original == "Pluribus"
    assert picture.aliases == ("из-многих", "плюрибус"), "псевдонимы лежат отдельно и по порядку"


def test_a_shared_alias_never_glues_two_different_pictures() -> None:
    """🔴 Одноимённость - больное место каталога, и псевдониму её открывать нельзя.

    Один и тот же псевдоним в заголовках двух РАЗНЫХ картин ничего не решает: выбрать
    между ними нечем, а молча подсунуть одну из двух хуже честного «не нашлось».
    """
    pictures = cluster(
        [
            parse_release_name("Ночная смена / Призраки (2019) BDRip 1080p"),
            parse_release_name("Дом у дороги / Призраки (2004) BDRip 1080p"),
        ]
    )

    assert len(pictures) == 2, "две разные картины"
    assert pick_franchise("призраки", pictures) == [], "однофамильцев не разводим - молчим"


def test_the_catalogues_own_name_outranks_any_alias() -> None:
    """Имя, которым каталог подписал картину сам, сильнее псевдонима чужого заголовка."""
    pictures = cluster(
        [
            parse_release_name("Призраки / Ghosts (2021) WEB-DL 1080p"),
            parse_release_name("Ночная смена / Призраки (2019) BDRip 1080p"),
        ]
    )
    found = pick_franchise("призраки", pictures)

    assert [p.title for p in found] == ["Призраки"], "точное имя каталога решает спор само"
