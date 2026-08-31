"""Отбор релиза у аниме: ворота для молчаливых имён и русская озвучка как условие показа.

Аниме — худший жанр замера покрытия, и обе причины видны прямо в именах раздач.
Первая: у аниме имя сплошь не называет ни разрешения, ни кодека, ни HD-источника, и
ворота отбора оставляют картину вообще без живых кандидатов. Вторая: японская дорожка
без перевода — это не «звук похуже», а несмотренный тайтл, и русский дубляж у аниме
часто лежит ОТДЕЛЬНОЙ раздачей, которая по сидам проигрывает вчистую.

🔴 TC-178. Вторая причина перестала быть предпочтением: «включилось» значит «включилось
с русской озвучкой». Релиз, у которого русской дорожки не оказалось, годным не считается,
и отбор идёт дальше по очереди; честная строка достаётся только той картине, у которой
русской нет ни у кого.

Имена здесь взяты с живой выдачи Prowlarr (Knaben, RuTor, Nyaa) и не причёсаны:
именно их своеобразие ворота и не переваривали.
"""

from __future__ import annotations

import io
from dataclasses import replace
from typing import Any, cast

import pytest

from tests.articles import UTENA, page
from tests.fakes.media_probe import FakeMediaProbe
from tests.test_cli import _FakeTorrServer, _resolve, rel
from torrcast.adapters.console.console.progress import Progress
from torrcast.adapters.filesystem.trace_journal.records import records
from torrcast.adapters.filesystem.trace_journal.shutdown import shutdown
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.digest.digest import digest
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.read_origin import read_origin
from torrcast.domain.media import Media
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.picture import Picture
from torrcast.domain.rank_settings import SD_BITRATE
from torrcast.domain.raw_result import RawResult
from torrcast.domain.release import Release
from torrcast.domain.runtime_guess import RUNTIME_GUESS
from torrcast.runtime.native_picture import native_picture
from torrcast.usecases.rank.bitrate_of import bitrate_of
from torrcast.usecases.rank.drop_reason import drop_reason
from torrcast.usecases.rank.gate_open import gate_open
from torrcast.usecases.rank.is_candidate import is_candidate
from torrcast.usecases.rank.is_dated import is_dated
from torrcast.usecases.rank.is_dead import is_dead
from torrcast.usecases.rank.rank_releases import rank_releases
from torrcast.usecases.rank.sound_note import sound_note
from torrcast.usecases.reinforce.plan_for import plan_for
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench

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

    plan = plan_for(picture, args, Config())

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

    plan = plan_for(picture, args, Config())

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

    plan = plan_for(picture, args, Config())

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

    plan = plan_for(picture, args, Config())

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
    rate = bitrate_of(pack, tv)
    assert rate is not None and 0.0 < rate < SD_BITRATE, (
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


def test_an_anime_mirrored_by_a_general_indexer_keeps_its_genre_bitrate() -> None:
    """Тот же признак, но раздача приехала ОТ ДВОИХ: с Nyaa и с общего индексера.

    Склейка оставляет одну строку, и её ``indexer`` - это индексер победившего ИМЕНИ, то
    есть в паре «Knaben против Nyaa.si» всегда алфавитно первый. Пока жанр читался у
    победителя, аниме с Nyaa теряло признак ровно тогда, когда его кто-то зеркалит, - и
    честный жанровый битрейт (замер: 170 раздач на 6 аниме-запросах) получал метку
    «старьё» за то, что рисованная картинка жмётся лучше живой съёмки.
    """
    quiet = "Anime Series [12 of 12] (2020) BDRip | JAP+Sub"
    mirror = (
        RawResult(quiet, "b" * 40, int(2.0 * GB), 40, "Knaben"),
        RawResult(quiet, "b" * 40, int(2.0 * GB), 31, "Nyaa.si"),
    )
    (release,) = to_releases(merge(*([item] for item in mirror)))
    tv = RUNTIME_GUESS["tv"]

    assert release.anime, "аниме-индексер в группе - это аниме, кто бы ни выиграл имя"
    rate = bitrate_of(release, tv)
    assert rate is not None and 0.0 < rate < SD_BITRATE, "спор идёт именно о низком битрейте"
    assert not is_dated(release, tv)


def test_the_sound_step_never_outranks_honest_quality() -> None:
    """Русский .avi вместо честного 1080p — не размен, а откат: ступень звука ниже старья."""
    old = named("Аниме / Anime (2002) DVDRip XviD | Дубляж", size_gb=1.4, seeders=100)
    good = named("Аниме / Anime (2002) WEB-DL 1080p", size_gb=8.0, seeders=100)

    assert rank_releases([old, good], RUNTIME, 25.0)[0] is good


@pytest.mark.parametrize(
    "name,promised",
    [
        ("Аниме [TV] [12 of 12] [RUS(int), JAP+Sub] [2020, WEBRip] [1080p]", True),
        ("Аниме [TV] [12 of 12] [RUS(ext), ENG, JAP+Sub] [2020, DVDRip]", False),
        ("Аниме [TV] [12 of 12] [RUS(int), RUS(ext), JAP+Sub] [2020, WEBRip]", True),
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

    Четыре ловушки живой выдачи разом: «Rus Sub» — это титры; «English Dub» и «Multi-Dub» —
    дубляж, только не тот; «| Shiza Project» и «AniLiberty» — единственный маркер дорожки
    во всём имени, и без него аниме-раздача выглядит немой; а «RUS(ext)» — это обещание
    дорожки ОТДЕЛЬНЫМ ФАЙЛОМ, которую показ не играет (🔴 TC-191).
    """
    assert parse_release_name(name).dubbed is promised


def test_a_russian_track_in_a_separate_file_is_not_a_russian_soundtrack() -> None:
    """🔴 TC-191. ``RUS(ext)`` — русская дорожка ОТДЕЛЬНЫМ ФАЙЛОМ, и «включилось» это не.

    Ровно этим «Наруто» и уезжал по-японски: пак на 91 сид носит в имени «[RUS(ext), ENG,
    JAP+Sub]», отбор читал метку как обещание русского звука и до соседа с «[RUS(int)]»
    (3 сида) не доходил. Внутри mkv у пака японская дорожка, русская лежит рядом файлом,
    и подмешивать её показ не умеет.

    Признак при этом не теряется: он живёт отдельно и нужен честной строке — «перевод
    есть, но отдельным файлом» и «перевода нет вовсе» это два разных ответа.
    """
    apart = parse_release_name(NARUTO_FULL)
    inside = parse_release_name(
        "Наруто / Naruto [TV] [1-5 из 220] [RUS(int)] [2002, DVDRip] [1080p]"
    )

    assert apart.external_dub and not apart.dubbed, "обещана отдельным файлом - не наша дорожка"
    assert inside.dubbed and not inside.external_dub, "внутри контейнера - наша"


def test_ext_slash_int_in_one_marker_still_promises_a_playable_track() -> None:
    """🔴 TC-301. ``RUS(ext/int)`` - это ОБЕЩАНИЕ внутренней дорожки, а не только внешней.

    Живой случай, ради которого написано: «Врата Штейна … [RUS(ext/int), JAP+Sub] …
    [1080p]» держит 86 сидов, тогда как все остальные русские раздачи картины стоят на
    нуле и на единице. Пока скобки съедались целиком, эта раздача не обещала русского
    вовсе - и не попадала ни в хвост очереди, ни в вопрос соседу, а показ уезжал
    по-японски со строкой «в каталоге перевод есть».

    Разница с ``RUS(ext)`` рядом принципиальна и обязана уцелеть: там дорожка правда
    только отдельным файлом, и играть её показ не умеет.
    """
    both = parse_release_name(
        "Врата Штейна / Steins;Gate [TV+Special] [E24+2 of 24+2] [RUS(ext/int), JAP+Sub] "
        "[2011, триллер, фантастика, драма, BDRip] [1080p]"
    )
    apart = parse_release_name("Аниме [TV] [12 of 12] [RUS(ext), ENG, JAP+Sub] [2020, WEBRip]")

    assert both.dubbed, "часть серий несёт русскую дорожку внутри контейнера"
    assert not both.external_dub, "«перевод лежит отдельным файлом» - тут это уже неправда"
    assert apart.external_dub and not apart.dubbed, "чистый ext по-прежнему не наша дорожка"


def test_a_dub_listing_foreign_languages_promises_nothing_russian() -> None:
    """🔴 TC-301. «[Dub - Japanese , English , Arabic]» - перечень ЧУЖИХ дорожек.

    Живой случай: «[TekkenQ8] Spirited Away … [Dub - Japanese , English , Arabic]» на 64
    сида вставал верхом отбора по звуковой ступени, обгоняя соседа со 110 сидами, и уверял
    человека строкой, что перевод у картины есть. Русского в нём нет ни одной дорожки.

    Обратный порядок читается только по названию языка: «Dub-Nickelodeon» - это студия
    нашего дубляжа, и трогать её нельзя.
    """
    foreign = parse_release_name(
        "[TekkenQ8] Spirited Away (2001) [BD 1080p] [Dub - Japanese , English , Arabic] "
        "[Sub - English , Arabic]"
    )
    studio = parse_release_name(
        "Аватар: Легенда о Корре / The Legend of Korra [01x01-12] (2012) WEB-DL | Dub-Nickelodeon"
    )

    assert not foreign.dubbed, "перечислены японский, английский и арабский - нашего нет"
    assert studio.dubbed, "после «Dub» стоит студия, а не чужой язык"


def test_an_internal_russian_track_outranks_an_external_one() -> None:
    """🔴 TC-191. ``RUS(int)`` встаёт над ``RUS(ext)`` ДО всякого ffprobe: метку читает ранжир.

    Обе раздачи тут живые и равные по сидам, и до правки порядок между ними решал размер:
    метка про звук в ранжир не попадала вовсе.
    """
    apart = named(
        "Аниме / Anime [TV] [12 of 12] [RUS(ext), ENG, JAP+Sub] [2020, WEB-DL] [1080p]",
        size_gb=20.0,
        seeders=40,
    )
    inside = named(
        "Аниме / Anime [TV] [12 of 12] [RUS(int), JAP+Sub] [2020, WEB-DL] [1080p]",
        size_gb=8.0,
        seeders=40,
    )

    assert rank_releases([apart, inside], RUNTIME, 25.0)[0] is inside


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

    assert sound_note(_media("jpn"), 0, pool) == ("Japanese sound only, no dub in the catalog")


def test_when_the_catalogue_may_have_a_dub_the_line_does_not_promise_it() -> None:
    """Перевод в выдаче есть, а в ЭТОМ релизе его не оказалось. Тогда строка обязана
    назвать и запасной ход: выбрать раздачу руками.
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

    assert note == "Japanese sound only - the catalog may hold a dub in another release"
    assert "--release N" not in note


def test_an_unplayable_dub_is_not_offered_as_a_way_out() -> None:
    """Отсев показа передаёт строке только очередь; тяжёлого дубляжа в ней уже нет."""
    selected = named("Anime [JAP] WEB-DL 1080p", size_gb=2.0, seeders=20)

    note = sound_note(_media("jpn"), 0, [], selected)

    assert note == "Japanese sound only, no dub in the catalog"
    assert "--release N" not in note


def test_a_dub_that_exists_only_as_a_separate_file_is_named_as_such() -> None:
    """🔴 TC-191. Весь перевод в каталоге - только ``RUS(ext)``, отдельным файлом.

    Отправлять человека выбирать раздачу руками тут нечестно: выбирать не из чего, все
    кандидаты приведут к тому же японскому звуку. Строка называет вещи как есть.
    """
    pool = [named(NARUTO_FULL, size_gb=157.3, seeders=91)]

    note = sound_note(_media("jpn", "eng"), 0, pool)

    assert note == ("Japanese sound only - the catalog has a dub, but it sits in a separate file")
    assert "--release N" not in note, "выбирать руками нечего - совет был бы враньём"


def test_a_separate_russian_audio_file_is_read_from_the_torrent_contents() -> None:
    """Имя релиза молчит, но уже полученный список файлов прямо называет русский звук."""
    from torrcast.domain.torr_file import TorrFile

    release = named("Anime BDRip 720p | L2, L1", size_gb=8, seeders=20)
    files = [
        TorrFile(0, "Anime/S01E01.mkv", 2 * GB),
        TorrFile(1, "Anime/Audio/S01E01.RUS.mka", 100 * 1024**2),
    ]

    assert not release.external_dub, "имя релиза симптом не выдаёт"
    assert sound_note(_media("jpn"), 0, [release], release, files) == (
        "Japanese sound only - the catalog has a dub, but it sits in a separate file"
    )


def test_a_release_with_a_russian_track_says_nothing_extra() -> None:
    """Русская дорожка на месте — предупреждать не о чем, лишних строк не печатаем."""
    pool = [named("Кино / Movie (1999) WEB-DL 1080p | D", size_gb=8, seeders=100)]

    assert sound_note(_media("jpn", "rus"), 1, pool) == ""


def test_the_line_names_the_language_it_actually_hears() -> None:
    """Язык берётся из дорожки, а не додумывается: у французского кино японскому
    звуку взяться неоткуда, а незнакомый код честнее назвать «оригинальным».
    """
    pool = [named("Кино / Movie (1999) WEB-DL 1080p", size_gb=8, seeders=100)]

    assert sound_note(_media("fra"), 0, pool) == "French sound only, no dub in the catalog"
    assert sound_note(_media("swe"), 0, pool) == "original sound only, no dub in the catalog"


def test_an_undetermined_track_without_any_clue_says_the_language_is_unknown() -> None:
    """Единственная дорожка с тегом ``und`` и без улик в имени: язык честно неизвестен.

    Замер на тысяче запросов: 16 играбельных релизов держали ровно одну дорожку ``und``,
    и показ про язык озвучки молчал. Молчать нельзя, но и выдавать неизвестное за русское
    (или за «оригинальный») — тоже: честная строка называет вещи как есть.
    """
    pool = [named("Movie (2019) WEB-DL 1080p", size_gb=8, seeders=100)]
    release = pool[0]

    assert sound_note(_media("und"), 0, pool, release) == (
        "track language unknown - the release did not name the voice language"
    )


def test_an_undetermined_track_is_called_russian_only_when_the_name_proves_it() -> None:
    """``und`` + русский маркер в имени раздачи — единственная улика, и по ней можно
    СКАЗАТЬ про русскую, назвав источник. Без улики за русскую её не выдаём.
    """
    proven = named("Кино / Movie (1999) WEB-DL 1080p | Дубляж", size_gb=8, seeders=100)
    assert proven.dubbed
    assert sound_note(_media("und"), 0, [proven], proven) == (
        "sound has no language tag - the release name says Russian"
    )

    mute = named("Movie (2019) WEB-DL 1080p", size_gb=8, seeders=100)
    assert not mute.dubbed
    assert sound_note(_media("und"), 0, [mute], mute) == (
        "track language unknown - the release did not name the voice language"
    )


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
    from torrcast.domain.media import Media
    from torrcast.domain.torr_file import TorrFile
    from torrcast.usecases.select._prep import _Prep

    prep = _Prep(number=1, release=named(name, size_gb=size_gb, seeders=17))
    prep.video = TorrFile(0, "anime.mkv", int(size_gb * GB))
    prep.media = Media(duration=dur, video="h264", video_bps=video_bps, height=height)
    return prep


def _bench() -> Any:
    """Отбор без раздач: TorrServer тут ни о чём не спрашивают."""
    from torrcast.usecases.select_bench.bench import Bench

    class _Nothing:
        def drop(self, torrent_hash: str) -> bool:
            """Раздач в этих тестах нет - забывать нечего."""
            return True

    return Bench(cast(Any, _Nothing()))


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
        == "too heavy for the receiver, ~36 Mbit/s"
    ), "прежним потолком он же отбраковывался - и строка отказа называет причину"


def test_a_whole_file_recode_is_chosen_by_weight_not_only_by_codec() -> None:
    """Сплошной перекод берётся и на h264 - когда тяжёл каждый кусок.

    Посегментный кодировщик на таком файле выродился бы в сотню коротких ffmpeg подряд;
    один длинный прогон дешевле и не даёт смешанного потока.
    """
    from torrcast.usecases.playback._encode_all import _encode_all

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
    from torrcast.usecases.playback._encode_all import _encode_all

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

    Прогрев зовёт :func:`torrcast.usecases.playback.layout.layout` с паспортом только что снятого
    ffprobe, показ - с тем, что лежит в записи состояния. Разойдись они, и ключ прогретого куска
    (:func:`torrcast.usecases.warm.warm_key`) не совпадёт с ключом, который спросит показ: грелось
    впустую, а на экран уехала бы смесь копии и перекода - ровно тот SPS, на котором приёмник
    встаёт.
    """
    from torrcast.domain.entry import Entry
    from torrcast.domain.media import Media
    from torrcast.usecases.playback._encode_all import _encode_all

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

    heavy = bitrate_of(remux, RUNTIME)
    assert heavy is not None and heavy > Config().bitrate_hard_mbit
    plan = plan_for(picture, args, Config())

    assert plan.ranked[0] is light, "лёгкий обязан быть дефолтом даже с меньшими сидами"
    assert plan.ranked[1] is remux, "но ремукс остаётся в очереди - им показ спасается"
    assert plan.candidates(args) == [1, 2], "оба годны, порядок решает тяжесть"


def test_a_4k_remux_stays_refused_because_a_whole_file_recode_does_not_keep_up() -> None:
    """4К-ремукс не спасает и сплошной перекод: замер снят на 1080p.

    У 2160p вчетверо больше пикселей, и на тех же ядрах перекод в реальное время не
    укладывается. Поэтому кадр выше 1080p судится прежним ``bitrate_hard_mbit`` - и по
    имени раздачи, и по паспорту ffprobe, если имя о разрешении промолчало. И отказ
    называет честную причину: ограничение - скорость НАШЕЙ машины, а не приёмник.
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
        == "recoding this frame is beyond this machine, ~33 Mbit/s"
    ), "молчаливое имя ловится паспортом, и отказ винит нашу машину, а не приёмник"


def test_the_recode_line_names_the_weight_and_the_reason() -> None:
    """Одна честная строка: тяжесть названа вслух и числом, а не подменена молчком."""
    from torrcast.domain.recode_note import recode_note

    assert recode_note("h264", 36.4) == (
        "video h264 36 Mbit/s - heavy for the receiver, recoding it whole"
    )
    assert recode_note("hevc") == "video hevc - recoding it whole on the fly"


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

    plan = plan_for(picture, args, Config())

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

    plan = plan_for(picture, args, Config())

    assert not plan.last_resort, "живой обычный кандидат есть - надеяться не на что"
    assert plan.ranked[0] is good, "HEVC не обгоняет живой H.264 даже семикратным перевесом сидов"
    assert [plan.ranked[n - 1] for n in plan.candidates(args)] == [good]


def test_a_4k_release_never_lifts_over_a_live_1080p_however_many_seeders_it_has() -> None:
    """🔴 TC-221: 2160p отбраковывается в пользу ЖИВОГО 1080p, а не берётся за чёткость.

    Решение владельца ровно такое, и держит его порядок, а не запрет: 4К играется только
    сплошным перекодом со скейлом вниз - копией приёмник его не берёт (TC-157), - то есть
    по цене это тот же класс, что BD-ремукс. Ступень «играется только сплошным перекодом»
    стоит выше живости и выше качества, поэтому девятикратный перевес сидов 4К не спасает.
    """
    from torrcast.usecases.rank.needs_whole_recode import needs_whole_recode
    from torrcast.usecases.rank.rank_releases import rank_releases

    uhd = named("Аниме / Anime [TV] [01-12 из 12] (2019) BDRip-HEVC 2160p", size_gb=20.0, seeders=9)
    hd = named("Аниме / Anime [TV] [01-12 из 12] (2019) BDRip-HEVC 1080p", size_gb=8.0, seeders=1)

    assert uhd.height > 1080 and hd.height == 1080
    assert needs_whole_recode(uhd, RUNTIME, 25.0), "4К - это сплошной перекод, и цена та же"
    assert not needs_whole_recode(hd, RUNTIME, 25.0)
    order = rank_releases([uhd, hd], RUNTIME, 40.0, hard_mbit=25.0, last=True)
    assert order[0] is hd, "живой 1080p с одним сидом обходит 4К с девятью"


def test_the_last_hope_opens_for_a_4k_hevc_because_it_is_scaled_down_now() -> None:
    """🔴 TC-222: 1080p у картины нет вовсе - 4К пускается в очередь, а не отбрасывается.

    Прежний запрет стоял на арифметике «перекод 4К не успевает», и замер TC-157 её
    перевернул: со скейлом до 1080p тот же ultrafast идёт 1.53x реального времени против
    1.03x без скейла. Отказывать тут значило бы отказывать в единственном носителе
    картины ради потолка, которого больше нет.
    """
    from torrcast.usecases.rank.hevc_hope import hevc_hope

    uhd = named("Аниме / Anime [TV] [01-12 из 12] (2019) BDRip-HEVC 2160p", size_gb=20.0, seeders=9)
    hd = named("Аниме / Anime [TV] [01-12 из 12] (2019) BDRip-HEVC 1080p", size_gb=8.0, seeders=1)

    assert hevc_hope(uhd, True), "последняя надежда - и 4К в ней участвует"
    assert hevc_hope(hd, True)
    assert not hevc_hope(hd, False), "ворота закрыты - признак не срабатывает вовсе"
    assert is_candidate(uhd, RUNTIME, 40.0, hard_mbit=25.0, last=True)


def test_a_light_4k_release_is_taken_and_scaled_down_instead_of_being_refused() -> None:
    """🔴 TC-222: лёгкое 4К больше не отказ - оно едет сплошным перекодом вниз до 1080p.

    Потолок ``bitrate_hard_mbit`` ловит 4К-ремуксы тяжестью, а 2160p на 12 Мбит/с для него
    лёгкий, и раньше такой релиз получал отказ по кадру. Замер TC-157 это правило снял:
    ужатый до 1080p перекод идёт быстрее неужатого. Отказ остаётся ровно там, где ужимать
    нечем, - при выключенном перекодировании, и назван он кадром, а не кодеком.
    """
    config = Config()
    light = cast(
        Any, _prep(GINTAMA_HEVC, video_bps=12_000_000.0, height=2160, size_gb=20.0, dur=7200.0)
    )
    light.media = replace(cast(Media, light.media), video="h264", pix_fmt="yuv420p")
    assert light.media.frame == 2160 and light.media.depth == 8
    assert light.media.recoded_whole, "копией 4К не уезжает даже в посильном кодеке (TC-221)"

    assert (
        _bench()._trouble(
            light,
            pinned=False,
            warn_mbit=config.bitrate_recode_mbit,
            recode=True,
            hard_mbit=config.bitrate_hard_mbit,
        )
        == ""
    ), "перекодирование включено - кадр ужмётся, и релиз годен"
    assert (
        _bench()._trouble(
            light,
            pinned=False,
            warn_mbit=config.bitrate_recode_mbit,
            recode=False,
            hard_mbit=config.bitrate_hard_mbit,
        )
        == "2160p - this frame reaches the receiver only through recoding"
    ), "ужимать нечем - честный отказ, и назван он кадром, а не кодеком"


def test_the_heavy_path_says_so_out_loud_in_one_line() -> None:
    """Молчаливых подмен нет: взяли HEVC последней надеждой - сказали одной строкой."""
    from torrcast.usecases.choice.last_hope_note import last_hope_note

    hevc = named(GINTAMA_HEVC, size_gb=30.2, seeders=4)
    dead = named(GINTAMA_DEAD, size_gb=99.2, seeders=0)
    picture = Picture(title="Гинтама", year=2006, kind="tv", releases=[dead, hevc])
    plan = plan_for(picture, Args(query=["gintama", "s1e1"]), Config())

    assert last_hope_note(plan, hevc) == phrase("choice.last_hope_episode", want="s1e1")
    assert last_hope_note(plan, dead) == "", "обычный релиз про надежду молчит"


def test_the_last_hope_asks_the_receiver_profile_not_a_module_constant() -> None:
    """«Тяжёлый ли HEVC» — вопрос ПРОФИЛЯ приёмника, и задан он там же, где всегда.

    Пороги приёмника живут в :mod:`torrcast.domain.profile`, и набор кодеков на сплошной перекод
    у профилей может разойтись. Последняя надежда стоит ровно на том, что HEVC — путь
    дорогой: процессор занят до титров, старт медленнее. Приёмнику, который берёт HEVC
    копией, ничего этого не грозит, и ворота ему не нужны.

    🔴 Оба живых профиля сегодня перекодируют HEVC (у приставки набор оставлен прежним
    до замера через наш mpegts), поэтому ступень работает на обоих одинаково. Приёмник,
    который HEVC копирует, остаётся БЕЗ такой раздачи вовсе: держит её не эта ступень, а
    ворота (:attr:`~torrcast.domain.release.Release.prime`), и ослаблять их — отдельная карточка.
    """
    from torrcast.domain.profile import ANDROID_TV, CAUTIOUS

    hevc = named(GINTAMA_HEVC, size_gb=30.2, seeders=4)
    dead = named(GINTAMA_DEAD, size_gb=99.2, seeders=0)
    picture = Picture(title="Гинтама", year=2006, kind="tv", releases=[dead, hevc])
    args = Args(query=["gintama", "s1e1"])

    cautious = plan_for(picture, args, Config(), CAUTIOUS)
    assert cautious.last_resort and cautious.ranked[0] is hevc

    android = plan_for(picture, args, Config(), ANDROID_TV)
    assert not android.last_resort, "CMAF-профиль берёт HEVC копией без тяжёлого пути"
    assert android.copy_hevc and android.ranked[0] is hevc

    native = replace(
        CAUTIOUS, key="native", recode_codecs=frozenset(), copy_codecs=frozenset({"h264", "hevc"})
    )
    plan = plan_for(picture, args, Config(), native)
    assert not plan.last_resort, "берёт HEVC копией - тяжёлого пути нет, и ворота не про него"
    assert plan.copy_hevc, "разрешение профиля доехало до обычных ворот"
    assert plan.ranked[0] is hevc, "живой HEVC собственного ресивера - обычный кандидат"
    assert plan.candidates(args)[0] == 1, "HEVC не потерялся между порядком и очередью"
    assert drop_reason(hevc, plan) == "", "счёт отсева не спорит с воротами"


def test_a_native_codec_does_not_weaken_the_quality_gate() -> None:
    """Профиль снимает только запрет кодека, но не потолок качества и веса."""
    from torrcast.domain.profile import CAUTIOUS

    native = replace(
        CAUTIOUS, key="native", recode_codecs=frozenset(), copy_codecs=frozenset({"h264", "hevc"})
    )
    heavy = named(GINTAMA_HEVC, size_gb=2000.0, seeders=40)
    playable = named(GINTAMA_HEVC, size_gb=8.0, seeders=4)
    picture = Picture(title="Гинтама", year=2006, kind="tv", releases=[heavy, playable])
    args = Args(query=["gintama", "s1e1"])

    plan = plan_for(picture, args, Config(recode=False), native)
    assert plan.copy_hevc, "HEVC разрешён именно профилем собственного ресивера"
    assert plan.ranked[0] is playable, "профиль не поднимает HEVC выше потолка битрейта"
    assert heavy not in [plan.ranked[n - 1] for n in plan.candidates(args)], (
        "тяжёлый релиз остаётся снаружи"
    )


# --- 🔴 TC-178: русская дорожка как условие ГОДНОСТИ релиза ---------------------------


def _tracks(ranked: list[Release], *langs: str) -> FakeMediaProbe:
    """ffprobe стенда: по языку дорожки на релиз, считая от верха. Отдаёт сам фейк -
    по его :attr:`~tests.fakes.media_probe.FakeMediaProbe.asked` видно, сколько раз мы
    ходили к паспорту и за кем.

    Язык привязан к САМОЙ раздаче (её магнит виден в адресе потока), а не к порядку
    вызовов: запасной релиз греется параллельно с верхом, и кто дошёл до ffprobe первым -
    дело случая.
    """
    return FakeMediaProbe(
        {
            f"hash-{release.magnet}/": language
            for release, language in zip(ranked, langs, strict=False)
        }
    )


def test_a_release_without_a_russian_track_is_not_good_enough_and_the_search_goes_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-178. «Включилось» значит «включилось с русской озвучкой».

    До этой правки паспорт с одной японской дорожкой считался годным: лестница выбирала
    лучшее из того, что есть В ВЗЯТОМ релизе, печатала честную строку - и человек
    оставался с японским звуком при живом соседе с русским. Честная строка тут не
    результат, а признание, что мы не дотянулись.
    """
    ranked = [rel(name="r0", seeders=100), rel(name="r1", seeders=90)]
    probe = _tracks(ranked, "jpn", "rus")
    torrserver = _FakeTorrServer()

    prep = _resolve(Bench(cast(Any, torrserver), prober=probe), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 2, "японский релиз годным не считается - идём дальше по очереди"
    assert prep.found.tracks[0].is_russian
    assert "release 1 has no English dub (Japanese) - taking 2" in printed


def test_the_gate_costs_no_extra_probe_when_the_top_release_speaks_russian(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Скорость - часть продукта: на счастливом пути гейт не стоит ни одного лишнего шага.

    Спрашивается уже прочитанный паспорт, а не второй ffprobe и не второй поход в рой.
    Верх заговорил по-русски - очередь дальше не идёт, и к паспорту каждой поднятой
    раздачи мы обращаемся ровно один раз.
    """
    ranked = [rel(name="r0", seeders=100), rel(name="r1", seeders=90), rel(name="r2", seeders=80)]
    probe = _tracks(ranked, "rus", "rus", "rus")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=probe), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 1
    asked = probe.asked
    assert len(asked) == len(set(asked)), "за один и тот же паспорт дважды не платим"
    assert len(asked) <= 2, "верх и греющийся ему на смену запасной - больше никого не трогали"
    assert "без русской озвучки" not in printed, "счастливый путь лишних строк не печатает"


def test_when_nobody_has_a_russian_track_the_show_still_happens_and_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-178. Гейт не слепой: русской нет ни у кого - человек всё равно получает картину.

    Отказать тут значило бы отобрать у зрителя и то, что есть: японский тайтл, который
    никто не озвучивал, - это дыра каталога, а не осечка отбора. Решение громкое: строка
    называет и то, что искали, и то, что в итоге включили.
    """
    ranked = [rel(name="r0", seeders=100), rel(name="r1", seeders=90)]
    probe = _tracks(ranked, "jpn", "jpn")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=probe), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 1, "лучший из того, что есть, а не отказ"
    assert "release 1 has no English dub (Japanese) - taking 2" in printed
    assert (
        "no English dub in any of the checked releases (2) - turning on release 1, sound Japanese"
    ) in printed


def test_the_catalogue_hole_lands_in_the_weekly_trace(
    journal: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-178. «Русской нет ни у кого» обязано попадать в след, а не тонуть в строке.

    По этим записям замер и считает, у скольких картин русской дорожки нет вовсе: экран
    гаснет вместе с сеансом, а недельная лента лежит и читается ``cast log``.
    """
    ranked = [rel(name="r0", seeders=100), rel(name="r1", seeders=90)]
    probe = _tracks(ranked, "jpn", "jpn")

    _resolve(Bench(cast(Any, _FakeTorrServer()), prober=probe), ranked)
    shutdown()
    capsys.readouterr()

    rows = records()
    mute = [r for r in rows if r.get("event") == "mute"]
    assert mute, "дыра каталога обязана быть в ленте"
    assert (mute[-1]["release"], mute[-1]["lang"], mute[-1]["checked"]) == (1, "Japanese", 2)
    assert "nobody has an English voice track (checked 2)" in digest(rows)


def test_a_hand_picked_release_is_never_judged_for_its_language(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--release N`` - человек выбрал сам, и спорить с ним про язык звука не наше дело."""
    ranked = [rel(name="r0", seeders=100), rel(name="r1", seeders=90)]
    probe = _tracks(ranked, "jpn", "rus")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=probe), ranked, release=1)

    assert prep.number == 1
    assert "без русской озвучки" not in capsys.readouterr().out


# --- 🔴 TC-492: «язык не назван» - это незнание, а не годность -------------------------


def test_an_unnamed_language_no_longer_ends_the_queue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-492. Переигровка сеанса «Эксперименты Лэйн» (11-08, очередь из восьми).

    Как было: релизы 1 и 3 забракованы паспортом («без русской озвучки»), у четвёртого
    язык звука не назван - и он игрался, потому что незнание засчитывалось за русскую
    дорожку. В очереди при этом оставались нетронутыми ещё четыре раздачи, и в одной из
    них русская дорожка есть. Зритель услышал нерусский звук при живом соседе.

    Как стало: незнание не годность. Очередь идёт дальше и доходит до подтверждённой
    русской. Лишнего ffprobe это не стоит - спрашивается тот же уже прочитанный паспорт,
    - а от бесконечного перебора выдачу защищают прежние потолки (:data:`MAX_TRIES`,
    :data:`VERDICT_BUDGET`), а не согласие играть неизвестно что.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(8)]
    probe = _tracks(ranked, "jpn", "jpn", "jpn", "und", "jpn", "rus", "jpn", "jpn")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=probe), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 6, "русская дорожка нашлась ниже по очереди - её и играем"
    assert "release 4 has no English dub (unnamed) - taking 5" in printed
    assert "nothing more honest nearby, playing it" not in printed, (
        "«не назван, играю его» больше не бывает"
    )


def test_when_the_queue_runs_out_the_named_language_plays_and_the_unnamed_does_not(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-741. Русской не нашлось ни у кого - играет тот, чей язык НАЗВАН.

    Хода под этот случай не заводится нового: работает тот же
    :meth:`~torrcast.usecases.select_bench.bench.Bench._mute_fallback`, что и всегда. А
    отложенным становится названный японский, а не безымянная дорожка: про японский
    зрителю есть что сказать строкой до картинки, про безымянную - ровно одно, что она
    первая в файле. Прежде незнание вытесняло знание «нет», и отбор кончался тем самым
    релизом, который сам же забраковал строкой «без русской озвучки».
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    probe = _tracks(ranked, "jpn", "und", "jpn")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=probe), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 1, "играет названный японский, а не дорожка без метки языка"
    assert "release 1 has no English dub (Japanese) - taking 2" in printed
    assert (
        "no English dub in any of the checked releases (3) - turning on release 1, sound Japanese"
    ) in printed
    # Отложенным не бывает безымянный: финальный ход обязан назвать НАЗВАННЫЙ язык.
    unnamed_turned_on = (
        "no English dub in any of the checked releases (3) - turning on release 1, sound unnamed"
    )
    assert unnamed_turned_on not in printed, "«не назван, играю его» больше не бывает"


def test_a_native_picture_still_plays_its_only_unnamed_track(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """У отечественной картины безымянная дорожка - паспорт происхождения, а не пробел.

    «Бригаду» никто не озвучивал, она так и снята: гонять по такой очереди гейт русской
    озвучки значило бы искать перевод русского фильма на русский.
    """
    ranked = [rel(name="r0", seeders=100), rel(name="r1", seeders=90)]
    probe = _tracks(ranked, "und", "rus")
    picture = Picture(title="Бригада", year=2002, releases=ranked, native=True)
    plan = Plan(picture=picture, ranked=ranked, runtime=RUNTIME, warn_mbit=20.0, recode_at=10.0)

    with Progress(out=io.StringIO()) as progress:
        prep = Bench(cast(Any, _FakeTorrServer()), prober=probe).resolve(
            plan, Args(query=["бригада"]), progress
        )

    assert prep.number == 1, "своя картина: пустой тег языка - это и есть русский звук"
    assert "без русской озвучки" not in capsys.readouterr().out


def test_a_foreign_picture_whose_original_is_hieroglyphs_keeps_the_voice_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-567. Имя картины записано иероглифами - это не «имени нет», и звук не наш.

    У такой статьи оригинала латиницей взять неоткуда, и паспорт уезжает ровно с тем же
    пустым полем, что у отечественного кино. Прежде отбор читал эту пустоту как паспорт
    происхождения, засчитывал безымянную дорожку за русскую и отдавал зрителю японский
    звук - при живой раздаче с русским прямо в следующей строке очереди.
    """
    ranked = [rel(name="r0", seeders=100), rel(name="r1", seeders=90)]
    probe = _tracks(ranked, "und", "rus")
    picture = Picture(title="Юная революционерка Утэна", year=1997, releases=ranked)
    native_picture(
        picture,
        "юная революционерка утэна",
        read_origin(
            [page("Юная революционерка Утэна", UTENA)], "Юная революционерка Утэна", trusted=True
        ),
    )
    plan = Plan(picture=picture, ranked=ranked, runtime=RUNTIME, warn_mbit=20.0, recode_at=10.0)

    with Progress(out=io.StringIO()) as progress:
        prep = Bench(cast(Any, _FakeTorrServer()), prober=probe).resolve(
            plan, Args(query=["юная", "революционерка", "утэна"]), progress
        )

    assert not picture.native, "иероглифы в скобке - это названное имя, а не его отсутствие"
    assert prep.number == 2, "безымянная дорожка чужой картины русской не становится"
    assert "release 1 has no English dub (unnamed) - taking 2" in capsys.readouterr().out


def test_a_native_passport_reaches_the_voice_gate_without_a_second_search(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Полицейский с Рублёвки: ответ справки относится и к обычному первому кругу."""
    ranked = [
        rel(name="Полицейский с Рублёвки 1080p", seeders=116),
        rel(name="Полицейский с Рублёвки 720p", quality="720p", seeders=80),
    ]
    probe = _tracks(ranked, "und", "rus")
    picture = Picture(title="Полицейский с Рублёвки", year=2016, kind="tv", releases=ranked)
    native_picture(
        picture,
        "полицейский с рублёвки",
        Origin(name="Полицейский с Рублёвки", native=True),
    )
    plan = Plan(picture=picture, ranked=ranked, runtime=RUNTIME, warn_mbit=20.0, recode_at=10.0)

    with Progress(out=io.StringIO()) as progress:
        prep = Bench(cast(Any, _FakeTorrServer()), prober=probe).resolve(
            plan, Args(query=["полицейский", "с", "рублёвки"]), progress
        )

    assert prep.number == 1 and prep.release.quality == "1080p"
    assert "без русской озвучки" not in capsys.readouterr().out


def test_a_release_name_promising_russian_does_not_save_an_unnamed_passport(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-741. Имя раздачи не паспорт: «| D» безымянную дорожку русской не делает.

    Судьёй имя тут не бывает ни в одну сторону (TC-191). Прежде оно покупало верху и
    запасной ход, и собственную мягкую строку - «имя релиза обещает русский», - хотя про
    сам звук по-прежнему не было известно ничего. Играет названный английский ниже, и
    ступень кадра, которой это стоило, зритель читает отдельной строкой: озвучка выше
    чёткости, но молчаливым размен не бывает.
    """
    ranked = [
        rel(name="Кино 1080p | D", seeders=120),
        rel(name="Кино 720p", quality="720p", seeders=80),
    ]
    probe = _tracks(ranked, "und", "eng")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=probe), ranked)

    marker = "no English dub in any of the checked releases ("
    verdicts = [line for line in capsys.readouterr().out.splitlines() if marker in line]
    assert prep.number == 2, "обещание именем годностью не считается"
    assert verdicts == [
        "no English dub in any of the checked releases (2) - turning on release 2, sound English"
    ]
