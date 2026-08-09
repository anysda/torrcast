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
    cluster,
    franchise_key,
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
