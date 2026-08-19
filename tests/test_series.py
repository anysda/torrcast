"""Серии = файлы раздачи: маппинг файлов в ``sNeM`` и отбор релизов по сезону.

Имена файлов взяты из живой выдачи Prowlarr и метаданных TorrServer: «Киберпанк:
Бегущие по краю», «Во все тяжкие», «Друзья», «Клиника», «Наруто». Ловушки тут не
выдуманные — каждая встретилась на настоящих раздачах.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.cluster import cluster
from torrcast.domain.config import Config
from torrcast.domain.episode import Episode
from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.map_episodes import map_episodes
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.picture import Picture
from torrcast.domain.runtime_guess import RUNTIME_GUESS
from torrcast.domain.split_episode import split_episode
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.rank.rank_releases import rank_releases
from torrcast.usecases.reinforce.plan_for import plan_for

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


def test_a_merged_double_episode_is_found_by_its_first_number() -> None:
    """🔴 TC-205: «друзья s10e17» — двойной финал одним файлом, и это ЕСТЬ s10e17.

    Сцена кладёт сдвоенную серию слитным именем: ``Friends.S10E17E18.The.Last.One.avi``
    (и вариант ``S10E17_18``). Страж границы слова видел за первым номером второй и не
    считал имя серией ВОВСЕ — файл молча выпадал из списка, и пак, объявивший «сезоны
    1-10: s1e1...s10e18», не мог отдать s10e17: серия лежала в раздаче, но не ложилась
    ни на какую пару «сезон, серия». Первый номер сдвоенного файла — честный ответ
    (тот же приём, что у ``10x17&18``): файл и есть семнадцатая серия.
    """
    for tail in ("S10E17E18", "S10E17_18", "10x17_18"):
        pack = files(
            "FRIENDS/Season 10/Friends.S10E16.The.One Where Estelle Dies.avi",
            f"FRIENDS/Season 10/Friends.{tail}.The.Last.One.avi",
        )
        found = map_episodes(pack)
        assert sne(found) == ["s10e16", "s10e17"], f"слитный номер {tail} потерял серию"

    # Весь путь целиком, как в живом показе: пак объявляет серию, choose её берёт.
    release = parse_release_name("Друзья / Friends [S01-10] (1994-2004) BDRip 1080p")
    pack = files(
        "FRIENDS/Season 10/Friends.S10E16.The.One Where Estelle Dies.avi",
        "FRIENDS/Season 10/Friends.S10E17E18.The.Last.One.avi",
    )
    series = _Series(want=Episode(10, 17))
    chosen = series.choose(release, pack)
    assert "S10E17E18" in chosen.name, "объявленная s10e17 берётся из двойного файла"

    # А слитный номер без разделителя серией не становится: «1080p» не хвост серии.
    glued = files(
        "Show/Show.S01E04.1080p.mkv",
        "Show/Show.S01E051080p.mkv",  # некорректное имя, а не «серия 5 в кадре 1080p»
    )
    assert sne(map_episodes(glued)) == ["s1e4"], "разделитель у второго номера обязателен"


def test_two_numbering_systems_are_named_aloud_instead_of_a_plain_miss() -> None:
    """🔴 TC-182: «гинтама s5e1» на раздаче со сквозным счётом — «нумерации разные».

    У «Гинтамы» сосуществуют ДВЕ системы координат: 38 раздач подписаны сезонами
    S05-S10 (нумерация стриминга), а куски RuTor — сквозным счётом через весь сериал
    (``[01-201]``, ``[202-252]``, ``[253-265]``). Это разные номера, и свести их честно
    нельзя: границ сезонов не назвало ни одно имя. Признак системы — из имени раздачи:
    сезон назван (``season``/``seasons``) или серии перечислены без сезона (сквозная
    линейка, как у :func:`torrcast.domain.run_span._run_span`). Сквозная раздача на просьбу о
    сезоне отвечает про РАЗНЫЕ нумерации и показывает обе, а не «серии нет» — серия
    там, скорее всего, есть, только под сквозным номером.
    """
    absolute = parse_release_name("Гинтама / Gintama TV-2 [202-252] (2011) BDRip-HEVC 1080p | L1")
    pack = files(*(f"Gintama/Gintama - {n}.mkv" for n in range(202, 253)))

    with pytest.raises(NotFoundError, match="нумерации разные"):
        _Series(want=Episode(5, 1)).choose(absolute, pack)

    # Своя система работает как работала: сквозной номер из сквозной раздачи берётся.
    assert "202" in _Series(want=Episode(1, 202)).choose(absolute, pack).name

    # А раздача, назвавшая сезон, на чужой сезон отвечает по-прежнему: «серии нет».
    by_season = parse_release_name("Гинтама / Gintama [S05] (2017) WEB-DL 1080p")
    season_pack = numbered("Gintama/Gintama.S05E{n:02d}.mkv", 12)
    with pytest.raises(NotFoundError, match="серии s6e1 в этой раздаче нет"):
        _Series(want=Episode(6, 1)).choose(by_season, season_pack)


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

    plan = plan_for(picture, args, Config())

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
    from torrcast.domain.episode import Episode
    from torrcast.domain.parse_release_name import parse_release_name
    from torrcast.domain.picture import Picture
    from torrcast.usecases.discover.season_gaps import season_gaps

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


def test_cross_season_episode_range_is_read() -> None:
    """TC-169: сквозной диапазон серий отдельной скобкой - это серии, а не фильм.

    Длинное аниме приезжает кусками, где сезона не назвали вовсе, а серии посчитали
    насквозь через весь сериал: «Гинтама / Gintama TV-1 [01-201] (2006)». Такое имя
    не читалось никак - ни серий, ни сериальности, - и раздача с ПЕРВОЙ серией
    становилась «фильмом» мимо разбора по сериям.
    """
    from torrcast.domain.episode import Episode
    from torrcast.domain.parse_release_name import parse_release_name

    first = parse_release_name("Гинтама / Gintama TV-1 [01-201] (2006) BDRip-HEVC  720p | L1")
    assert first.kind == "tv"
    assert first.episodes == tuple(range(1, 202))
    assert first.covers_episode(Episode(1, 1))

    later = parse_release_name("Гинтама / Gintama TV-2 [202-252] (2011) BDRip-HEVC 1080p | L1")
    assert later.episodes == tuple(range(202, 253))
    # Кусок, начинающийся с 202-й, первой серией себя не называет.
    assert not later.covers_episode(Episode(1, 1))

    # Годы в скобках сериями не становятся, а номера частей франшизы не подписывают
    # серии ни ведущим нулём, ни тремя цифрами.
    whole = parse_release_name(
        "Гинтама / Gintama TV [01-252] + OVA + Movies  + BONUS (2006-2012) DVDRip-AVC, HDTV-AVC"
    )
    assert whole.episodes == tuple(range(1, 253))
    assert parse_release_name("Форсаж [1-4] (2001-2009) BDRip 1080p").episodes == ()
    assert parse_release_name("Moana 2 2024 1080p WEB-DL DDP5 1 x264-NTb").episodes == ()
    assert parse_release_name("Moana 2 2024 1080p WEB-DL DDP5 1 x264-NTb").kind == "movie"


def test_a_whole_show_with_linear_episode_numbers_covers_later_seasons() -> None:
    """Полный пак с S1 и сквозным E не объявляет все поздние сезоны чужими."""
    linear = parse_release_name("Викинги / Vikings / S1E1-89 of 89 [2013-2020, WEB-DL 1080p] MVO")
    assert linear.season is None
    assert linear.episode_count == 89
    assert linear.covers(4)
    assert linear.covers_episode(Episode(4, 15))

    season = parse_release_name("Викинги / Vikings / S1E1-9 of 9 [2013, WEB-DL 1080p] MVO")
    assert season.season == 1
    assert not season.covers(4)

    short_show = parse_release_name(
        "Острые козырьки / Peaky Blinders / S1E1-36 of 36 [2013-2022, BDRip] MVO"
    )
    assert short_show.season is None
    assert short_show.covers_episode(Episode(5, 2))

    long_season = parse_release_name(
        "Мстители: Величайшие герои Земли / The Avengers / "
        "S1E1-26 of 26 [2010-2011, WEB-DL 1080p] Dub"
    )
    assert long_season.season == 1
    assert not long_season.covers(2)


def test_named_seasons_do_not_turn_their_count_into_episode_count() -> None:
    """Диапазоны сезонов и сквозных серий читаются независимо."""
    release = parse_release_name(
        "Игра престолов / Game of Thrones / Сезоны: 1-8 из 8 / E1-73 of 73 "
        "[2011-2019, WEB-DL 1080p] MVO"
    )
    assert release.seasons == tuple(range(1, 9))
    assert release.episode_count == 73
    assert release.covers_episode(Episode(8, 1))


def test_a_colon_after_the_season_word_does_not_invent_a_season_range() -> None:
    """«5 сезон: 1-3 серии из 3» - это серии пятого сезона, а не сезоны 1-3.

    Двоеточие после слова «сезон» на трекере чаще открывает перечень СЕРИЙ, чем
    диапазон сезонов, и разводит их только то, назван ли сезон ДО слова
    (:data:`~torrcast.domain._name_data.data_2._SEASON_SPAN_RES`). Без этой границы полный пак
    «Сезоны: 1-8 из 8» читался правильно, а каждое обычное имя сезона теряло свой номер.
    """
    one = parse_release_name(
        "Чёрное зеркало (5 сезон: 1-3 серии из 3) / Black Mirror / 2019 / ПД / WEBRip (720p)"
    )
    assert one.season == 5
    assert one.seasons == ()
    assert one.episode_count == 3

    whole = parse_release_name(
        "Клан Сопрано (1-6 сезоны: 1-86 серии из 86) / The Sopranos / 1999-2004 / АП / WEB-DL"
    )
    assert whole.seasons == tuple(range(1, 7))
    assert whole.episode_count == 86


def test_year_gate_lets_one_numbering_line_through() -> None:
    """TC-169: гейт года сшивает куски, продолжающие нумерацию, и держит ремейки.

    «Гинтама» идёт по каталогу шестью кусками с 2006 по 2018 год, и между крайними 12
    лет: гейт читал это как ремейк, и картина с первой серией оставалась в стороне от
    той, где лежали остальные 200. Ремейк при этом начинает счёт заново - по этому его
    и отличаем.
    """
    from torrcast.domain.glue import glue
    from torrcast.domain.parse_release_name import parse_release_name

    def picture(name: str, year: int | None) -> Picture:
        return Picture(title="Гинтама", year=year, kind="tv", releases=[parse_release_name(name)])

    early = picture("Гинтама / Gintama TV-1 [01-201] (2006) BDRip-HEVC  720p | L1", 2006)
    late = picture("Гинтама / Gintama TV-2 [202-252] (2011) BDRip-HEVC 1080p | L1", 2011)
    assert len(glue([early, late])) == 1

    # Счёт начат заново - это другая картина, и сшивать её нельзя.
    remake = picture("Гинтама / Gintama [01-24] (2011) BDRip-HEVC 1080p | L1", 2011)
    assert len(glue([early, remake])) == 2

    # Молчащие о сериях куски судит прежний гейт года.
    silent = picture("Гинтама / Gintama (2011) BDRip 1080p | L1", 2011)
    assert len(glue([early, silent])) == 2


def test_seasons_of_one_show_dated_apart_still_make_one_picture() -> None:
    """🔴 TC-201. Сезоны одного сериала подписаны РАЗНЫМИ годами - и это один сериал.

    Гейт года разводит одноимённые картины не зря (ремейк «Флэша» 2014-го не сериал
    1990-го), но у длинного сериала каждый сезон датирован своим годом, и гейт резал
    его на «годовые» картины: «Доктор Кто» давал 16 штук, «Чёрное зеркало» 7,
    «Клиника» 8. Выбор сезона тогда решался тем, какая из них выиграет ранжир: на
    ``доктор кто s5e10`` побеждала картина 2017 года при живой картине 2005 в том же меню.

    Сшивает их признак ПРОДОЛЖЕНИЯ НУМЕРАЦИИ (тот же приём, что для сквозной нумерации
    аниме), а не имя: у ремейка нумерация начинается заново, и он остаётся отдельным.
    """
    show = [
        parse_release_name(f"Доктор Кто / Doctor Who [S{n:02d}] ({year})")
        for n, year in enumerate(
            (2005, 2006, 2007, 2008, 2010, 2011, 2012, 2014, 2015, 2017), start=1
        )
    ]
    assert len(cluster(show)) == 1, "сезоны одного сериала - одна картина"

    remakes = [
        parse_release_name("Флэш / The Flash [S01] (1990)"),
        parse_release_name("Флэш / The Flash [S01] (2014)"),
    ]
    assert len(cluster(remakes)) == 2, "перезапуск начинает нумерацию заново - другая картина"


def test_a_stitched_show_is_dated_by_its_first_season() -> None:
    """🔴 Сшитый сериал подписан годом ПЕРВОГО сезона, а не самого обсиженного.

    Сшивка сезонов (TC-201) собирает в одну картину кучки, разъехавшиеся на десятилетия,
    и год картины брался у самой толстой из них. На живых пулах так и выходило: «Доктор
    Кто» - 12 раздач 2005-го против 90 раздач 2017-го - подписывался «(2017, сериал)»,
    «Игра престолов» - «(2019)», «Чёрное зеркало» - «(2019)».

    Врёт при этом не только строка меню. Справку ищут по паре «имя + год» и сверяют год
    по первым фразам статьи (:func:`torrcast.domain.facts.confirms.confirms`), а статья открывается
    годом начала сериала. С чужим годом справки не будет вовсе - ни рейтинга, ни описания, ни
    хронометража, по которому считается битрейт.
    """
    show = [
        parse_release_name("Доктор Кто / Doctor Who [S01] (2005) BDRip 1080p | D"),
        parse_release_name("Доктор Кто / Doctor Who [S02] (2006) BDRip 1080p | D"),
        parse_release_name("Доктор Кто / Doctor Who [S03] (2017) WEB-DL 1080p | D"),
        parse_release_name("Доктор Кто / Doctor Who [S03] (2017) WEB-DL 2160p | D"),
        parse_release_name("Доктор Кто / Doctor Who [S03] (2017) BDRemux 1080p | D"),
    ]

    pictures = cluster(show)

    assert len(pictures) == 1, "сезоны одного сериала - одна картина"
    assert pictures[0].year == 2005, "год сериала - тот, с которого он начался"


def test_same_named_different_shows_are_not_stitched_by_season_numbers() -> None:
    """🔴 TC-240. «Трансформеры» 2007 и «Трансформеры» 2017 - РАЗНЫЕ сериалы.

    Сшивка сезонов (TC-201) держится на номере сезона, а номер - улика короткая: у
    «Transformers: Animated» (2007-2009) есть сезоны 1-3, и любой чужой сериал под тем
    же русским именем, начавший со второго сезона, читался как его продолжение. Так
    «Transformers: Prime Wars Trilogy» (2017) и приклеился к мультсериалу десятилетней
    давности: 20 серий чужой картины уехали в чужое меню.

    Развело их имя, а не номер. Оригинальное название у раздачи было - «Трансформеры:
    Трилогия войн Праймов / Transformers: Prime Wars Trilogy», - но слово «трилогия»
    считалось меткой сборника и резало строку вместе с оригиналом, оставляя безымянного
    тёзку. В середине фразы это обычное слово названия, а меткой сборника оно бывает,
    только когда закрывает свой кусок: «Матрица: Трилогия / The Matrix».
    """
    animated = [
        parse_release_name(
            "Трансформеры / Transformers: Animated / S1E1-16 of 16 [2007] WEB-DL 1080p | D"
        ),
        parse_release_name(
            "Трансформеры / Transformers: Animated / S2E1-13 of 13 [2008] WEB-DL 1080p | D"
        ),
        parse_release_name(
            "Трансформеры / Transformers: Animated / S3E1-13 of 13 [2009] WEB-DL 1080p | D"
        ),
    ]
    stranger = parse_release_name(
        "Трансформеры: Трилогия войн Праймов / Transformers: Prime Wars Trilogy / "
        "S2E9-28 of 28 [2017, WEB-DL 1080p] Sub Rus"
    )

    pictures = cluster([*animated, stranger])

    assert len(pictures) == 2, "разные сериалы под одним русским именем - разные картины"
    same = next(p for p in pictures if p.original == "Transformers: Animated")
    assert len(same.releases) == 3, "сезоны своего сериала остались вместе"
    assert stranger.original == "Transformers: Prime Wars Trilogy", "оригинал раздача назвала"

    # Метка сборника на своём месте - в конце куска - режет имя, как и раньше.
    pack = parse_release_name("Матрица: Трилогия / The Matrix (1999) BDRip 1080p")
    assert pack.title == "Матрица"


def test_the_episode_table_belongs_to_the_release_being_played() -> None:
    """🔴 Список серий в состоянии - у ТОЙ раздачи, которую играют.

    Один ``_Series`` живёт на всю картину, а спрашивают его параллельно: подготовка
    поднимает запасные раздачи, и каждая зовёт :meth:`_Series.choose` из своего потока.
    Пока разбор ложился полем на объект, список серий картины оставляла ПОСЛЕДНЯЯ
    ответившая раздача. В живом показе это стоило автоперехода целиком: у пака «Рик и
    Морти» (21 серия) в состояние уезжал пустой список от соседней раздачи, сериал
    переставал быть сериалом (:attr:`torrcast.domain.entry.Entry.serial`), и следующая серия не
    поднималась вовсе.
    """
    pack = parse_release_name("Рик и Морти / Rick and Morty [S01-02] (2013) BDRip 1080p")
    played = numbered("Rick/Rick.and.Morty.S01E{n:02d}.1080p.BDRip.mkv", 11)
    series = _Series(want=Episode(1, 1))

    chosen = series.choose(pack, played)
    assert "S01E01" in chosen.name

    # Соседняя раздача той же картины отвечает позже и своей серии не находит: её разбор
    # обязан умереть вместе с её же отказом.
    other = parse_release_name("Рик и Морти / Rick and Morty [S09] (2026) WEB-DL 1080p")
    with pytest.raises(NotFoundError, match="серии s1e1 в этой раздаче нет"):
        series.choose(other, numbered("Rick/Rick.and.Morty.S09E{n:02d}.1080p.WEB-DL.mkv", 10))

    table = series.table(played, pack.season)
    assert len(table) == 11, "в состоянии серии сыгранной раздачи, а не соседней"
    assert table[0] == [1, 1, 1] and table[-1] == [1, 11, 11]
