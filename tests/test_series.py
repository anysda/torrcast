"""Серии = файлы раздачи: маппинг файлов в ``sNeM`` и отбор релизов по сезону.

Имена файлов взяты из живой выдачи Prowlarr и метаданных TorrServer: «Киберпанк:
Бегущие по краю», «Во все тяжкие», «Друзья», «Клиника», «Наруто». Ловушки тут не
выдуманные — каждая встретилась на настоящих раздачах.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from torrcast.cli import Args, _plan_for, rank_releases
from torrcast.parse import (
    Episode,
    EpisodeFile,
    Picture,
    map_episodes,
    parse_release_name,
    split_episode,
)
from torrcast.state import Config
from torrcast.stream import RUNTIME_GUESS, TorrFile

GB = 1024**3


def files(*names: str, size: int = GB) -> list[TorrFile]:
    """Файлы раздачи как их отдаёт TorrServer: сквозной номер, путь, размер."""
    return [TorrFile(i, name, size) for i, name in enumerate(names, start=1)]


def numbered(pattern: str, count: int, size: int = GB) -> list[TorrFile]:
    return files(*(pattern.format(n=n) for n in range(1, count + 1)), size=size)


def sne(found: list[EpisodeFile]) -> list[str]:
    return [str(f.at) for f in found]


def test_classic_season_episode_in_the_file_name() -> None:
    """`S01E01` в имени файла, «Season 1» в каталоге — самый частый вид раздачи."""
    raw = (
        "Cyberpunk Edgerunners (Season 1) HDR10 WEB-DL 1080p/"
        "Cyberpunk.Edgerunners.S01E{n:02d}.1080p.WEB-DL.HDR.HEVC.mkv"
    )
    found = map_episodes(numbered(raw, 10))

    assert len(found) == 10
    assert sne(found)[:2] == ["s1e1", "s1e2"] and sne(found)[-1] == "s1e10"
    assert [f.index for f in found] == list(range(1, 11)), "порядок серий = порядок файлов"


def test_dot_between_season_and_episode() -> None:
    """`Breaking.Bad.S01.E07` — точка между сезоном и серией тоже sNeM."""
    found = map_episodes(numbered("Breaking.Bad.S01.BDRip-SOFCJ/Breaking.Bad.S01.E{n:02d}.mkv", 7))

    assert sne(found) == [f"s1e{n}" for n in range(1, 8)]


def test_season_pack_maps_every_file_to_its_own_season() -> None:
    """Пак сезонов: серии нескольких сезонов, каждый файл — на свой ``sNeM``.
    «Пак или один сезон» решают ФАЙЛЫ: имя раздачи о числе сезонов может и соврать.
    """
    pack = files(
        *(
            f"Во все тяжкие/Season {s}/s{s:02d}e{e:02d}.avi"
            for s, count in ((1, 7), (2, 13), (3, 13))
            for e in range(1, count + 1)
        )
    )

    found = map_episodes(pack)

    assert len(found) == 33
    assert {f.season for f in found} == {1, 2, 3}
    assert sne(found)[:2] == ["s1e1", "s1e2"]
    assert sne(found)[7] == "s2e1", "после последней серии сезона идёт первая следующего"
    assert found[7].index == 8, "и её файл - тот, что лежит в каталоге Season 2"


def test_subtitles_and_bonus_files_are_not_episodes() -> None:
    """«Друзья»: на каждую серию рядом лежит .srt, а в конце — бонусный ролик без номера.
    Формат серий — ``01x01``, двойной финал ``10x17&18`` считается одной серией.
    """
    pack = files(
        "FRIENDS/Season 01/01x01 - The One Where Monica Gets A New Roomate.avi",
        "FRIENDS/Season 01/01x01 - The One Where Monica Gets A New Roomate.srt",
        "FRIENDS/Season 01/01x02 - The One With the Sonogram at the End.avi",
        "FRIENDS/Season 01/01x02 - The One With the Sonogram at the End.srt",
        "FRIENDS/Season 10/10x17&18 - The Last One Part 1 & 2.avi",
        "FRIENDS/Season 10/Friends - all about review.avi",
    )

    found = map_episodes(pack)

    assert sne(found) == ["s1e1", "s1e2", "s10e17"]
    assert all(not f.name.endswith(".srt") for f in found)


def test_cyrillic_x_between_season_and_episode() -> None:
    """«Клиника»: с третьего сезона релизер печатает кириллическую «х» — визуально
    неотличимо от латинской, и раздача целиком повисла бы на этой букве.
    """
    pack = files(
        "Scrubs/Season 2/Scrubs 2x24 My Dream Job.avi",
        "Scrubs/Season 3/Scrubs 3х01 My Own American Girl.avi",  # х - U+0445
    )

    assert sne(map_episodes(pack)) == ["s2e24", "s3e1"]


def test_anime_files_with_bare_numbers() -> None:
    """Аниме без sNeM в именах: голый номер серии и ни слова о сезоне — считаем первым."""
    raw = (
        "[VCB-Studio] Cyberpunk Edgerunners [BDRip 1080p x265 FLAC]/"
        "[VCB-Studio] Cyberpunk Edgerunners {n:02d} [BDRip 1080p x265 FLAC].mkv"
    )

    found = map_episodes(numbered(raw, 10))

    assert sne(found) == [f"s1e{n}" for n in range(1, 11)]
    assert "1080" not in sne(found)[0], "разрешение и кодек за номер серии не сходят"


def test_a_channel_name_is_not_a_season_number() -> None:
    """🔴 `Naruto.Shippuuden.001.IPTVRip.2x2.XviD.avi`: «2x2» — телеканал-рипер, а не
    «2 сезон 2 серия». Наивное чтение дало бы всем 318 файлам один и тот же номер —
    поэтому связность проверяется по всему списку, а не по одному имени.
    """
    raw = "Naruto.Shippuuden.2x2.IPTVRip.kitor/Naruto.Shippuuden.{n:03d}.IPTVRip.2x2.XviD.Rus.avi"

    found = map_episodes(numbered(raw, 20), season_hint=2)

    assert len(found) == 20, "все файлы стали разными сериями"
    assert sne(found)[:2] == ["s2e1", "s2e2"]
    assert sne(found)[-1] == "s2e20"


def test_openings_and_endings_are_not_episodes() -> None:
    """«Наруто»: рядом с сериями лежат опенинги и эндинги — тоже с голыми номерами."""
    root = "[SOFCJ] Naruto (DVDRip 768x576 HEVC)"
    small = 59 * 1024**2
    pack = [
        *files(f"{root}/OP-ED [Creditless]/Openings/[SOFCJ] Naruto OP - 01.mkv", size=small),
        *files(f"{root}/OP-ED [Creditless]/Endings/[SOFCJ] Naruto ED - 01.mkv", size=small),
        *numbered(root + "/[SOFCJ] Naruto - {n:03d} (DVDRip 768x576 HEVC).mkv", 5),
    ]

    found = map_episodes(pack)

    assert sne(found) == ["s1e1", "s1e2", "s1e3", "s1e4", "s1e5"]
    assert all("OP" not in f.name and "ED" not in f.name for f in found)


def test_sample_files_are_dropped_by_size() -> None:
    """Сэмпл — те же серии в миниатюре: и по имени, и по размеру он не серия."""
    pack = [
        *numbered("Series.S01E{n:02d}.1080p.mkv", 5),
        TorrFile(6, "Series.S01E06.sample.mkv", 20 * 1024**2),
        TorrFile(7, "Series.S01E07.1080p.mkv", 30 * 1024**2),  # огрызок: 3 % от медианы
    ]

    found = map_episodes(pack)

    assert sne(found) == ["s1e1", "s1e2", "s1e3", "s1e4", "s1e5"]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Сериал (2024)/05 из 24 серии.mkv", "s1e5"),
        ("Сериал/Сериал - 12 серия.mkv", "s1e12"),
        ("Show/E07.mkv", "s1e7"),
        ("Show/Show.ep.09.mkv", "s1e9"),
    ],
)
def test_episode_without_a_season_in_the_name(name: str, expected: str) -> None:
    """Номер серии есть, сезона нет: «05 из 24», «12 серия», ``E07``, ``ep.09``."""
    other = name.replace("05", "06").replace("12", "13").replace("07", "08").replace("09", "10")
    pack = [*files(name), *files(other)]

    assert sne(map_episodes(pack))[0] == expected


def test_season_comes_from_the_folder_when_the_file_is_silent() -> None:
    """Сезон живёт в каталоге, номер серии — в имени файла: складываем одно с другим."""
    pack = files(*(f"Сериал/3 сезон/{n:02d}.mkv" for n in (1, 2, 3)))

    assert sne(map_episodes(pack)) == ["s3e1", "s3e2", "s3e3"]


def test_the_release_season_is_used_when_nothing_else_says_it() -> None:
    """Ни в файле, ни в каталоге сезона нет — берём его из имени раздачи (подсказка)."""
    pack = numbered("Series/{n:02d}.mkv", 3)

    assert sne(map_episodes(pack, season_hint=4)) == ["s4e1", "s4e2", "s4e3"]


def test_files_without_any_numbers_keep_the_order_of_the_release() -> None:
    """Номеров нет вовсе — нумеруем по порядку файлов: это лучше, чем «серий не нашлось»."""
    pack = files("Сериал/Пилот.mkv", "Сериал/Знакомство.mkv", "Сериал/Развязка.mkv")

    assert sne(map_episodes(pack)) == ["s1e1", "s1e2", "s1e3"]


def test_a_release_without_video_files_maps_to_nothing() -> None:
    assert map_episodes(files("Сериал/readme.txt", "Сериал/cover.jpg")) == []


def test_the_same_episode_twice_keeps_the_bigger_file() -> None:
    """Две версии одной серии в раздаче — играем ту, что крупнее (обычно она и лучше)."""
    pack = [
        TorrFile(1, "Series/S01E01.480p.mkv", 300 * 1024**2),
        TorrFile(2, "Series/S01E01.1080p.mkv", 2 * GB),
        TorrFile(3, "Series/S01E02.1080p.mkv", 2 * GB),
    ]

    found = map_episodes(pack)

    assert sne(found) == ["s1e1", "s1e2"]
    assert found[0].index == 2


def test_release_name_tells_which_seasons_it_covers() -> None:
    """Отбор релизов под нужный сезон: пак `[S01-06]` покрывает шестой сезон,
    раздача одного сезона — нет, а молчащее о сезоне имя под подозрением не держим.
    """
    pack = parse_release_name("Во все тяжкие / Breaking Bad [S01-06] (2008) BDRip 1080p")
    single = parse_release_name("Во все тяжкие / Breaking Bad [S02] (2009) BDRip 1080p")
    silent = parse_release_name("Во все тяжкие / Breaking Bad (2008) BDRip 1080p")

    assert pack.seasons == (1, 2, 3, 4, 5, 6) and pack.covers(6) and not pack.covers(7)
    assert single.season == 2 and single.covers(2) and not single.covers(3)
    assert silent.covers(1) and silent.covers(9), "имя молчит - решат файлы"


@pytest.mark.parametrize(
    "name,inside,outside",
    [
        # Живая выдача «Наруто»: огрызок на восемь серий и полный пак на 220.
        ("Наруто / Naruto [S01E01-08 of 220] (2002-2007) BDRip", (1, 8), (9, 220)),
        ("Наруто / Naruto [TV] [1-5 из 220] [2002, DVDRip] [1080p]", (1, 5), (6, 220)),
        ("Наруто (S1) / Naruto [TV] [E220 of 220] [RUS(ext), JAP+Sub] [2002]", (1, 220), ()),
        # Одна серия целым релизом: аниме-раздачи так лежат сплошь и рядом.
        ("Локи / Loki S01E03 (2021) WEB-DL 1080p", (3,), (1, 2, 4)),
        ("Киберпанк / Cyberpunk Edgerunners [01-10 of 10] (2022) WEB-DL 1080p", (1, 10), (11,)),
    ],
)
def test_release_name_tells_which_episodes_are_inside(
    name: str, inside: tuple[int, ...], outside: tuple[int, ...]
) -> None:
    """Огрызок отличается от сезон-пака своим же именем — и это стоит ноль секунд.

    Ровно тот вопрос, на котором авто-выбор ловился у «Наруто», «Локи» и
    «Сверхъестественного»: верхом отбора стоял огрызок, а полный сезон лежал строкой
    ниже, и «серии s1e1 в этой раздаче нет» выяснялось уже после похода в рой.
    """
    release = parse_release_name(name)

    assert all(release.covers_episode(Episode(1, n)) for n in inside), "названные серии внутри"
    assert not any(release.covers_episode(Episode(1, n)) for n in outside), "остальных нет"


def test_a_season_pack_and_a_silent_name_are_never_accused_of_missing_an_episode() -> None:
    """Пак сезонов и молчаливое имя под подозрение не попадают: решат файлы.

    Иначе у сериала, где серии не перечисляет ни одно имя (а это норма), не осталось бы
    ни одного кандидата — и починка сезон-паков сломала бы обычный сериал.
    """
    pack = parse_release_name("Сверхъестественное / Supernatural [S01-15] (2005-2020) WEB-DL")
    silent = parse_release_name("Локи / Loki [S01] (2021) WEB-DL 1080p-LostFilm")

    assert pack.episodes == () and silent.episodes == ()
    assert pack.covers_episode(Episode(1, 1)) and pack.covers_episode(Episode(15, 20))
    assert silent.covers_episode(Episode(1, 1)) and silent.covers_episode(Episode(1, 6))
    assert not pack.covers_episode(Episode(16, 1)), "сезона нет - и серии нет"


def test_the_selector_prefers_the_pack_that_has_the_wanted_episode() -> None:
    """Огрызок уходит под всех, кто может содержать серию, даже с кратной разницей в сидах.

    Живой замер «Наруто»: верхом стоял ``[S01E01-08 of 220]`` на 1 сиде, а полный пак
    на 220 серий и 91 сид лежал третьим. Просьба про двадцатую серию гарантированно
    упиралась в «серии s1e20 в этой раздаче нет» — при том, что серия была рядом.
    """
    stub = parse_release_name("Наруто / Naruto [S01E01-08 of 220] (2002) BDRip 1080p")
    full = parse_release_name("Наруто / Naruto [S01] [E220 of 220] (2002) BDRip 1080p")
    stub = replace(stub, size=8 * GB, seeders=900)
    full = replace(full, size=160 * GB, seeders=1)
    runtime = RUNTIME_GUESS["tv"]

    assert rank_releases([stub, full], runtime, 40.0)[0] is stub, "без серии решают сиды"
    assert rank_releases([stub, full], runtime, 40.0, want=Episode(1, 1))[0] is stub
    order = rank_releases([stub, full], runtime, 40.0, want=Episode(1, 20))
    assert order[0] is full, "нужна двадцатая - верх тот, у кого она есть"
    assert order[1] is stub, "и всё же не выкинут: руками --release N его возьмут"


def test_a_stub_release_is_thrown_out_before_the_swarm_not_after() -> None:
    """Огрызок не попадает в очередь попыток вовсе — и отбраковка не молчаливая.

    Попыток всего три, и каждая стоит 5-40 с метаданных по DHT. Тратить их на раздачи,
    которые уже своим именем сказали «нужной серии тут нет», незачем.
    """
    stub = replace(
        parse_release_name("Наруто / Naruto [S01E01-08 of 220] (2002) BDRip 1080p"),
        size=8 * GB,
        seeders=900,
    )
    full = replace(
        parse_release_name("Наруто / Naruto [S01] [E220 of 220] (2002) BDRip 1080p"),
        size=160 * GB,
        seeders=1,
    )
    picture = Picture(title="Наруто", year=2002, kind="tv", releases=[stub, full])
    args = Args(query=["наруто s1e20"])

    plan = _plan_for(picture, args, Config())

    assert plan.candidates(args) == [1], "в очереди только пак с двадцатой серией"
    assert plan.skipped == [stub], "а огрызок назван вслух, а не выкинут молча"


@pytest.mark.parametrize(
    "query,title,expected",
    [
        ("киберпанк s2e5", "киберпанк", (2, 5)),
        ("киберпанк 2x5", "киберпанк", (2, 5)),
        ("киберпанк 2 сезон 5 серия", "киберпанк", (2, 5)),
        ("во все тяжкие S01E01", "во все тяжкие", (1, 1)),
        ("матрица 2", "матрица 2", None),
    ],
)
def test_the_episode_is_cut_off_the_query(
    query: str, title: str, expected: tuple[int, int] | None
) -> None:
    """Указание серии отделяется от запроса — в Prowlarr уедет «киберпанк», а не
    «киберпанк 2x5». Номер франшизы («матрица 2») серией не считается.
    """
    name, found = split_episode(query)

    assert name == title
    assert ((found.season, found.episode) if found else None) == expected


def test_season_gaps_speaks_instead_of_dropping_picture() -> None:
    """TC-154: сериал, выпавший из меню из-за отсутствия сезона, называет себя вслух.

    Замер на «Гинтама»: картина 2018 года доезжает до меню с 41 раздачей и 33 живыми,
    план по ней не строится (ни одна раздача не назвала первый сезон - в именах стоят
    5-10), и она молча исчезала из списка. Человек читал дефолт, вставший на спин-офф
    «Gintama: 3-nen Z-gumi Ginpachi-sensei», и ни одного слова о том, куда делся
    основной сериал. Молчаливых отказов у нас не бывает.
    """
    from torrcast.cli import season_gaps
    from torrcast.parse import Episode, Picture, parse_release_name

    gintama = Picture(
        title="Гинтама",
        year=2018,
        kind="tv",
        releases=[
            parse_release_name("Gintama S06E06 Inside the Palace 1080p CR WEB-DL H 264-Kitsune"),
            parse_release_name("Gintama S10E22 Specter 1080p CR WEB-DL DDP2 0 H 264-Kitsune"),
        ],
    )
    spinoff = Picture(
        title="Gintama: 3-nen Z-gumi Ginpachi-sensei",
        year=None,
        kind="tv",
        releases=[parse_release_name("Gintama 3-nen Z-gumi Ginpachi-sensei 1080p BDRip x264")],
    )

    lines = season_gaps([gintama, spinoff], shown=set(), want=Episode(1, 1))
    assert lines == ["«Гинтама» (2018): раздач 2, но сезона 1 среди них нет - названы 6, 10"]
    # Картина, попавшая в меню, о себе не рассказывает: рассказывать не о чем.
    assert season_gaps([gintama], shown={gintama.key}, want=Episode(1, 1)) == []
    # Имена, молчащие о сезонах, не дают повода сказать «сезона нет»: это была бы ложь.
    assert season_gaps([spinoff], shown=set(), want=Episode(1, 1)) == []
