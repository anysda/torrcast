"""Отбор релиза у аниме: ворота для молчаливых имён и предпочтение русской озвучки.

Аниме — худший жанр замера покрытия, и обе причины видны прямо в именах раздач.
Первая: у аниме имя сплошь не называет ни разрешения, ни кодека, ни HD-источника, и
ворота отбора оставляют картину вообще без живых кандидатов. Вторая: японская дорожка
без перевода — это не «звук похуже», а несмотренный тайтл, и русский дубляж у аниме
часто лежит ОТДЕЛЬНОЙ раздачей, которая по сидам проигрывает вчистую.

Имена здесь взяты с живой выдачи Prowlarr (Knaben, RuTor, Nyaa) и не причёсаны:
именно их своеобразие ворота и не переваривали.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from torrcast.cli import (
    SD_BITRATE,
    Args,
    _plan_for,
    bitrate_of,
    gate_open,
    is_candidate,
    is_dated,
    is_dead,
    rank_releases,
    sound_note,
)
from torrcast.parse import Picture, Release, parse_release_name
from torrcast.state import Config
from torrcast.stream import RUNTIME_GUESS, AudioTrack, Media

RUNTIME = RUNTIME_GUESS["movie"]
GB = 1024**3

#: Тот самый пак: 220 серий, 91 сид, и ни слова о разрешении или кодеке в имени.
NARUTO_FULL = (
    "Наруто (S1) / Naruto (Датэ Хаято) [TV] [E220 of 220] [RUS(ext), ENG, JAP+Sub] "
    "[2002, приключения, комедия, боевые искусства, сёнэн, DVDRip]"
)


def named(name: str, *, size_gb: float, seeders: int) -> Release:
    """Релиз из живого имени: размер и сиды — те же, что отдал индексер."""
    return replace(parse_release_name(name), size=int(size_gb * GB), seeders=seeders)


def test_a_full_anime_pack_without_a_single_quality_marker_gets_into_the_queue() -> None:
    """Молчаливый пак на 91 сид — кандидат, когда именные кандидаты умирают.

    Живая выдача «наруто»: у картины «Наруто» (2002) три раздачи. Полный сериал на
    220 серий держит 91 сид и о качестве молчит, а именные кандидаты — «[1-5 из 220]»
    на три сида и «[S01E01-08 of 220]» на один. Очередь из двух умирающих огрызков —
    это не защита от мусора, это отсутствие показа.
    """
    full = named(NARUTO_FULL, size_gb=157.3, seeders=91)
    five = named(
        "Наруто / Naruto [TV] [1-5 из 220] [RUS(int)] [2002, боевые искусства, DVDRip] [1080p]",
        size_gb=6.8,
        seeders=3,
    )
    eight = named(
        "Наруто / Naruto [S01E01-08 of 220] (2002-2007) BDRip | D | AniOmnia + StudioBand",
        size_gb=4.0,
        seeders=1,
    )
    picture = Picture(title="Наруто", year=2002, kind="tv", releases=[full, five, eight])
    args = Args(query=["наруто", "s1e1"])

    plan = _plan_for(picture, args, Config())

    assert plan.loose, "живого именного кандидата у картины нет — ворота открыты"
    assert plan.ranked[0] is full, "дефолт — единственная живая раздача, а не огрызок на 3 сида"
    assert plan.candidates(args)[:1] == [1]
    assert len(plan.candidates(args)) == 3, "запасные остались, судить их будет ffprobe"


def test_a_rich_movie_keeps_the_gate_shut_and_the_queue_named() -> None:
    """У картины с богатой выдачей ворота не открываются, и мусор в очередь не течёт.

    Ровно тот случай, ради которого ворота и стоят: живой именной кандидат есть, а
    значит молчаливой раздаче в кандидатах делать нечего — её очередь не наступит.
    """
    good = named("Кино / Movie (1999) BDRip 1080p | D", size_gb=8.0, seeders=200)
    second = named("Кино / Movie (1999) WEB-DL 1080p | D", size_gb=9.0, seeders=140)
    mute = named("Кино / Movie (1999) Complete", size_gb=4.0, seeders=180)
    picture = Picture(title="Кино", year=1999, releases=[good, second, mute])
    args = Args(query=["кино"])

    plan = _plan_for(picture, args, Config())

    assert not plan.loose, "живых именных кандидатов двое — открывать нечего"
    assert not is_candidate(mute, RUNTIME, 25.0), "молчаливая раздача кандидатом не стала"
    assert [plan.ranked[n - 1] for n in plan.candidates(args)] == [good, second]


def test_the_open_gate_does_not_let_a_game_repack_pretend_to_be_a_show() -> None:
    """Не-видео не проходит ни при каких воротах — оно не «неизвестного качества».

    Живая выдача «one piece»: репак игры «Pirate Warriors 4 … PC» несёт 97 сидов и о
    качестве видео молчит по той причине, что видео там нет. Пока послабление его не
    отсекало, он перевешивал сериал с русским дубляжом и вставал дефолтом меню.
    """
    game = named(
        "One Piece: Pirate Warriors 4: Legendary Edition [v 1.0.8.6 + DLCs] (2020) PC | RePack",
        size_gb=12.0,
        seeders=97,
    )

    assert game.kind == "other"
    assert game.quiet, "о качестве видео имя молчит — видео там нет"
    assert not is_candidate(game, RUNTIME, 25.0, loose=True)


def test_a_name_that_confessed_its_codec_stays_outside_the_open_gate() -> None:
    """Послабление — про молчание, а не про плохие новости: названный HEVC остаётся вне.

    Разница принципиальная. Молчание — отсутствие оценки, и судить его может только
    ffprobe. Названный HEVC — оценка, и она уже дана: приёмник его не декодирует.
    """
    hevc = named("Аниме / Anime [TV] [12 of 12] BDRip-HEVC 1080p", size_gb=10.0, seeders=300)
    mute = named("Аниме / Anime [TV] [12 of 12] Complete", size_gb=10.0, seeders=300)

    assert not is_candidate(hevc, RUNTIME, 25.0, loose=True)
    assert is_candidate(mute, RUNTIME, 25.0, loose=True)


def test_the_gate_stays_shut_when_nobody_in_the_pool_is_alive() -> None:
    """Мёртвый пул открывать незачем: показывать всё равно нечего."""
    dead = named("Аниме / Anime [TV] [12 of 12] Complete", size_gb=10.0, seeders=0)

    assert not gate_open([dead], RUNTIME, 25.0)


def test_a_russian_dub_outranks_a_japanese_only_release_with_more_seeders() -> None:
    """Русская озвучка обыгрывает чисто японский релиз, даже когда тот сидастее.

    Живая выдача «наруто», картина «Боруто»: «[JAP+Sub] WEB-DL 1080p» держит 8 сидов,
    «[RUS(int)]» — три. Смотреть первый нельзя: субтитры мы решили не делать, а
    японского языка у зрителя нет. Восемь сидов против трёх этого не меняют.
    """
    japanese = named(
        "Боруто / Boruto: Naruto Next Generations [TV] [225-293] [JAP+Sub] [2017, WEB-DL] [1080p]",
        size_gb=93.8,
        seeders=8,
    )
    russian = named(
        "Боруто / Boruto: Naruto Next Generations [TV] [168-180 из 293] [RUS(int)] "
        "[2017, WEB-DL] [1080p]",
        size_gb=9.4,
        seeders=3,
    )

    assert rank_releases([japanese, russian], RUNTIME, 25.0)[0] is russian


def test_a_dead_russian_release_does_not_beat_a_live_one() -> None:
    """Мёртвый рой — не выигрыш ни на каком языке.

    Живая выдача «наруто»: у «Ураганных хроник» русская раздача имеет НОЛЬ сидов
    против трёх у соседней. Поднять её значило бы поменять японский показ на никакой.
    """
    alive = named(
        "Наруто / Naruto: Shippuuden [001-500] (2007) BDRip 1080p", size_gb=47.5, seeders=3
    )
    dead = named(
        "Наруто: Ураганные хроники / Naruto: Shippuuden [001-356] (2007) WEB-DL 1080p | Дубляж",
        size_gb=110.0,
        seeders=0,
    )

    assert rank_releases([alive, dead], RUNTIME, 25.0)[0] is alive


def test_a_zero_seeded_release_never_stands_above_a_live_one() -> None:
    """Ноль сидов — это не «качество получше», а отсутствие показа: такая раздача вниз.

    Живая выдача «наруто». Верхом отбора стоял ``WEBRip 720p | Akari Group`` на 46 ГБ с
    НУЛЁМ сидов: имя у него чистое, ступень старья он проходит, — а раздача с тремя
    живыми сидами лежала ниже, потому что призналась в ``DVDRip``. Enter в такой верх
    стоит двадцати секунд молчания DHT и перехода к следующему, то есть ровно столько
    же, сколько стоит пустой старт.
    """
    tv = RUNTIME_GUESS["tv"]
    dead = named(
        "Наруто: Ураганные хроники / Naruto Shippuuden [S01E01-18 of 45] (2007-2017) "
        "WEBRip 720p | Akari Group",
        size_gb=46.2,
        seeders=0,
    )
    alive = named(
        "Наруто / Naruto [TV] [1-5 из 220] [RUS(int)] "
        "[2002, приключения, боевые искусства, сёнэн, DVDRip] [1080p]",
        size_gb=6.8,
        seeders=3,
    )

    assert is_dead(dead, alive=3) and not is_dead(alive, alive=3)
    assert is_dated(alive, tv) and not is_dated(dead, tv), (
        "по ступени старья мёртвый выигрывает — и до правки этого хватало, чтобы встать верхом"
    )
    assert rank_releases([dead, alive], tv, 25.0)[0] is alive


def test_a_pool_where_nobody_is_seeded_keeps_its_order() -> None:
    """Мёртвые ВСЕ — понижать некого и не в пользу кого: ступень живости молчит."""
    first = named(
        "Аниме / Anime [TV] [12 of 12] [RUS(int)] [2020, WEB-DL] [1080p]", size_gb=8.0, seeders=0
    )
    second = named(
        "Аниме / Anime [TV] [12 of 12] [JAP+Sub] [2020, WEB-DL] [1080p]", size_gb=8.0, seeders=0
    )

    assert not is_dead(first, alive=0) and not is_dead(second, alive=0)
    assert rank_releases([second, first], RUNTIME, 25.0)[0] is first


def test_an_anime_pack_is_not_called_dated_for_its_genre_bitrate() -> None:
    """Серия аниме идёт 24 минуты и жмётся в разы лучше живой съёмки — это не старьё.

    Живая выдача «наруто ураганные хроники»: пак «[TV] [500 из 500] [RUS(MVO)]» на 9.7 ГБ
    держит семь сидов и русскую многоголоску. Пятьсот серий в такой раздаче — это
    прикидка в 0.06 Мбит/с на серию, то есть глубоко ниже порога SD; метку «старьё» пак
    получал за неё и проваливался под соседа с ОДНИМ сидом. Сосед, к слову, ничем не
    лучше по имени: тот же 2007 год, тот же WEB-рип, — он просто НЕ СЧИТАЕТ свои серии
    («[243-405 из XXX]»), а значит и прикидывать у него нечего.

    Ворота отбора у такой картины открыты (:func:`gate_open`): именных кандидатов, кроме
    умирающего соседа, у неё нет.
    """
    pack = named(
        "Наруто Ураганные хроники / Naruto Shippuden [TV] [500 из 500] [RUS(MVO)] [2007, AAC]",
        size_gb=9.7,
        seeders=7,
    )
    rival = named(
        "Наруто: Ураганные хроники / Naruto: Shippuuden [TV] [243-405 из XXX] [RUS(int), JAP+Sub] "
        "[2007, приключения, боевые искусства, сёнэн, WEBRip] [1080p]",
        size_gb=90.4,
        seeders=1,
    )
    tv = RUNTIME_GUESS["tv"]

    assert pack.anime and pack.quiet, "имя аниме о качестве молчит — тем и жив признак"
    assert 0.0 < bitrate_of(pack, tv) < SD_BITRATE, (
        "битрейт по прикидке и правда ниже порога SD — спор именно о том, что это значит"
    )
    assert not is_dated(pack, tv), "жанровый битрейт старьём не делает"
    assert gate_open([pack, rival], tv, 25.0)
    assert rank_releases([rival, pack], tv, 25.0, loose=True)[0] is pack


def test_a_named_sd_anime_is_still_dated_for_all_its_genre() -> None:
    """Признак жанра выключает ОДНУ прикидку по размеру, а не весь порядок.

    Аниме, которое призналось именем — ``DVDRip``, ``XviD``, «480p», — старьём быть не
    перестало: там имя сказало о себе правду, а спорить с правдой признак не нанимался.
    """
    rip = named(
        "Аниме / Anime [TV] [12 of 12] (2002) DVDRip XviD | Дубляж", size_gb=4.0, seeders=100
    )
    sd = named("Аниме / Anime [TV] [12 of 12] [2002, WEB-DL] [480p]", size_gb=4.0, seeders=100)
    good = named("Аниме / Anime [TV] [12 of 12] [2020, WEB-DL] [1080p]", size_gb=8.0, seeders=100)

    assert rip.anime and sd.anime
    assert is_dated(rip, RUNTIME) and is_dated(sd, RUNTIME)
    assert rank_releases([rip, sd, good], RUNTIME, 25.0)[0] is good


def test_the_sound_step_never_outranks_honest_quality() -> None:
    """Русский .avi вместо честного 1080p — не размен, а откат: ступень звука ниже старья."""
    old = named("Аниме / Anime (2002) DVDRip XviD | Дубляж", size_gb=1.4, seeders=100)
    good = named("Аниме / Anime (2002) WEB-DL 1080p", size_gb=8.0, seeders=100)

    assert rank_releases([old, good], RUNTIME, 25.0)[0] is good


@pytest.mark.parametrize(
    "name,promised",
    [
        ("Аниме [TV] [12 of 12] [RUS(int), JAP+Sub] [2020, WEBRip] [1080p]", True),
        ("Аниме [TV] [12 of 12] [RUS(ext), ENG, JAP+Sub] [2020, DVDRip]", True),
        ("Naruto: Shippuuden [01-500 из 500] (2007) BDRip-HEVC 1080p | Shiza Project", True),
        ("Naruto- Shippuuden - AniLiberty.TOP [HDTVRip 720p][AVC][370-500]", True),
        ("Кино / Movie (1999) WEB-DL 1080p | D", True),
        ("Аниме [TV] [12 of 12] [JAP+Sub] [2020, WEBRip] [1080p]", False),
        ("Аниме [TV] [12 of 12] [JAP+Rus Sub] [2020, WEBRip] [1080p]", False),
        ("[Yameii] Chainsaw Man the Movie (2025) [English Dub] [CR WEB-DL 1080p]", False),
        ("[Funimation] Steins Gate 0 [Multi-Dub][ESP-LAT][PT-BR][Multi-Sub][1080p]", False),
        ("[SubsPlease] Chainsaw Man Movie - Reze-hen (1080p) [0066A2DD].mkv", False),
    ],
)
def test_the_name_is_read_for_a_russian_track_not_for_subtitles(name: str, promised: bool) -> None:
    """Обещание русской ДОРОЖКИ читается из имени, а титры и чужой дубляж — не обещание.

    Три ловушки живой выдачи разом: «Rus Sub» — это титры; «English Dub» и «Multi-Dub» —
    дубляж, только не тот; а «| Shiza Project» и «AniLiberty» — единственный маркер
    дорожки во всём имени, и без него аниме-раздача выглядит немой.
    """
    assert parse_release_name(name).dubbed is promised


def _media(*languages: str) -> Media:
    tracks = tuple(AudioTrack(index=i, language=lang) for i, lang in enumerate(languages))
    return Media(duration=1440.0, tracks=tracks, video="h264", height=1080, width=1920)


def test_a_japanese_only_show_says_so_out_loud_instead_of_playing_silently() -> None:
    """Перевода в каталоге нет — человек слышит об этом строкой, а не на слух.

    Решение владельца: субтитров не делаем. Значит японский тайтл останется японским, и
    единственное честное поведение — сказать это ДО картинки. Показ при этом играет:
    решает зритель, наше дело — предупредить.
    """
    pool = [named("Аниме [TV] [12 of 12] [JAP+Sub] [2020, WEBRip] [1080p]", size_gb=8, seeders=50)]

    assert sound_note(_media("jpn"), 0, pool) == "только японский звук, перевода в каталоге нет"


def test_when_the_catalogue_does_have_a_dub_the_line_says_where_to_look() -> None:
    """Перевод в выдаче есть, а в ЭТОМ релизе его не оказалось — так бывает у ``RUS(ext)``,
    где русская дорожка лежит отдельным файлом. Тогда строка обязана назвать и запасной ход.
    """
    pool = [
        named(NARUTO_FULL, size_gb=157.3, seeders=91),
        named(
            "Наруто / Naruto [TV] [1-5 из 220] [RUS(int)] [2002, DVDRip] [1080p]",
            size_gb=6.8,
            seeders=3,
        ),
    ]

    note = sound_note(_media("jpn", "eng"), 0, pool)

    assert note.startswith("только японский звук - перевода в этом релизе нет")
    assert "--release N" in note


def test_a_release_with_a_russian_track_says_nothing_extra() -> None:
    """Русская дорожка на месте — предупреждать не о чем, лишних строк не печатаем."""
    pool = [named("Кино / Movie (1999) WEB-DL 1080p | D", size_gb=8, seeders=100)]

    assert sound_note(_media("jpn", "rus"), 1, pool) == ""


def test_the_line_names_the_language_it_actually_hears() -> None:
    """Язык берётся из дорожки, а не додумывается: у французского кино японскому
    звуку взяться неоткуда, а незнакомый код честнее назвать «оригинальным».
    """
    pool = [named("Кино / Movie (1999) WEB-DL 1080p", size_gb=8, seeders=100)]

    assert "только французский звук" in sound_note(_media("fra"), 0, pool)
    assert "только оригинальный звук" in sound_note(_media("swe"), 0, pool)


def test_an_undetermined_track_without_any_clue_says_the_language_is_unknown() -> None:
    """Единственная дорожка с тегом ``und`` и без улик в имени: язык честно неизвестен.

    Замер на тысяче запросов: 16 играбельных релизов держали ровно одну дорожку ``und``,
    и показ про язык озвучки молчал. Молчать нельзя, но и выдавать неизвестное за русское
    (или за «оригинальный») — тоже: честная строка называет вещи как есть.
    """
    pool = [named("Movie (2019) WEB-DL 1080p", size_gb=8, seeders=100)]
    release = pool[0]

    assert (
        sound_note(_media("und"), 0, pool, release)
        == "язык дорожки неизвестен - раздача не назвала язык озвучки"
    )


def test_an_undetermined_track_is_called_russian_only_when_the_name_proves_it() -> None:
    """``und`` + русский маркер в имени раздачи — единственная улика, и по ней можно
    СКАЗАТЬ про русскую, назвав источник. Без улики за русскую её не выдаём.
    """
    proven = named("Кино / Movie (1999) WEB-DL 1080p | Дубляж", size_gb=8, seeders=100)
    assert proven.dubbed
    assert (
        sound_note(_media("und"), 0, [proven], proven)
        == "звук без метки языка - по имени релиза русская"
    )

    mute = named("Movie (2019) WEB-DL 1080p", size_gb=8, seeders=100)
    assert not mute.dubbed
    assert "русская" not in sound_note(_media("und"), 0, [mute], mute)


def test_a_bare_und_track_is_not_shown_to_the_human_as_the_word_und() -> None:
    """В подписи озвучки «und» человеку не место: код языка ему ничего не говорит.
    Без метки и заголовка дорожка называется по номеру, а язык — отдельной строкой.
    """
    assert AudioTrack(index=0, language="und").label == "дорожка 1"
    assert AudioTrack(index=0, language="und", title="Дубляж").label == "Дубляж"
    assert AudioTrack(index=0, language="rus").label == "rus"
