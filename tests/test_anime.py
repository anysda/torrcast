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
from typing import Any, cast

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

    assert plan.loose, "живого именного кандидата у картины нет - ворота открыты"
    assert plan.ranked[0] is full, "дефолт - единственная живая раздача, а не огрызок на 3 сида"
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

    assert not plan.loose, "живых именных кандидатов двое - открывать нечего"
    assert not is_candidate(mute, RUNTIME, 25.0), "молчаливая раздача кандидатом не стала"
    assert [plan.ranked[n - 1] for n in plan.candidates(args)] == [good, second]


def test_a_russian_release_waits_in_the_queue_tail_when_the_gate_shut_it_out() -> None:
    """🔴 TC-195. Вечер владельца: «Тачки» 2006 - очередь из одного релиза при пяти раздачах.

    Живая выдача «тачки» (замер 09.08.2026, четыре индексера): у картины пять раздач.
    Верх - названный ``1080p H.264`` 7.1 ГБ на 66 сид, и он единственный именной, поэтому
    ворота закрыты и очередь состояла ровно из него. Его рой промолчал, и показ ответил
    «раздач в выдаче 5, потрогали 1 - до остальных отбор не дошёл» - при двух нетронутых
    раздачах С ДУБЛЯЖОМ (4.4 ГБ на 3 и на 1 сид).

    Откат правки роняет тест: очередь снова становится ``[1]``.
    """
    top = named("Тачки / Cars (2006) BDRip 1080p [H.264]", size_gb=7.1, seeders=66)
    dub_big = named("Тачки / Cars (2006) [Дубляж, Многоголосый, Субтитры]", size_gb=4.4, seeders=3)
    dub_small = named("Тачки / Cars (2006) [Дубляж, Субтитры]", size_gb=4.4, seeders=1)
    picture = Picture(title="Тачки", year=2006, releases=[top, dub_big, dub_small])
    args = Args(query=["тачки"])

    plan = _plan_for(picture, args, Config())

    assert not plan.loose, "живой именной кандидат есть - ворота закрыты, и это правильно"
    queue = plan.candidates(args)
    assert queue[0] == 1, "голова очереди не сдвинулась: дефолт и время до картинки прежние"
    assert len(queue) == 3, "русские раздачи ждут в хвосте, а не выброшены из очереди"
    assert {plan.ranked[n - 1] for n in queue[1:]} == {dub_big, dub_small}


def test_the_queue_tail_takes_russian_only_and_not_any_silent_rip() -> None:
    """Хвост - про русскую дорожку, а не про «пустить всех»: англоязычный рип не зовём.

    Молчание про КАЧЕСТВО рассудит ffprobe, молчание про ЯЗЫК рассуживать нечем, и
    хвост, натащивший англорипов, подсунул бы человеку кино без перевода.
    """
    top = named("Кино / Movie (1999) BDRip 1080p | D", size_gb=8.0, seeders=200)
    mute = named("Кино / Movie (1999) Complete", size_gb=4.0, seeders=180)
    picture = Picture(title="Кино", year=1999, releases=[top, mute])
    args = Args(query=["кино"])

    plan = _plan_for(picture, args, Config())

    assert plan.candidates(args) == [1], "русской дорожки у молчуна нет - в хвост не идёт"


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
    assert game.quiet, "о качестве видео имя молчит - видео там нет"
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
        "по ступени старья мёртвый выигрывает - и до правки этого хватало, чтобы встать верхом"
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

    assert pack.anime and pack.quiet, "имя аниме о качестве молчит - тем и жив признак"
    assert 0.0 < bitrate_of(pack, tv) < SD_BITRATE, (
        "битрейт по прикидке и правда ниже порога SD - спор именно о том, что это значит"
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


#: Живое имя того самого класса: BD-ремукс аниме-сезона, 12 серий, 83 ГБ, 17 сидов.
#: Внутри серия на 23.9 минуты и 36.4 Мбит/с видео - вдвое выше прежней отбраковки.
TITAN_REMUX = (
    "Атака титанов (S3, часть 1) / Shingeki no Kyojin Season 3 [TV] [E12 of 12] "
    "[JAP+Sub] [2018, приключения, драма, сёнэн, BDRemux] [1080p]"
)
#: Полнометражное аниме тем же ремуксом: 30 ГБ, и прикидка по имени уже видит тяжесть.
TITAN_MOVIE = (
    "Атака Титанов: Хроника / Shingeki no Kyojin: Chronicle [Movie] [JAP+Sub] "
    "[2020, приключения, драма, BDRemux] [1080p]"
)


def _prep(name: str, *, video_bps: float, height: int, size_gb: float, dur: float) -> object:
    """Прочитанный ffprobe релиз: ровно то, чем судит отбор после похода в рой."""
    from torrcast.cli import _Prep
    from torrcast.stream import Media, TorrFile

    prep = _Prep(number=1, release=named(name, size_gb=size_gb, seeders=17))
    prep.video = TorrFile(0, "anime.mkv", int(size_gb * GB))
    prep.media = Media(duration=dur, video="h264", video_bps=video_bps, height=height)
    return prep


def _bench() -> Any:
    """Отбор без раздач: TorrServer тут ни о чём не спрашивают."""
    from torrcast.cli import _Bench

    class _Nothing:
        def drop(self, torrent_hash: str) -> None:
            """Раздач в этих тестах нет - забывать нечего."""

    return _Bench(cast(Any, _Nothing()))


def test_an_anime_bd_remux_plays_by_a_whole_file_recode_instead_of_being_refused() -> None:
    """Ремукс на 36 Мбит/с - не отказ: его тянет сплошной перекод по файлу.

    Замер на 4 vCPU по этой самой раздаче: перекод ultrafast в 9 Мбит/с идёт 3.4x
    реального времени, чтение раздачи из роя - 47.7 МБ/с против нужных 4.7 МБ/с,
    самый тяжёлый сегмент 13.2 МБ при потолке 16. Прежний потолок отбраковки (25)
    ронял такой релиз после ffprobe, и у аниме это значило «показа нет»: BD-ремукс
    там сплошь и рядом единственное, что нашлось.
    """
    config = Config()
    prep = _prep(TITAN_REMUX, video_bps=36_420_000.0, height=1080, size_gb=6.8, dur=1434.0)
    bench = _bench()

    assert (
        bench._trouble(
            prep,
            pinned=False,
            warn_mbit=config.bitrate_recode_mbit,
            recode=True,
            hard_mbit=config.bitrate_hard_mbit,
        )
        == ""
    ), "1080p-ремукс на 36 Мбит/с обязан играть"
    assert (
        bench._trouble(prep, pinned=False, warn_mbit=config.bitrate_hard_mbit, recode=True)
        == "слишком тяжёлый для приёмника, ~36 Мбит/с"
    ), "прежним потолком он же отбраковывался - и строка отказа называет причину"


def test_a_whole_file_recode_is_chosen_by_weight_not_only_by_codec() -> None:
    """Сплошной перекод берётся и на h264 - когда тяжёл каждый кусок.

    Посегментный кодировщик на таком файле выродился бы в сотню коротких ffmpeg подряд;
    один длинный прогон дешевле и не даёт смешанного потока.
    """
    from torrcast.cli import _encode_all

    config = Config()

    whole = _encode_all(config, "h264", 36.4)
    assert whole is not None and whole.preset == "ultrafast"
    assert whole.mbit == config.recode_mbit, "цель - планка приёмника, а не битрейт источника"
    assert _encode_all(config, "h264", 17.8) is None, "честный тяжёлый 1080p идёт как раньше"
    assert _encode_all(replace(config, recode=False), "h264", 36.4) is None


def test_ten_bit_h264_goes_through_a_whole_file_recode_like_hevc() -> None:
    """🔴 Hi10P - не «обычный h264»: приёмник его не декодирует, значит перекод целиком.

    Замер на живом Q70D (TC-164, «Death Note» BDRip 1080p, 6.5 Мбит/с, ``High 10`` /
    ``yuv420p10le``): копия доигрывала ~70 с буфера и вставала в вечную петлю
    «залип - LOAD - BUFFERING». Гейт смотрел только на имя кодека, а имя у Hi10P то же
    самое - ``h264``, - поэтому он и проходил как обычный.
    """
    from torrcast.cli import _encode_all

    config = Config()

    whole = _encode_all(config, "h264", 6.5, 10)
    assert whole is not None, "десятибитный H.264 обязан идти сплошным перекодом"
    assert whole.preset == "ultrafast"
    assert whole.mbit == config.recode_mbit, "6.5 × 2.5 выше планки - берём планку"
    assert _encode_all(config, "h264", 6.5, 8) is None, "восьмибитный уезжает копией"
    assert _encode_all(config, "h264", 6.5) is None, "глубину не спрашивали - прежний путь"
    assert _encode_all(replace(config, recode=False), "h264", 6.5, 10) is None

    # Вверх не перекодируем: лёгкому источнику - лёгкая цель, тем же правилом, что у HEVC.
    light = _encode_all(config, "h264", 1.3, 10)
    assert light is not None and light.mbit == pytest.approx(3.25)


def test_the_show_and_the_warmer_decide_the_recode_the_same_way() -> None:
    """🔴 Показ и прогрев обязаны решать одинаково - иначе прогретое ляжет не под тем ключом.

    Прогрев зовёт :func:`torrcast.cli._layout` с паспортом только что снятого ffprobe, показ -
    с тем, что лежит в записи состояния. Разойдись они, и ключ прогретого куска
    (:func:`torrcast.warm.warm_key`) не совпадёт с ключом, который спросит показ: грелось
    впустую, а на экран уехала бы смесь копии и перекода - ровно тот SPS, на котором
    приёмник встаёт.
    """
    from torrcast.cli import _encode_all
    from torrcast.state import Entry
    from torrcast.stream import Media

    config = Config()
    media = Media(1366.0, (), "h264", profile="High 10", pix_fmt="yuv420p10le")
    # Запись состояния несёт ровно то же, что паспорт: и кодек, и глубину.
    entry = Entry(
        title="Тетрадь смерти", magnet="magnet:?xt=1", codec=media.video or "", depth=media.depth
    )

    warmer = _encode_all(config, media.video or "", 6.5, media.depth)
    show = _encode_all(config, entry.codec, 6.5, entry.depth)
    assert warmer == show and show is not None, "одно решение на обе стороны"
    # А без глубины стороны расходятся - это и был дефект.
    assert _encode_all(config, entry.codec, 6.5) != show


def test_a_heavy_remux_never_outranks_a_light_release_that_plays_as_is() -> None:
    """Тяжёлое берётся, только если легче ничего нет: ремукс идёт последним из годных.

    Ступень стоит выше сидов нарочно. Сплошной перекод ремукса занимает процессор с
    первой секунды до титров и требует от роя ~4.7 МБ/с непрерывно, а релиз на
    8 Мбит/с уезжает копией и переживает просадку роя за счёт запаса.
    """
    remux = named(TITAN_MOVIE, size_gb=30.0, seeders=200)
    light = named(
        "Атака Титанов: Хроника / Shingeki no Kyojin: Chronicle [Movie] [RUS(int), JAP+Sub] "
        "[2020, приключения, драма, BDRip] [1080p]",
        size_gb=7.0,
        seeders=20,
    )
    picture = Picture(title="Атака Титанов: Хроника", year=2020, releases=[remux, light])
    args = Args(query=["атака титанов хроника"])

    assert bitrate_of(remux, RUNTIME) > Config().bitrate_hard_mbit
    plan = _plan_for(picture, args, Config())

    assert plan.ranked[0] is light, "лёгкий обязан быть дефолтом даже с меньшими сидами"
    assert plan.ranked[1] is remux, "но ремукс остаётся в очереди - им показ спасается"
    assert plan.candidates(args) == [1, 2], "оба годны, порядок решает тяжесть"


def test_a_4k_remux_stays_refused_because_a_whole_file_recode_does_not_keep_up() -> None:
    """4К-ремукс не спасает и сплошной перекод: замер снят на 1080p.

    У 2160p вчетверо больше пикселей, и на тех же ядрах перекод в реальное время не
    укладывается. Поэтому кадр выше 1080p судится прежним ``bitrate_hard_mbit`` - и по
    имени раздачи, и по паспорту ffprobe, если имя о разрешении промолчало.
    """
    config = Config()
    uhd = named(
        "Атака Титанов: Последняя атака / Attack on Titan - The Last Attack [Movie] "
        "[JAP+Sub] [2024, BDRemux] [2160p]",
        size_gb=30.0,
        seeders=6,
    )

    assert uhd.height > 1080
    assert not is_candidate(
        uhd, RUNTIME, config.bitrate_recode_mbit, hard_mbit=config.bitrate_hard_mbit
    ), "4К на 33 Мбит/с не берём: перекодировать его в реальное время нечем"

    mute = _prep(TITAN_MOVIE, video_bps=33_000_000.0, height=2160, size_gb=30.0, dur=7200.0)
    assert (
        _bench()._trouble(
            mute,
            pinned=False,
            warn_mbit=config.bitrate_recode_mbit,
            recode=True,
            hard_mbit=config.bitrate_hard_mbit,
        )
        == "слишком тяжёлый для приёмника, ~33 Мбит/с"
    ), "молчаливое имя ловится паспортом"


def test_the_recode_line_names_the_weight_and_the_reason() -> None:
    """Одна честная строка: тяжесть названа вслух и числом, а не подменена молчком."""
    from torrcast.stream import recode_note

    assert recode_note("h264", 36.4) == (
        "видео h264 36 Мбит/с - тяжело приёмнику, перекодирую целиком"
    )
    assert recode_note("hevc") == "видео hevc - перекодирую на ходу целиком"


#: Живая выдача «Gintama s1e1»: 162 раздачи в каталоге, первая серия - ровно в двух.
#: Единственный её живой носитель - HEVC, и до ворот отбора он не доживал.
GINTAMA_HEVC = "Гинтама / Gintama TV-1 [01-201] (2006) BDRip-HEVC  720p | L1"
GINTAMA_DEAD = (
    "Гинтама / Gintama TV [01-252] + OVA + Movies  + BONUS (2006-2012) DVDRip-AVC, HDTV-AVC"
)


def test_the_only_live_carrier_of_the_episode_is_hevc_and_it_finally_plays() -> None:
    """«Гинтама»: первая серия жива ровно в HEVC - и очередь обязана до неё дойти.

    Замер по кэшу живой выдачи. Каталог - 162 раздачи, первая серия по именам есть в
    двух: ``DVDRip-AVC`` на 99 ГБ с НУЛЁМ сидов и ``BDRip-HEVC 720p`` с четырьмя.
    Ворота отбора HEVC не пускали вовсе, кандидатом оставалась мёртвая раздача, и показа
    не было. При этом играть HEVC тракт умеет ровно так же, как десятибитный H.264, -
    сплошным перекодом по файлу.
    """
    hevc = named(GINTAMA_HEVC, size_gb=30.2, seeders=4)
    dead = named(GINTAMA_DEAD, size_gb=99.2, seeders=0)
    picture = Picture(title="Гинтама", year=2006, kind="tv", releases=[dead, hevc])
    args = Args(query=["gintama", "s1e1"])

    plan = _plan_for(picture, args, Config())

    assert hevc.is_hevc and not hevc.prime, "именем он признался, и ворота держали его снаружи"
    assert plan.last_resort, "живого кандидата с первой серией нет ни одного"
    assert plan.ranked[0] is hevc, "живой HEVC выше мёртвого AVC: ноль сидов - это не показ"
    assert [plan.ranked[n - 1] for n in plan.candidates(args)] == [hevc, dead]


def test_a_live_ordinary_release_keeps_hevc_out_of_the_queue_as_before() -> None:
    """Обычный случай не двигается ни на строку: при живом H.264 HEVC не кандидат.

    Цена сплошного перекода замерена и никуда не делась: процессор занят от первой
    секунды до титров, старт медленнее (8 с против 5). Поэтому HEVC - последняя надежда,
    а не равноправный кандидат.
    """
    good = named("Аниме / Anime [TV] [01-12 из 12] (2019) BDRip 1080p | D", size_gb=8.0, seeders=40)
    hevc = named(
        "Аниме / Anime [TV] [01-12 из 12] (2019) BDRip-HEVC 1080p | L1", size_gb=6.0, seeders=300
    )
    picture = Picture(title="Аниме", year=2019, kind="tv", releases=[hevc, good])
    args = Args(query=["аниме", "s1e1"])

    plan = _plan_for(picture, args, Config())

    assert not plan.last_resort, "живой обычный кандидат есть - надеяться не на что"
    assert plan.ranked[0] is good, "HEVC не обгоняет живой H.264 даже семикратным перевесом сидов"
    assert [plan.ranked[n - 1] for n in plan.candidates(args)] == [good]


def test_the_last_hope_does_not_open_for_a_4k_hevc_because_the_recode_never_keeps_up() -> None:
    """2160p сплошным перекодом не идёт: телевизор показа не начинает вовсе.

    Скорость замерена на 1080p - 4.04x реального времени на 4 vCPU; у 2160p вчетверо
    больше пикселей. Пускать такой релиз в очередь значило бы обещать показ, которого не
    будет, поэтому здесь нужен честный отказ, а не вечная петля воскрешений.
    """
    from torrcast.cli import hevc_hope

    uhd = named("Аниме / Anime [TV] [01-12 из 12] (2019) BDRip-HEVC 2160p", size_gb=20.0, seeders=9)
    hd = named("Аниме / Anime [TV] [01-12 из 12] (2019) BDRip-HEVC 1080p", size_gb=8.0, seeders=9)

    assert uhd.height > 1080 and hd.height == 1080
    assert not hevc_hope(uhd, True), "4К не спасает и последняя надежда"
    assert hevc_hope(hd, True)
    assert not hevc_hope(hd, False), "ворота закрыты - признак не срабатывает вовсе"
    assert not is_candidate(uhd, RUNTIME, 40.0, hard_mbit=25.0, last=True)
    assert is_candidate(hd, RUNTIME, 40.0, hard_mbit=25.0, last=True)


def test_a_light_4k_hevc_is_refused_by_the_passport_not_looped_forever() -> None:
    """Лёгкое 4К проходит потолок веса - и всё равно отказ: приёмнику не по кадру.

    Потолок ``bitrate_hard_mbit`` ловит 4К-ремуксы тяжестью, а 2160p HEVC на 12 Мбит/с
    для него лёгкий. Спасает не вес: спасает кадр, и считать его надо по паспорту
    ffprobe, а не по имени раздачи (:attr:`torrcast.profile.Profile.recode_frame`).
    """
    config = Config()
    light = cast(
        Any, _prep(GINTAMA_HEVC, video_bps=12_000_000.0, height=2160, size_gb=20.0, dur=7200.0)
    )
    light.media = replace(cast(Media, light.media), video="hevc")
    assert light.media.recoded_whole, "HEVC уезжает сплошным перекодом - о нём и речь"

    assert (
        _bench()._trouble(
            light,
            pinned=False,
            warn_mbit=config.bitrate_recode_mbit,
            recode=True,
            hard_mbit=config.bitrate_hard_mbit,
        )
        == "hevc 2160p - приёмник не берёт такой кадр в перекодированном виде"
    ), "отказ назван своим именем, и очередь идёт дальше"


def test_the_heavy_path_says_so_out_loud_in_one_line() -> None:
    """Молчаливых подмен нет: взяли HEVC последней надеждой - сказали одной строкой."""
    from torrcast.cli import last_hope_note

    hevc = named(GINTAMA_HEVC, size_gb=30.2, seeders=4)
    dead = named(GINTAMA_DEAD, size_gb=99.2, seeders=0)
    picture = Picture(title="Гинтама", year=2006, kind="tv", releases=[dead, hevc])
    plan = _plan_for(picture, Args(query=["gintama", "s1e1"]), Config())

    assert last_hope_note(plan, hevc) == (
        "живой раздачи серии s1e1 без HEVC нет - беру HEVC последней надеждой"
    )
    assert last_hope_note(plan, dead) == "", "обычный релиз про надежду молчит"


def test_the_last_hope_asks_the_receiver_profile_not_a_module_constant() -> None:
    """«Тяжёлый ли HEVC» — вопрос ПРОФИЛЯ приёмника, и задан он там же, где всегда.

    Пороги приёмника живут в :mod:`torrcast.profile`, и набор кодеков на сплошной перекод
    у профилей может разойтись. Последняя надежда стоит ровно на том, что HEVC — путь
    дорогой: процессор занят до титров, старт медленнее. Приёмнику, который берёт HEVC
    копией, ничего этого не грозит, и ворота ему не нужны.

    🔴 Оба живых профиля сегодня перекодируют HEVC (у приставки набор оставлен прежним
    до замера через наш mpegts), поэтому ступень работает на обоих одинаково. Приёмник,
    который HEVC копирует, остаётся БЕЗ такой раздачи вовсе: держит её не эта ступень, а
    ворота (:attr:`~torrcast.parse.Release.prime`), и ослаблять их — отдельная карточка.
    """
    from torrcast.profile import ANDROID_TV, CAUTIOUS

    hevc = named(GINTAMA_HEVC, size_gb=30.2, seeders=4)
    dead = named(GINTAMA_DEAD, size_gb=99.2, seeders=0)
    picture = Picture(title="Гинтама", year=2006, kind="tv", releases=[dead, hevc])
    args = Args(query=["gintama", "s1e1"])

    for profile in (CAUTIOUS, ANDROID_TV):
        plan = _plan_for(picture, args, Config(), profile)
        assert plan.last_resort, f"{profile.key}: HEVC он перекодирует целиком - надежда нужна"
        assert plan.ranked[0] is hevc

    native = replace(
        CAUTIOUS, key="native", recode_codecs=frozenset(), copy_codecs=frozenset({"h264", "hevc"})
    )
    plan = _plan_for(picture, args, Config(), native)
    assert not plan.last_resort, "берёт HEVC копией - тяжёлого пути нет, и ворота не про него"
