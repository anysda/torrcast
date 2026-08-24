"""Меню релизов: порядок кандидатов, дефолт по Enter и рендер таблицы."""

from __future__ import annotations

import io
import re
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.fakes.blurb_source import FakeBlurbSource
from tests.fakes.blurb_store import FakeBlurbStore
from tests.fakes.choice_environment import FakeChoiceEnvironment
from torrcast.adapters.console.console.progress import Progress
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.cluster import cluster
from torrcast.domain.episode import Episode
from torrcast.domain.facts.fact import Fact
from torrcast.domain.infra_error import InfraError
from torrcast.domain.kind import Kind
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.pick_settings import VERDICT_BUDGET
from torrcast.domain.picture import Picture
from torrcast.domain.prewarm_settings import MAX_LIVE, PREWARM
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.rank_settings import ALIVE_SEEDERS, FULL_HD_LIVENESS, TABLE_LIMIT
from torrcast.domain.release import Release
from torrcast.domain.runtime_guess import RUNTIME_GUESS
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.choice._pick_plan import _pick_plan
from torrcast.usecases.choice._played import _played
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.backed import backed
from torrcast.usecases.choice.default_line import default_line
from torrcast.usecases.choice.default_note import default_note
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.fitness import fitness
from torrcast.usecases.choice.liveliest import liveliest
from torrcast.usecases.choice.liveliness import liveliness
from torrcast.usecases.choice.menu_blocks import menu_blocks
from torrcast.usecases.choice.namesake_note import namesake_note
from torrcast.usecases.choice.part_one_swap import part_one_swap
from torrcast.usecases.choice.playable import playable
from torrcast.usecases.choice.swap_note import _is_default, swap_note
from torrcast.usecases.choice.understudy import understudy
from torrcast.usecases.choice.understudy_note import understudy_note
from torrcast.usecases.choice.warm_order import warm_order
from torrcast.usecases.choice.warned import warned
from torrcast.usecases.choice.year_note import year_note
from torrcast.usecases.discover._asked_kind import _asked_kind
from torrcast.usecases.discover._no_budget import _no_budget
from torrcast.usecases.discover._nothing import _nothing
from torrcast.usecases.discover._second_language import _second_language
from torrcast.usecases.discover.kin_line import _kin, kin_line
from torrcast.usecases.discover.silent_swarm import silent_swarm
from torrcast.usecases.facts import Facts
from torrcast.usecases.playback._launch import _refuse_hopeless
from torrcast.usecases.rank.bitrate_of import bitrate_of
from torrcast.usecases.rank.is_candidate import is_candidate
from torrcast.usecases.rank.is_dated import is_dated
from torrcast.usecases.rank.is_disc import is_disc
from torrcast.usecases.rank.is_extra import is_extra
from torrcast.usecases.rank.is_full_hd import is_full_hd
from torrcast.usecases.rank.needs_whole_recode import needs_whole_recode
from torrcast.usecases.rank.quality_text import quality_text
from torrcast.usecases.rank.rank_releases import rank_releases
from torrcast.usecases.rank.render_table import render_table
from torrcast.usecases.rank.sound_note import sound_note
from torrcast.usecases.rank.understated import understated
from torrcast.usecases.rank.voice_unproven import voice_unproven
from torrcast.usecases.reinforce._ceiling_reinforce import _ceiling_reinforce
from torrcast.usecases.reinforce._timed import _timed
from torrcast.usecases.reinforce._topup import _topup as _reinforce_topup
from torrcast.usecases.reinforce.ceiling_hides_name import ceiling_hides_name
from torrcast.usecases.releases_command import _cmd_releases
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select._verdict import _silenced
from torrcast.usecases.select._voiced import _Voiced
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench

RUNTIME = RUNTIME_GUESS["movie"]
GB = 1024**3


def rel(
    name: str = "Кино / Movie (1999) BDRip 1080p",
    *,
    codec: str | None = "H.264",
    quality: str | None = "1080p",
    size_gb: float = 8.0,
    seeders: int = 100,
    voices: tuple[str, ...] = ("Дубляж",),
) -> Release:
    return Release(
        raw_name=name,
        title="Кино",
        year=1999,
        quality=quality,
        codec=codec,
        voices=voices,
        size=int(size_gb * GB),
        seeders=seeders,
        # Свой magnet на релиз: без него раздачи неразличимы, а подготовка их греет
        # параллельно - и тест не может сказать, про какую именно раздача ffprobe.
        magnet=f"magnet-{name}",
    )


def test_hevc_is_marked_and_h264_is_not() -> None:
    assert warned(rel(codec="HEVC", size_gb=4), RUNTIME, 20.0) == "не берём"
    assert warned(rel(codec="H.264", size_gb=4), RUNTIME, 20.0) == ""


def test_the_table_promises_to_recode_hevc_instead_of_refusing_it() -> None:
    """Перекодирование включено — HEVC играет, и таблица обязана говорить то же самое.

    «Не берём» рядом с релизом, который на самом деле возьмётся и поедет на ТВ, — это
    та же молчаливая подмена, только наоборот: человек выберет другой релиз зря.
    """
    hevc = rel(codec="HEVC", size_gb=4)
    assert warned(hevc, RUNTIME, 20.0, recode_at=10.0) == "перекодирую целиком"
    assert warned(hevc, RUNTIME, 20.0) == "не берём", "без перекодирования отказ честен"


def test_fat_bitrate_is_marked_even_for_h264() -> None:
    """~28 ГБ на два часа — это 33 Мбит/с, а потолок декодера Q70D около 20."""
    assert warned(rel(size_gb=28), RUNTIME, 20.0) == "тяжёлый"
    assert warned(rel(codec="HEVC", size_gb=28), RUNTIME, 20.0) == "не берём, тяжёлый"


def test_default_is_the_most_seeded_candidate() -> None:
    """Enter = самый обсиженный кандидат; HEVC кандидатом не бывает никогда."""
    top = rel(name="top", seeders=900)
    hevc = rel(name="hevc", codec="HEVC", seeders=800)
    good = rel(name="good", seeders=200)
    meh = rel(name="meh", seeders=10)
    order = [r.raw_name for r in rank_releases([hevc, meh, top, good], RUNTIME, 20.0)]
    assert order == ["top", "good", "meh", "hevc"]


def test_hd_source_without_codec_is_a_candidate() -> None:
    """Кодек в имени раздачи чаще молчит: WEB-DL и BDRip засчитываются кандидатами,
    DVDRip и CAM — нет.
    """
    web = Release(raw_name="WEB-DL", title="Кино", source="WEB-DL", size=4 * GB, seeders=10)
    dvd = Release(raw_name="DVDRip", title="Кино", source="DVDRip", size=1 * GB, seeders=900)
    assert is_candidate(web, RUNTIME, 20.0) and not is_candidate(dvd, RUNTIME, 20.0)
    assert rank_releases([dvd, web], RUNTIME, 20.0)[0].raw_name == "WEB-DL"


def test_seeded_dvdrip_does_not_beat_a_live_1080p() -> None:
    """Ни кодека, ни качества в имени — не кандидат, и толпа сидов дефолта не даёт."""
    dvd = rel(name="DVDRip", codec=None, quality=None, size_gb=1.4, seeders=800)
    hd = rel(name="1080p", seeders=40)
    assert rank_releases([dvd, hd], RUNTIME, 20.0)[0].raw_name == "1080p"
    # Живого 1080p нет вовсе - берём просто самый обсиженный, DVDRip годится.
    sd = rel(name="ещё DVDRip", codec=None, quality=None, size_gb=1.4, seeders=5)
    assert rank_releases([sd, dvd], RUNTIME, 20.0)[0].raw_name == "DVDRip"


def test_fat_release_stays_in_the_table_but_never_becomes_the_default() -> None:
    """Тяжелее потолка отбора (тут он задан 20 Мбит/с) - релиз в таблице есть, но помечен
    и не дефолт.

    ⚠️ Число тут аргумент теста, а не свойство приёмника: рабочий потолок битрейта
    Samsung Q70D - ~10 Мбит/с (замер; «~20» было легендой), и живёт он в его профиле
    (:attr:`torrcast.domain.profile.Profile.recode_at_mbit`).
    """
    fat = rel(name="remux", size_gb=28, seeders=900)
    thin = rel(name="1080p", size_gb=8, seeders=30)
    assert not is_candidate(fat, RUNTIME, 20.0) and is_candidate(thin, RUNTIME, 20.0)
    ranked = rank_releases([fat, thin], RUNTIME, 20.0)
    assert ranked[0].raw_name == "1080p"
    assert "remux" in [r.raw_name for r in ranked]
    assert warned(fat, RUNTIME, 20.0) == "тяжёлый"


def test_disc_images_never_become_the_default() -> None:
    """В VIDEO_TS/BDMV нет цельного файла — стримить нечего, дефолтом быть не может."""
    disc = rel(name="Тачки / Cars (2006) DVD-Video", seeders=500)
    plain = rel(name="Тачки / Cars (2006) BDRip 1080p", seeders=5)
    assert is_disc(disc) and not is_disc(plain)
    assert rank_releases([disc, plain], RUNTIME, 20.0)[0].raw_name.endswith("BDRip 1080p")


def _named(name: str, size_gb: float, seeders: int) -> Release:
    """Раздача прямо из сохранённой выдачи: имя настоящее, размер и сиды тоже."""
    return replace(
        parse_release_name(name),
        size=int(size_gb * GB),
        seeders=seeders,
        magnet=f"magnet-{name}",
    )


def test_a_making_of_never_stands_for_the_picture_itself() -> None:
    """🔴 TC-290. Ролик о съёмках - не картина, и кандидатом он быть не вправе.

    Живой случай из сохранённой выдачи «тачки»: у картины «Тачки 2» ворота отбора судили
    разрешение, битрейт, живость и звук - и ни одна ступень не спрашивала, картина ли это
    вообще. «HDRip … фильм о фильме» на 0.4 ГБ проходил обычным кандидатом, а в пуле, где у
    картины всего две раздачи, вставал ПЕРВЫМ, то есть дефолтом Enter. Человек просит кино
    и получает получасовой ролик о съёмках - молчаливая подмена самой картины.
    """
    making = _named(
        "Тачки 2 / Cars 2 [2011, мультфильм, комедия, приключения, HDRip] фильм о фильме", 0.4, 1
    )
    trailer = _named("Тачки 2 / Cars 2 (2011) HDRip 720р-Трейлер", 0.02, 0)
    picture = _named("Тачки 2 / Cars 2 (2011) BDRip 720p от Leonardo and Scarabey", 3.0, 13)

    assert making.extras and trailer.extras, "имя само называет их приложением к картине"
    assert not picture.extras
    assert not is_candidate(making, RUNTIME, 16.0) and not is_candidate(trailer, RUNTIME, 16.0)
    assert is_candidate(picture, RUNTIME, 16.0), "а сама картина кандидат, как и была"
    assert rank_releases([making, picture], RUNTIME, 16.0)[0] is picture


def test_the_picture_keeps_its_own_name_even_when_it_sounds_like_a_bonus() -> None:
    """Ограждение: слово в СОБСТВЕННОМ имени картины приложением её не делает.

    Три случая из тех же выдач, и все три обязаны остаться кандидатами: документальная
    картина, у которой «вырезанные сцены» стоят в названии; раздача, несущая картину И
    приложение к ней («+ Бонус», «+ Extra»); короткометражка, которую справка честно
    называет короткой, - при её длительности вес на минуту у неё обычный.
    """
    own_name = _named(
        "Твин Пикс: Вырезанные сцены / Twin Peaks: The Missing Pieces (2014) BDRip 720p", 7.36, 4
    )
    with_bonus = _named("Тачки + Бонус / Cars (2006) BDRip 1080p от HD Club", 10.8, 6)
    pack = _named("Пацаны / The Boys [S01-05 + Extra] (2019-2026) WEB-DL-AVC | КПК", 9.46, 40)
    short = _named("Немая жизнь / Silent Life [2006, драма, WEB-DL 1080p] интервью", 1.4, 12)

    assert not own_name.extras and not with_bonus.extras and not pack.extras
    assert is_candidate(own_name, RUNTIME, 16.0) and is_candidate(with_bonus, RUNTIME, 16.0)
    # Короткометражке метку ставит имя, а ворота её снимает длительность из справки:
    # 21 минута при 1.4 ГБ - это 9 Мбит/с, вес картины, а не ролика о ней.
    assert short.extras, "слово в имени есть"
    assert not is_candidate(short, RUNTIME, 16.0), "на прикидке «фильм это два часа» - ролик"
    assert is_candidate(short, 21 * 60.0, 16.0), "справка назвала 21 минуту - это картина"


def test_the_only_release_of_a_picture_is_not_shown_instead_of_it() -> None:
    """🔴 TC-432. Единственная раздача, которая не картина, в очередь не встаёт.

    У «Мандалорца» 2019 года в сохранённой выдаче ровно одна раздача-фильм, и та
    трейлер. Прежняя безусловность верха ранжира ставила его в очередь первым, и
    человек, прося сериал, получал ролик о нём - подмену картины молча. Ворота
    проходят все, включая верх; вернуть отсеянную раздачу может только сам человек,
    номером из таблицы.
    """
    only = _named(
        "Мандалорец / The Mandalorian [2019, фантастика, приключения, HDRip] Трейлер", 0.21, 1
    )
    plan = Plan(
        picture=Picture(title="Мандалорец", year=2019, releases=[only]),
        ranked=rank_releases([only], RUNTIME, 16.0),
        runtime=RUNTIME,
        warn_mbit=16.0,
    )
    assert not is_candidate(only, RUNTIME, 16.0)
    assert plan.candidates(Args(query=["мандалорец"])) == [], "подмены картины нет"
    assert plan.candidates(Args(query=["мандалорец"], release=1)) == [1], (
        "названный человеком номер в ворота не ходит"
    )


def test_an_empty_queue_is_an_honest_refusal_not_a_substitute() -> None:
    """🔴 TC-432. Ворота не пустил никого - честное «не нашлось», а не подстановка.

    «Ведьмак 3: Дикая Охота» - игра на 35.6 ГБ, и на запрос «ведьмак s2e4» она стояла
    единственным кандидатом своей картины: верх ранжира попадал в очередь безусловно.
    Отказ обязан назвать выдачу и причину отсева каждой раздачи - и не советовать
    выбирать руками там, где все раздачи отвергнуты по известным признакам.
    """
    game = [rel(name=f"игра {n}", size_gb=35.6, seeders=40 - n) for n in range(2)]

    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, _FakeTorrServer())), game)

    msg = str(caught.value)
    assert "годного релиза нет: раздач в выдаче 2" in msg, msg
    assert "все до одной отсеял отбор (тяжелее потолка - 2)" in msg, msg
    assert "выбери руками" not in msg and "--release" not in msg


def test_an_empty_queue_without_kin_still_names_the_next_step() -> None:
    """🔴 TC-447. Соседей по франшизе нет - а ход у отказа обязан быть всегда.

    Пустая очередь без живых частей франшизы кончала строку перечнем причин, и хода в
    ней не было - а отказ без хода это тупик. «Выбери руками» тут врал бы: раздачи
    отвергнуты по известным признакам, номер этого не меняет. «Ничего не нашлось» врало
    бы тоже: картина в каталоге есть, негодны её раздачи, - так и говорится.
    """
    game = [rel(name=f"игра {n}", size_gb=35.6, seeders=40 - n) for n in range(2)]

    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, _FakeTorrServer())), game)

    msg = str(caught.value)
    assert "все до одной отсеял отбор (тяжелее потолка - 2)" in msg, msg
    assert "в каталоге есть" not in msg, "соседей нет - и подсказки про них нет"
    assert "картина есть, а раздачи её негодны" in msg, msg
    assert "назови её иначе или зайди позже" in msg, msg
    assert "выбери руками" not in msg and "--release" not in msg


def test_an_out_of_range_hand_picked_number_names_its_picture() -> None:
    """🔴 TC-446. Названный руками номер считается по выбранной картине, и отказ её
    называет.

    «релизов 2, номера 3 нет» без имени читалось как счёт всей выдачи, а считалось по
    одной картине - той, что человек выбрал в меню или назвал флагом ``--pick``.
    """
    plan = _plan([rel(name="r1"), rel(name="r2")])

    with pytest.raises(NotFoundError, match="у «Кино» релизов 2, номера 3 нет"):
        plan.candidates(Args(query=["кино"], release=3))


def test_a_heavy_bonus_disc_with_a_plain_mark_is_turned_away() -> None:
    """🔴 TC-339. Однозначная метка судит без веса: тяжёлое приложение - не кандидат.

    «Дополнительные материалы» и «бонус-диск» не бывают картиной ни при каком битрейте:
    «Титаник | Дополнительные материалы» на 11.6 ГБ, «Довод» на 22.5 ГБ, «Хоббит:
    Приложения» на 19.2 ГБ проходили ворота по весу и могли подменить картину, стоит
    умереть всему выше них. Метке без веса - только ВОРОТА; порядок и таблица видят
    раздачу по-прежнему, а картина, у которой других раздач нет, своего верха не
    теряет (:meth:`Plan.candidates`).

    Метка НЕоднозначная («трейлер» у ещё не вышедшей картины, «фильм о фильме» у
    документального кино) без веса не судится: такую носят и раздачи самой картины.
    """
    from torrcast.usecases.rank.is_extra import is_extra

    bonus = _named("Титаник / Titanic (1997) BDRip | Дополнительные материалы", 11.56, 12)
    disc = _named("Тачки 3 [Бонус-Диск] / Cars 3 [Bonus Disc] (2017) BDRip 720p", 2.7, 3)
    picture = _named("Титаник / Titanic (1997) BDRip 1080p", 11.0, 12)
    trailer = _named("Дюна: Часть Третья / Dune: Part Three (2026) WEB-DL | Трейлеры", 2.5, 10)

    assert bonus.extras_sure and disc.extras_sure
    assert is_extra(bonus, RUNTIME) and is_extra(disc, RUNTIME), "вес такой метке не нужен"
    assert not is_candidate(bonus, RUNTIME, 16.0) and not is_candidate(disc, RUNTIME, 16.0)
    assert not trailer.extras_sure and not is_extra(trailer, RUNTIME)
    assert is_candidate(trailer, RUNTIME, 16.0), "неоднозначная метка без веса не судит"
    assert rank_releases([bonus, picture], RUNTIME, 16.0)[0] is picture


def test_the_only_sure_marked_release_of_a_picture_is_not_shown_instead_of_it() -> None:
    """🔴 TC-432 поверх TC-339: однозначная метка отнимает и единственную раздачу.

    У «воссоединения актёрского состава» из сохранённой выдачи единственная раздача
    несёт метку «допматериалы» - и она же есть та самая картина, которую спросили.
    Замер TC-339 держался на том, что верх :attr:`~torrcast.usecases.select.plan.Plan.ranked`
    попадает в очередь безусловно; TC-432 повёл через ворота и его, и такая картина теперь кончается
    честным отказом, а не бонус-диском вместо картины. Метка при этом судит БЕЗ веса, как и судила:
    2.4 ГБ тут по битрейту выглядят картиной.

    Вернуть отсеянную раздачу может только сам человек, номером из таблицы: ``--release N``
    в ворота не ходит.
    """
    only = _named(
        "Властелин Колец: воссоединение актёрского состава / Cast Reunion [2021] допматериалы",
        2.4,
        2,
    )
    plan = Plan(
        picture=Picture(
            title="Властелин Колец: воссоединение актёрского состава", year=2021, releases=[only]
        ),
        ranked=rank_releases([only], RUNTIME, 16.0),
        runtime=RUNTIME,
        warn_mbit=16.0,
    )
    assert only.extras_sure and not is_candidate(only, RUNTIME, 16.0)
    assert plan.candidates(Args(query=["властелин", "колец"])) == [], "подмены картины нет"
    assert plan.candidates(Args(query=["властелин", "колец"], release=1)) == [1], (
        "названный человеком номер в ворота не ходит"
    )


def test_ordinary_release_is_not_mistaken_for_a_disc() -> None:
    assert not is_disc(rel(name="Кино (1999) BDRip 1080p x264 от Мутный"))
    assert is_disc(rel(name="Кино (1999) Blu-Ray Disc 1080p"))


def test_table_has_all_the_columns() -> None:
    text = render_table([rel(seeders=214, voices=("Дубляж",))], RUNTIME, 20.0)
    lines = text.splitlines()
    assert lines[0] == "Релизы:"
    assert lines[1].split() == ["N", "Качество", "Размер", "Сиды", "Озвучка", "Студия", "Кодек"]
    assert lines[2].split() == ["1", "1080p", "8.0", "ГБ", "214", "Дубляж", "-", "H.264"]


def test_table_marks_hevc_row() -> None:
    text = render_table([rel(codec="HEVC", size_gb=28, seeders=45)], RUNTIME, 20.0)
    assert text.splitlines()[2].endswith("HEVC не берём, тяжёлый")


def test_table_columns_line_up() -> None:
    releases = [
        rel(seeders=1, voices=("Дубляж",)),
        rel(seeders=1000, voices=("Дубляж", "Original")),
    ]
    rows = render_table(releases, RUNTIME, 20.0).splitlines()[1:]
    assert len({len(row.rstrip()) - len(row.rstrip().rsplit("  ", 1)[-1]) for row in rows}) == 1


def test_table_shows_only_the_head_of_a_long_list() -> None:
    releases = [rel(name=f"r{i}", seeders=100 - i) for i in range(TABLE_LIMIT + 7)]
    text = render_table(releases, RUNTIME, 20.0)
    assert len(text.splitlines()) == TABLE_LIMIT + 3  # заголовок, шапка, строки, хвост
    assert "и ещё 7 с меньшим числом сидов" in text


def test_missing_values_are_shown_as_dashes() -> None:
    text = render_table([rel(codec=None, quality=None, size_gb=0, voices=())], RUNTIME, 20.0)
    row = text.splitlines()[2]
    assert "-" in row and "?" in row


@pytest.mark.parametrize("size_gb,expected", [(4.0, ""), (28.0, "тяжёлый")])
def test_bitrate_threshold_is_configurable(size_gb: float, expected: str) -> None:
    assert warned(rel(size_gb=size_gb), RUNTIME, 20.0) == expected


def test_the_ceiling_is_sixteen_because_the_tv_rebuffers_at_eighteen() -> None:
    """Потолок битрейта опущен по живому замеру на Q70D.

    17.8 Мбит/с телевизор играет с ребуфером раз в 30–60 с, и каждый подвис
    стоит 8 с пропущенного фильма. Поэтому дефолт опущен 20 → 16: смотрибельность важнее
    пиковой чёткости. Руками (``--release N``) тяжёлый релиз берётся по-прежнему, и
    молчком это не делается — в таблице он помечен «тяжёлый».
    """
    from torrcast.domain.config import Config

    assert Config().bitrate_warn_mbit == 16.0
    fat = rel(size_gb=17.8 * RUNTIME / 8 / 1024**3 * 1e6)  # ровно 17.8 Мбит/с
    assert not is_candidate(fat, RUNTIME, Config().bitrate_warn_mbit), "Enter его не возьмёт"
    assert warned(fat, RUNTIME, Config().bitrate_warn_mbit) == "тяжёлый", "но и не спрячет"
    assert is_candidate(rel(size_gb=13.0), RUNTIME, Config().bitrate_warn_mbit), "15.5 Мбит/с ок"


class _FakeTorrServer:
    """TorrServer ровно в том объёме, в каком его дёргает подготовка релиза."""

    def __init__(self, files: list[TorrFile] | None = None, dead: set[str] | None = None) -> None:
        self.dropped: list[str] = []
        self.files = files if files is not None else [TorrFile(0, "movie.mkv", 4 * GB)]
        self.dead = dead or set()

    def add(self, magnet: str) -> str:
        return f"hash-{magnet}"

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        if torrent_hash in self.dead:  # раздача с мёртвым роем: пиров нет и не будет
            raise SwarmError(f"раздача не отдала метаданные за {timeout:.0f} с - нет пиров")
        return self.files

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> bool:
        self.dropped.append(torrent_hash)

        return True


#: Подделка ffprobe: адрес потока, потолок ожидания и признак живого роя - в :class:`Media`.
_Prober = Callable[..., Media]


def _probes(releases: list[Release], *codecs: str) -> _Prober:
    """Подсунуть ffprobe: по кодеку на релиз, считая от лучшего.

    ⚠️ Раздавать кодеки по порядку ВЫЗОВОВ нельзя: прогрев греет запасной релиз
    параллельно с основным, и кто из потоков дошёл до ffprobe первым — дело случая.
    Так уже ловилось: тест «три негодных подряд» развалился от того, что в подготовке
    появился лишний вызов перед probe. Поэтому кодек привязан к самой раздаче: её magnet
    виден в адресе потока, а место в очереди известно заранее.
    """

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        for number, release in enumerate(releases):
            if f"hash-{release.magnet}/" in url and number < len(codecs):
                return Media(3600.0, (), codecs[number])
        return Media(3600.0, (), "h264")

    return read


def _plan(ranked: list[Release], recode_at: float = 10.0) -> Any:
    from torrcast.domain.picture import Picture

    picture = Picture(title="Кино", year=1999, releases=ranked)
    # ``recode_at`` не украшение: в бою перекодирование включено (:class:`Config`), и
    # именно от него зависит, отказ HEVC или сплошной перекод. Ноль - «перекодирование
    # выключено», и тогда поведение обязано остаться прежним.
    return Plan(
        picture=picture, ranked=ranked, runtime=RUNTIME, warn_mbit=20.0, recode_at=recode_at
    )


def _raw(name: str, tag: str, seeders: int) -> Any:
    """Одна строка выдачи опоздавшего индексера; хэш подделываем из тега."""
    from torrcast.domain.raw_result import RawResult

    return RawResult(
        title=name, info_hash=tag * 40, size=int(8 * GB), seeders=seeders, indexer="Nyaa.si"
    )


def _topup(plan: Any, rows: list[Any], menu: frozenset[str] = frozenset()) -> tuple[Any, str]:
    """Долив опоздавшего в готовый план; отдаёт новый план и напечатанное."""
    plan.late = lambda: rows
    out = io.StringIO()
    with Progress(out=out) as progress:
        fresh = _reinforce_topup(
            plan, Args(query=["кино"]), load_config(), CAUTIOUS, progress, menu
        )
    return fresh, out.getvalue()


def test_долив_опоздавшего_пополняет_пул_выбранной_картины() -> None:
    """🔴 TC-118. Круг ушёл по кворуму, Nyaa доехал, пока человек читал меню. Его раздачи
    доливаются в пул ВЫБРАННОЙ картины - иначе опоздавший терялся бы вовсе."""
    plan = _plan([rel(name="Кино / Movie (1999) BDRip 1080p", seeders=100)])
    fresh, said = _topup(plan, [_raw("Кино / Movie (1999) BDRip 2160p", "b", 900)])

    assert len(fresh.picture.releases) == 2
    assert fresh.picture.key == plan.picture.key, "картина та же - подменять её долив не вправе"
    assert "доехал после списка: раздач 2 вместо 1" in said


def test_долив_называет_вслух_смену_верха_отбора() -> None:
    """Верх отбора долив поменять вправе - выбирали картину, а не раздачу, - но не молча:
    строка называет и опоздавшего, и то, что верх теперь другой."""
    plan = _plan([rel(name="Кино / Movie (1999) BDRip 1080p", seeders=100)])
    fresh, said = _topup(plan, [_raw("Кино / Movie (1999) BDRip 1080p x264", "c", 900)])

    assert fresh.ranked[0].seeders == 900, "обсиженная раздача встала верхом отбора"
    assert "верх отбора другой" in said


def test_долив_не_вносит_в_список_картину_которой_в_меню_не_было() -> None:
    """Меню уже напечатано, и человек по нему ответил. Картина, приехавшая с опоздавшим,
    в него попасть не может - предложить её уже некому, а подменить выбранную нельзя.
    Но и молча она пропадать не должна (TC-238): молчаливых пропаж не бывает, и человек
    узнаёт одной строкой, что опоздавший источник привёз ещё одну картину."""
    plan = _plan([rel(name="Кино / Movie (1999) BDRip 1080p", seeders=100)])
    fresh, said = _topup(plan, [_raw("Другое / Other (2001) BDRip 1080p", "d", 900)])

    assert fresh is plan, "чужая картина плана не меняет вовсе"
    assert "привёз «Другое» (2001)" in said, "опоздавшего и привезённое называют вслух"
    assert "в списке её не было, в отбор она не пойдёт" in said


def test_долив_молчит_про_картину_которая_в_меню_есть() -> None:
    """Раздача ДРУГОЙ картины из меню тоже не доливается - долив пополняет только пул
    выбранной, - но сказать про такую «в списке её не было» значило бы соврать: она там
    есть, человек её видел. Поэтому соседняя по меню строки не получает."""
    from torrcast.adapters.prowlarr.to_releases import to_releases
    from torrcast.domain.cluster import cluster

    plan = _plan([rel(name="Кино / Movie (1999) BDRip 1080p", seeders=100)])
    rows = [_raw("Другое / Other (2001) BDRip 1080p", "d", 900)]
    guest = cluster(to_releases(rows))[0]
    menu = frozenset({plan.picture.key, guest.key})
    fresh, said = _topup(plan, rows, menu)

    assert fresh is plan, "чужой пул долив не пополняет"
    assert said == "", "про картину из меню говорить «её не было» - соврать"


def test_чужая_картина_не_глушит_долив_в_свою() -> None:
    """Опоздавший привёз и раздачу ВЫБРАННОЙ картины, и картину вне списка: пул растёт,
    и печатаются обе строки - про долив и про ту, что в отбор не пойдёт."""
    plan = _plan([rel(name="Кино / Movie (1999) BDRip 1080p", seeders=100)])
    fresh, said = _topup(
        plan,
        [
            _raw("Кино / Movie (1999) BDRip 2160p", "b", 900),
            _raw("Другое / Other (2001) BDRip 1080p", "d", 900),
        ],
    )

    assert len(fresh.picture.releases) == 2, "своя раздача долилась"
    assert "доехал после списка: раздач 2 вместо 1" in said
    assert "привёз «Другое» (2001)" in said


def test_пустой_долив_оставляет_план_прежним() -> None:
    """Опоздавший так и не доехал - план прежний, и ни одной лишней строки."""
    plan = _plan([rel(name="Кино / Movie (1999) BDRip 1080p", seeders=100)])
    fresh, said = _topup(plan, [])

    assert fresh is plan
    assert said == ""


class _Spent:
    """Клиент поиска, у которого от цели осталось ровно столько."""

    def __init__(self, spare: float) -> None:
        self._spare = spare
        #: Частный бюджет за целью ещё не выдан - как у свежего клиента поиска
        #: (:attr:`torrcast.adapters.prowlarr.prowlarr.Prowlarr.over_goal`). Подделка обязана
        #: обещать это поле: без него охранник читал бы у настоящего клиента то, чего у неё нет.
        self.over_goal = False

    def spare(self) -> float:
        return self._spare

    def late(self) -> list[Any]:
        return []


def _budget(spare: float) -> tuple[float | None, str]:
    out = io.StringIO()
    with Progress(out=out) as progress:
        left = _no_budget(cast(Any, _Spent(spare)), "добор по «кино»", progress)
    return left, out.getvalue()


def test_дешёвый_добор_не_снимается_молчуном_съевшим_цель() -> None:
    """🔴 TC-512. Первый круг съел цель молчанием Knaben, но дешёвый добор не исчезает:
    ему остаются измеренные 1.5 с справки и 1 с круга, а выход за цель назван."""
    left, said = _budget(0.3)

    from torrcast.domain.facts.settings import FACTS_BUDGET

    assert left == FACTS_BUDGET
    assert "всё равно делаю в свои 2.5 с" in said
    assert "поиск уже съел цель в 10 с" in said


def test_частный_бюджет_за_целью_выдаётся_один_раз_за_поиск() -> None:
    """🔴 TC-512. Превышение цели терпится ОДНО, а не по одному на каждый заход.

    Пол круга - это потолок одного индексера, а не цена круга: замер на молчащих опорных
    дал 2.0 с при одном и 4.0 с при двух, то есть добор стоит до 5.5 с вместо расчётных
    2.5. Охраняемых заходов на пути до трёх (переспрос строкой или уточнение, сезонная и
    голосовая строки), и раздать бюджет каждому значило бы дописать к уже съеденной цели
    до пятнадцати секунд - молчун перестал бы сужать каталог и начал тормозить путь.
    Поэтому за целью проходит первый заход, а следующим отвечает то, что уже найдено.
    """
    from torrcast.domain.facts.settings import FACTS_BUDGET

    client = cast(Any, _Spent(0.3))
    out = io.StringIO()
    with Progress(out=out) as progress:
        first = _no_budget(client, "добор по «кино»", progress)
        second = _no_budget(client, "добор сезона 2", progress)
        third = _no_budget(client, "добор по «Kino»", progress)
    said = out.getvalue()

    assert first == FACTS_BUDGET, "первый заход за целью получает свой частный бюджет"
    assert second is None and third is None, "второе превышение цели уже не оплачивается"
    assert "добор по «кино» всё равно делаю" in said
    assert "добор сезона 2 не делаю: поиск уже съел цель в 10 с" in said
    assert "добор по «Kino» не делаю" in said, "отказ сказан вслух каждому, а не молча"


def test_целый_остаток_цели_частный_бюджет_не_тратит() -> None:
    """Пока цель цела, заходы идут из общего остатка и превышения не занимают: частный
    бюджет ждёт того единственного захода, который упрётся в съеденную цель."""
    from torrcast.domain.facts.settings import FACTS_BUDGET

    client = cast(Any, _Spent(9.0))
    with Progress(out=io.StringIO()) as progress:
        assert _no_budget(client, "уточнение", progress) == FACTS_BUDGET
        assert _no_budget(client, "добор сезона 2", progress) == FACTS_BUDGET
    assert client.over_goal is False, "остатка хватало - превышения не было"


def test_остаток_цели_делится_между_справкой_и_кругом() -> None:
    """Справка на пути добора учтена честно: ей достаётся остаток за вычетом доли самого
    круга, и её потолок она не переходит. Порог второго захода из этих двух частей и
    сложен - иначе полторы секунды справки съедали бы круг целиком, а он уже оплачен."""
    from torrcast.domain.facts.settings import FACTS_BUDGET
    from torrcast.domain.goal_spare import CIRCLE_SHARE, SECOND_LEAST

    assert SECOND_LEAST == FACTS_BUDGET + CIRCLE_SHARE, "порог = потолок справки плюс круг"
    assert _budget(10.0)[0] == FACTS_BUDGET, "цела вся цель - справке её полный потолок"
    assert _budget(SECOND_LEAST)[0] == pytest.approx(FACTS_BUDGET), "в обрез - потолок тот же"
    assert _budget(SECOND_LEAST - 0.01)[0] == FACTS_BUDGET, "общий остаток добор не снимает"


def test_добор_вторым_именем_не_отменяется_съеденной_целью() -> None:
    """🔴 TC-386. Остатка цели на добор по второму имени нет - а добор всё равно делается.

    Отмена тут стоила картины: живой замер TC-372 - «тачки» при медленном Knaben (7.0 с
    вместо 0.5) теряли пул с 28 раздач до 4-5 и кончались отказом. По лестнице целей
    «не включилось» сильнее «дольше 10 секунд», поэтому цель подчиняется: справке на
    этом пути достаётся её обычный потолок (отдавать весь остаток уже нечего - он
    съеден), а круг идёт с полом в целую цель (:attr:`Prowlarr.cap_floor`).
    """
    from torrcast.domain.facts.settings import FACTS_BUDGET

    empty = _asked_reference([], Args(query=["клиника", "s1e1"]), spare=0.3)
    assert empty == ("клиника", True, FACTS_BUDGET), "картины нет - справку спросили всерьёз"

    lean = Picture(title="Клиника", year=2001, kind="tv", releases=[rel(name="Клиника s01e01")])
    thin = _asked_reference([lean], Args(query=["клиника", "s1e1"]), spare=0.3)
    assert thin == ("клиника", True, FACTS_BUDGET), "и на тощем пуле - её обычный потолок"


def test_тип_картины_справке_называет_выдача_а_на_пустой_сам_запрос() -> None:
    """🔴 TC-243. Тип нужен справке, и брать его наугад нельзя - только с чужих слов.

    У сериала и фильма разные статьи, и подсказка наугад уводит в чужую («Восхождение» с
    ``True`` - сериал 2024 вместо фильма Шепитько). Поэтому источников ровно два, и оба
    говорят о картине прямо: разобранная выдача первого круга, а на пустой выдаче - сам
    запрос, в котором человек назвал серию. Молчание о серии по-прежнему не значит
    «фильм»: тогда справка идёт прежним осторожным режимом «оба типа» (``None``).
    """
    show = Picture(title="Клиника", year=2001, kind="tv")
    film = Picture(title="Клиника", year=2001, kind="movie")

    assert _asked_kind(show, Args(query=["клиника"])) is True
    assert _asked_kind(film, Args(query=["клиника"])) is False
    asked = _asked_kind(None, Args(query=["клиника", "s1e1"]))
    assert asked is True, "выдачи нет, но серию назвал сам человек - это сериал"
    assert _asked_kind(None, Args(query=["клиника"])) is None, "спросить не у кого"


def _resolve(bench: Any, ranked: list[Release], recode_at: float = 10.0, **flags: Any) -> Any:
    args = Args(query=["кино"], **flags)
    with Progress(out=io.StringIO()) as progress:
        return bench.resolve(_plan(ranked, recode_at), args, progress)


def test_a_release_that_turns_out_not_to_be_h264_is_swapped_out_loudly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Имя раздачи о кодеке молчит, а видео мы отдаём copy: настоящий кодек решает.
    Не h264 — честная строка и следующий кандидат, молчаливых подмен не бывает.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "av1", "h264")
    torrserver = _FakeTorrServer()
    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    assert (prep.number, prep.found.video) == (2, "h264")
    assert prep.want.name == "movie.mkv"
    assert "релиз 1 не годится (av1) - беру 2" in capsys.readouterr().out
    assert torrserver.dropped, "неподошедшая раздача из TorrServer убирается"


@pytest.mark.machine
def test_two_release_passports_start_together_before_verdicts() -> None:
    """Запасной ffprobe не ждёт первого приговора; третий счастливый путь не оплачивает."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    second_started = threading.Event()
    first_saw_second = False

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        nonlocal first_saw_second
        if f"hash-{ranked[1].magnet}/" in url:
            second_started.set()
        if f"hash-{ranked[0].magnet}/" in url:
            first_saw_second = second_started.wait(0.5)
        codec = "h264" if f"hash-{ranked[2].magnet}/" in url else "av1"
        return Media(3600.0, (), codec)

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=read), ranked)

    assert prep.number == 3
    assert first_saw_second, "запасной паспорт поднят до готовности первого приговора"


def test_hevc_release_plays_and_says_so_instead_of_being_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """HEVC — не отказ, а сплошной перекод: аниме иначе не играет вовсе.

    До этого верх отбора с HEVC внутри стоил строки «релиз 1 не годится (hevc)», и на
    Nyaa, где HEVC бывает всем, что нашлось, показ кончался «годного релиза нет».
    Теперь такой релиз играет, перекодированный целиком, и об этом говорится вслух.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "hevc", "h264")
    torrserver = _FakeTorrServer()

    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert (prep.number, prep.found.video) == (1, "hevc"), "HEVC-релиз играет, а не отказывает"
    assert "видео hevc - перекодирую на ходу целиком" in printed
    assert "не годится" not in printed and not re.search(r"беру \d", printed)


def test_hevc_is_still_refused_when_recoding_is_switched_off(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Перекодирование выключено — играть HEVC нечем, и отказ остаётся честным.

    Обратная сторона того же решения: сплошной перекод и есть единственный способ
    показать HEVC на этом приёмнике, поэтому без него релиз годным не становится.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "hevc", "h264")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked, recode_at=0.0)

    assert prep.number == 2, "без перекодирования HEVC остаётся отказом"
    assert "релиз 1 не годится (hevc) - беру 2" in capsys.readouterr().out


def test_mpeg4_release_plays_through_the_same_whole_recode_instead_of_being_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """XviD/DivX - не отказ, а сплошной перекод: на старом кино другого носителя нет.

    Мультклассика и советская документалка лежат в единственной раздаче, и внутри у неё
    ``mpeg4``. Такой релиз играет тем же механизмом, что и HEVC, и говорит об этом
    вслух; цена перекода замерена (:attr:`torrcast.domain.profile.Profile.recode_codecs`).
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "mpeg4", "h264")
    torrserver = _FakeTorrServer()

    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert (prep.number, prep.found.video) == (1, "mpeg4"), "mpeg4-релиз играет, а не отказывает"
    assert "видео mpeg4 - перекодирую на ходу целиком" in printed
    assert "не годится" not in printed and not re.search(r"беру \d", printed)


def test_mpeg4_is_still_refused_when_recoding_is_switched_off(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Перекодирование выключено - играть mpeg4 нечем, и отказ остаётся честным."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "mpeg4", "h264")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked, recode_at=0.0)

    assert prep.number == 2, "без перекодирования mpeg4 остаётся отказом"
    assert "релиз 1 не годится (mpeg4) - беру 2" in capsys.readouterr().out


def test_a_dead_swarm_is_not_a_hang_but_the_next_release(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Так выглядел худший из багов: «Дорожки: читаю поток…» и тишина навсегда.

    Раздача с мёртвым роем обязана стоить одной строки и перехода к следующему релизу,
    а не молчаливого зависания без прогресса и без таймаута.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "h264")
    torrserver = _FakeTorrServer(dead={"hash-magnet-r0"})

    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 2, "мёртвая раздача не останавливает показ"
    assert "релиз 1 не годится (не дождались за 20 с)" in printed
    assert "беру 2" in printed


def test_silent_swarms_do_not_burn_the_tries_meant_for_verdicts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """«Нет пиров» четыре раза подряд — это не повод сдаться: живые ждут ниже в очереди.

    Главная причина 🟡 в замере на тысяче запросов: отбор пробовал ровно три раздачи и
    заканчивал словами «годного релиза нет», хотя рядом в очереди стояли играбельные.
    Перепроверка тех же картин в один поток оживляла шесть из восьми («Кавказская
    пленница», «Зона интересов», «Бесконечная история»).

    Разница между двумя осечками принципиальная: приговор ffprobe («это av1») про релиз
    рассказал всё, а молчание роя — ничего, кроме того, что раздача не отозвалась.
    Попытку жжёт только первое.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(6)]
    prober = _probes(ranked, "h264")
    torrserver = _FakeTorrServer(dead={f"hash-magnet-r{i}" for i in range(4)})

    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 5, "четыре молчаливых роя подряд - и всё же дошли до живого"
    assert printed.count("не дождались") == 4, "каждая осечка стоит строку, молчаливых нет"
    assert "беру 5" in printed


def test_the_walk_down_the_queue_stops_when_the_start_budget_is_out(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Упорство упорством, а человек сидит у консоли: бюджет фазы отбора конечен.

    Потолок тот же, что был у трёх попыток по полному бюджету раздачи
    (:data:`~torrcast.domain.pick_settings.PICK_BUDGET`), и кончиться он обязан честной строкой, а
    не новым походом в рой. 🔴 TC-435: честная - это «рой молчит», а не «годного релиза
    нет»: негодных не нашли ни одной, их просто не прочитали. Совета «выбери руками»
    тут нет - весь бюджет ушёл на раздачи, стоявшие выше неспрошенных, и про хвост
    очереди мы не знаем ничего (:func:`~torrcast.usecases.discover.silent_swarm.silent_swarm`).
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(6)]
    prober = _probes(ranked, "h264")
    torrserver = _FakeTorrServer(dead={f"hash-magnet-r{i}" for i in range(4)})

    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, torrserver), prober=prober, pick_budget=0.0), ranked)

    msg = str(caught.value)
    assert "раздач в выдаче 6, потрогали 1 из очереди 6" in msg, msg
    assert "эти молчат, на остальных не хватило времени" in msg, msg
    assert "не дождались" in msg, "причина молчания названа, а не спрятана"
    assert "годного релиза нет" not in msg, "это молчание роя, а не отсутствие годных"
    assert "выбери руками" not in msg and "--release" not in msg
    assert "зайди позже" in msg, "ход остаётся, но честный"
    assert capsys.readouterr().out.count("не дождались") == 1, "бюджет вышел - второго похода нет"


class _FakeClock:
    """Поддельные монотонные часы: время двигают ожидания, а не настоящий сон."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class _Sleeper:
    """Подготовка, которая не будет готова никогда, - вместо :class:`threading.Event`.

    Каждый заход ожидания двигает поддельные часы ровно на свой срок: цикл идёт как
    настоящий, а секунды не тратятся.
    """

    def __init__(self, clock: _FakeClock) -> None:
        self.clock = clock

    def wait(self, timeout: float | None = None) -> bool:
        self.clock.now += timeout or 0.0
        return False


def test_the_pick_budget_cuts_the_wait_it_has_already_started() -> None:
    """🔴 TC-436. Потолок фазы отбора держит и ожидание ВНУТРИ попытки, а не только переход.

    Замер TC-424: потолок (:data:`~torrcast.domain.pick_settings.PICK_BUDGET`, 180 с) проверялся
    ровно между попытками, поэтому свежий прогрев, начатый на 179-й секунде, ждал своего по СВОЕМУ
    сроку
    - метаданные плюс проба плюс 5, то есть до 65 с, - и худший обход стоил человеку около
    245 с вместо объявленных 180. Платит за это зритель ожиданием картинки.

    Проверяется тут ровно ожидание: раздача не отвечает никогда, часы поддельные, а срок
    фазы кончается через секунду после того, как ожидание началось.
    """
    clock = _FakeClock()
    bench = Bench(cast(Any, _FakeTorrServer()), clock=clock)
    prep = _Prep(number=1, release=rel(), started=clock.now, phase="метаданные")
    prep.ready = cast(Any, _Sleeper(clock))

    began = clock.now
    with Progress(out=io.StringIO()) as progress:
        bench._wait(prep, progress, limit=clock.now + 1.0)
    waited = clock.now - began

    assert waited < bench.meta_budget + bench.probe_budget, (
        f"ждали {waited:.1f} с - это срок раздачи, а потолок фазы кончился через секунду"
    )
    assert waited <= 1.5, f"ждали {waited:.1f} с сверх потолка фазы"
    assert prep.error, "недождавшаяся подготовка обязана назваться неудачей, а не тишиной"


def test_a_timed_out_walk_does_not_speak_for_the_queue_it_never_reached() -> None:
    """🔴 TC-435. Встали по часам - молчание приписывается только тронутым.

    Замер TC-424: обход «Дюны» (пул 134, очередь 89) встал по потолку фазы на 60-й
    раздаче и кончился строкой «годного релиза нет (...): выбери руками». Негодных
    среди них не нашли ни одной - ни одна не отозвалась вовсе, - и отказ обязан
    называть это молчанием роя. Ровно так же он обязан не выдавать за молчание те 29
    раздач очереди, до которых обход не дошёл, и не звать выбирать их номером.
    """
    alive = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    heavy = [rel(name=f"жирный{i}", size_gb=40.0, seeders=10 - i) for i in range(2)]
    ranked = alive + heavy
    prober = _probes(ranked, "h264")
    torrserver = _FakeTorrServer(dead={f"hash-magnet-r{i}" for i in range(3)})

    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, torrserver), prober=prober, pick_budget=0.0), ranked)

    msg = str(caught.value)
    assert "раздач в выдаче 5, потрогали 1 из очереди 3" in msg, msg
    assert "играть нечего" not in msg, "двое в очереди не тронуты - за них не говорим"
    assert "выбери руками" not in msg and "--release" not in msg
    assert "годного релиза нет" not in msg


def test_a_fully_walked_queue_of_dead_swarms_is_an_honest_dead_swarm(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Очередь пройдена до конца, а ни одна раздача не отозвалась - это не «годного нет».

    Отказы разные, и человеку с ними разное. «Годного релиза нет» зовёт выбрать руками, но
    выбирать не из чего: раздачи есть и по именам годны, только рой у всех до одной молчит -
    ни метаданных, ни потока. Это не выбор качества, это отсутствие показа, и говорить о нём
    надо прямо. Отличие от :func:`test_the_walk_down_the_queue_stops...`: там встали по
    бюджету и ниже могли лежать живые, а тут очередь именно кончилась.

    «Пиров нет» тут при этом не говорится: сиды у раздач как раз числятся - сотня, - и
    молчание роя с пустой выдачей путать нельзя
    (:func:`~torrcast.usecases.discover.silent_swarm.silent_swarm`).

    🔴 TC-300. Строк на три раздачи тут четыре: перед отказом лучший из промолчавших
    спрашивается ещё раз, один и без отсрочек
    (:meth:`~torrcast.usecases.select_bench.bench.Bench._recheck`). Рой этой картины мёртв
    по-настоящему, второй спрос это подтверждает - и отказ остаётся ровно тем же, что был, вместе со
    всеми своими числами.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "h264")
    torrserver = _FakeTorrServer(dead={f"hash-magnet-r{i}" for i in range(3)})

    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    msg = str(caught.value)
    assert "раздач в выдаче 3, потрогали 3 (все)" in msg and "ни одна не отозвалась" in msg
    assert "до 100" in msg, "сиды называются как обещание индексера, а не как факт"
    assert "пиров нет" not in msg, "пиры числятся - врать про пустую выдачу нельзя"
    assert "годного релиза нет" not in msg
    printed = capsys.readouterr().out
    assert printed.count("не дождались") == 3, "обход называет три окончившихся ожидания"
    assert printed.count("нет пиров") == 1, "повторный полный спрос называет свой итог"
    assert "релиз 1 молчит и в одиночку" in printed, "второй спрос тоже стоит строки"


class _Impatient(_FakeTorrServer):
    """Рой отзывается, но не в отсрочку: за отсрочку у него ни одного контакта, за полный
    бюджет раздачи - метаданные целиком.

    Так выглядит живая раздача, которую очередь считает мёртвой: отсрочка обрывает её
    втрое раньше её собственного бюджета (:data:`~torrcast.domain.rank_settings.PEER_GRACE`), и
    очередь доходит до конца, ни разу никого не дослушав.
    """

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        if grace > 0:
            raise SwarmError(f"рой пуст - за {grace:.0f} с ни одного пира")
        return self.files


def test_a_queue_that_went_silent_to_the_end_gets_one_patient_ask_and_reaches_the_living(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-300. Промолчавшая целиком очередь - не приговор картине: спрашиваем ещё раз.

    Отсрочки на первый контакт заведены ради очереди: пока в ней есть кого спросить,
    ошибка отсрочки стоит одного места. Когда промолчали ВСЕ, ошибка стоит показа, а
    бюджет фазы при этом не потрачен и наполовину - и лучший из промолчавших
    спрашивается ещё раз, один и по полному бюджету раздачи.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "h264")
    torrserver = _Impatient()

    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 1, "терпеливый второй спрос дошёл до живой раздачи"
    assert printed.count("не дождались") == 3, "каждая осечка честно называет наше ожидание"
    assert (
        "промолчала вся очередь (3) - спрашиваю релиз 1 ещё раз, одного и без отсрочек "
        "(жду до 60 с)" in printed
    )


def test_a_patient_ask_that_gets_a_verdict_does_not_report_silent_swarm() -> None:
    """Полный второй спрос ответил приговором - рой уже нельзя называть молчащим."""
    ranked = [rel(name="r0", seeders=100)]
    prober = _probes(ranked, "av1")

    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, _Impatient()), prober=prober), ranked, recode_at=0.0)

    msg = str(caught.value)
    assert "годного релиза нет" in msg and "av1" in msg
    assert "рой" not in msg and "зайди позже" not in msg


def test_an_exhausted_queue_does_not_offer_a_release_that_was_already_rejected() -> None:
    """Все номера проверены и отвергнуты - ручной выбор не является ходом."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(2)]
    prober = _probes(ranked, "av1", "av1")

    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked, recode_at=0.0)

    msg = str(caught.value)
    assert "годного релиза нет" in msg and "av1" in msg
    assert "выбери руками" not in msg and "--release" not in msg
    assert "назови картину иначе" in msg


def test_the_patient_ask_is_not_made_when_the_phase_budget_cannot_cover_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Второй спрос живёт внутри прежнего потолка фазы, а не сверх него.

    Потолок (:data:`~torrcast.domain.pick_settings.PICK_BUDGET`) заводился не зря: человек сидит у
    консоли. Остатка меньше худшей цены спроса - спроса и нет, отказ приходит как приходил.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "h264")
    torrserver = _Impatient()

    with pytest.raises(NotFoundError) as caught:
        # На обход часов фазы хватает, а на второй спрос - уже нет.
        _resolve(Bench(cast(Any, torrserver), prober=prober, pick_budget=1.0), ranked)

    printed = capsys.readouterr().out
    assert "потрогали 3 (все)" in str(caught.value)
    assert "ещё раз" not in printed, "бюджет фазы второго спроса не покрывает - его и нет"


def test_the_patient_ask_goes_to_the_release_the_swarm_silenced_not_to_a_judged_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Терпение достаётся тому, про кого мы ничего не узнали, а не тому, про кого узнали всё.

    Раздача, у которой метаданные приехали, а нужного файла в ней не оказалось, второму
    спросу не подлежит: её ответ не изменится ни от какого терпения. Спрашивается первая
    из тех, кого оборвал рой.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "h264")

    class _Mixed(_Impatient):
        """Верх метаданные отдаёт мгновенно, остальные молчат до полного бюджета."""

        def wait_files(
            self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
        ) -> list[TorrFile]:
            if torrent_hash == "hash-magnet-r0":
                return self.files
            return super().wait_files(torrent_hash, timeout, grace)

    def choose(plan: Any, release: Release, files: list[TorrFile]) -> TorrFile:
        if release.raw_name == "r0":
            raise NotFoundError("серии s1e1 в этой раздаче нет (серий не нашлось)")
        return files[0]

    torrserver = _Mixed()
    prep = _resolve(Bench(cast(Any, torrserver), choose=choose, prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 2, "терпеливо спросили того, кого оборвал рой"
    assert "спрашиваю релиз 2 ещё раз" in printed
    assert "спрашиваю релиз 1" not in printed, "про верх известно всё - терпеть тут нечего"


def test_a_patient_verdict_rewrites_the_reason_of_the_release_that_was_reasked() -> None:
    """Повторный спрос исправляет строку именно того релиза, которому он достался."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(2)]
    prober = _probes(ranked, "h264", "av1")

    class _Mixed(_Impatient):
        def wait_files(
            self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
        ) -> list[TorrFile]:
            if torrent_hash == "hash-magnet-r0":
                return self.files
            return super().wait_files(torrent_hash, timeout, grace)

    def choose(plan: Any, release: Release, files: list[TorrFile]) -> TorrFile:
        if release.raw_name == "r0":
            raise NotFoundError("серии s1e1 в этой раздаче нет")
        return files[0]

    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, _Mixed()), choose=choose, prober=prober), ranked, recode_at=0.0)

    msg = str(caught.value)
    assert "1 - серии s1e1 в этой раздаче нет" in msg
    assert "2 - av1" in msg, msg


@pytest.mark.parametrize(
    ("failure", "silenced"),
    [
        (SwarmError("рой молчит"), True),
        (NotFoundError("файл не найден"), False),
        (ServerDownError("служба не отвечает"), False),
        (InfraError("новый инфраструктурный отказ"), False),
    ],
)
def test_a_failure_explicitly_names_whether_the_swarm_was_silent(
    failure: InfraError | NotFoundError, silenced: bool
) -> None:
    """Новый вид инфраструктурного отказа не получает судьбу роя по наследованию."""
    prep = _Prep(number=1, release=rel(), failure=failure)

    assert _silenced(prep) is silenced


def test_a_disc_image_verdict_is_not_asked_twice(capsys: pytest.CaptureFixture[str]) -> None:
    """Приговор «образ диска» - не молчание роя: второй спрос дал бы ровно тот же ответ.

    Раздача, у которой метаданные приехали целиком и видеофайла в ней не оказалось,
    осуждена, а не промолчала: про неё известно всё, и терпение её ответа не изменит.
    Опознаётся это ТИПОМ отказа (:func:`torrcast.usecases.select._verdict._silenced`), а типом тут
    обязан быть тот же, что у «нужной серии нет»
    (:func:`torrcast.adapters.stream_probe.pick_video_file.pick_video_file` поднимает его на пути
    настоящего прогрева, без всякого подставного ``choose``).
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(2)]
    prober = _probes(ranked, "h264")
    # Рой у верха ЖИВОЙ: метаданные приехали, а внутри - образ диска, видеофайла нет.
    disc = _FakeTorrServer(files=[TorrFile(0, "movie.iso", 25 * GB)])

    # У второй рой мёртв - она промолчала по-настоящему, и переспрашивать надо её.
    class _HalfDead(_FakeTorrServer):
        def wait_files(
            self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
        ) -> list[TorrFile]:
            if torrent_hash == f"hash-{ranked[1].magnet}":
                raise SwarmError(f"раздача не отдала метаданные за {timeout:.0f} с - нет пиров")
            return self.files

    torrserver = _HalfDead(files=disc.files)
    with pytest.raises(NotFoundError):
        _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert "релиз 1 не годится (в раздаче нет отдельного видеофайла" in printed
    assert "спрашиваю релиз 2 ещё раз" in printed, "переспрашивается промолчавший"
    assert "спрашиваю релиз 1" not in printed, "осуждённый второго спроса не получает"
    assert printed.count("отдельного видеофайла") == 1, "приговор звучит ровно один раз"


def test_a_disc_image_verdict_is_not_reported_as_a_silent_swarm() -> None:
    """🔴 TC-399. «В раздаче нет видеофайла» - приговор, а не молчание роя.

    По запросу «lain» выдача состояла из одной раздачи - самиздатовского журнала
    «lainzine 1-5». Осмотр честно ответил «отдельного видеофайла нет», а итоговый отказ
    советовал «зайди позже - рой может ожить», хотя рой был ни при чём: метаданные
    приехали, про раздачу известно всё, и ожить ей не поможет ничто. Отказ обязан
    назвать причину, а не роем её прикрывать.
    """
    ranked = [rel(name="r0", seeders=100)]
    prober = _probes(ranked, "h264")

    def choose(plan: Any, release: Release, files: list[TorrFile]) -> TorrFile:
        raise NotFoundError("в раздаче нет отдельного видеофайла (похоже на образ диска)")

    torrserver = _FakeTorrServer()
    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, torrserver), choose=choose, prober=prober), ranked)

    msg = str(caught.value)
    assert "годного релиза нет" in msg and "нет отдельного видеофайла" in msg
    assert "зайди позже" not in msg, "рой тут ни при чём - обещать его пробуждение нельзя"
    assert "не отозвалась" not in msg, "раздача отозвалась: приговор, а не молчание"


def test_an_explicitly_named_release_is_played_as_asked_with_a_loud_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--release N` неприкосновенен: проверка кодека его не подменяет. Не h264 — громкая
    строка и показ того, что просили.

    🔴 Строка изменилась вместе с решением: раньше тут печаталось «внимание: видео av1 -
    ресивер может не взять, а мы не перекодируем», и это было ровно то враньё, из-за
    которого AV1 и VP9 уезжали на приёмник копией в mpegts. Копией их не отдаём вовсе
    (:meth:`torrcast.domain.profile.Profile.verdict`): раз человек назвал релиз руками, он идёт
    сплошным перекодом, и об этом сказано вслух.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "av1")
    torrserver = _FakeTorrServer()

    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked, release=1)

    printed = capsys.readouterr().out
    assert (prep.number, prep.found.video) == (1, "av1"), "названный релиз не подменяется"
    assert "видео av1 - перекодирую на ходу целиком" in printed
    assert "не перекодируем" not in printed and not re.search(r"беру \d", printed)
    assert not torrserver.dropped, "раздача остаётся: её и просили"


def test_a_named_hevc_release_is_not_a_warning_but_a_promise_to_recode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--release N` с HEVC внутри: обещание перекода, а не «мы не перекодируем».

    Ровно тут и жила латентная петля: строка про «не перекодируем» врала наполовину —
    показ шёл, тяжёлые куски перекодировались, лёгкие уезжали HEVC как есть, и приёмник
    вставал намертво на границе первого такого куска.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "hevc")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked, release=1)

    printed = capsys.readouterr().out
    assert prep.number == 1
    assert "видео hevc - перекодирую на ходу целиком" in printed
    assert "не перекодируем" not in printed


#: Кодеки, которых мы не берём на себя, по одному на релиз: перекод целиком замерен для
#: HEVC (:data:`torrcast.domain.probe_settings.RECODE_CODECS`), а av1/vc1/vp9/mpeg2video остаются
#: честным отказом. Раздаются на ВСЮ очередь: играбельный релиз ниже по списку отбор теперь
#: дочерпывает (TC-188), и «годного нет» обязано означать, что годного правда нет.
REFUSED = ("av1", "mpeg2video", "vc1", "vp9", "av1")


def test_a_queue_of_failed_probes_ends_with_an_honest_exit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ни один релиз очереди не дал играбельного видео - код 1 с объяснением."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(5)]
    prober = _probes(ranked, *REFUSED)
    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)
    assert "годного релиза нет" in str(caught.value)
    assert "1 - av1" in str(caught.value) and "3 - vc1" in str(caught.value)
    assert len(re.findall(r"беру \d", capsys.readouterr().out)) == 4  # очередь пройдена


def test_cheap_verdicts_do_not_eat_the_place_of_the_living_release_below(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-188. Живой 1080p за тремя заведомо худшими: до него обязаны дойти.

    Замер каталога: из 92 живых 1080p, прошедших мимо показа, 44 просто СТОЯЛИ В
    ОЧЕРЕДИ. Съедали их места вот такие три - SD-рип, vp9, av1: ffprobe читает их
    за секунду и тут же отбраковывает, человеку такой приговор не стоит почти ничего,
    а место в очереди он занимал ровно как приговор тяжёлому ремуксу.

    Здесь три приговора подряд стоят долей секунды (:class:`_FakeTorrServer` отвечает
    сразу), то есть весь :data:`~torrcast.domain.pick_settings.VERDICT_BUDGET` остаётся нетронутым,
    и четвёртая раздача - названный 1080p - обязана быть спрошена.
    """
    ranked = [
        rel(name="SD-рип", quality="480p", seeders=90),
        rel(name="старьё", quality="576p", seeders=80),
        rel(name="av1", seeders=70),
        rel(name="честный 1080p", seeders=60),
    ]
    prober = _probes(ranked, "vp9", "vp9", "av1", "h264")

    began = time.monotonic()
    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)
    spent = time.monotonic() - began

    printed = capsys.readouterr().out
    assert prep.number == 4, "три дешёвых приговора - и всё же дошли до живого 1080p"
    assert printed.count("не годится") == 3, "каждый приговор стоит строки, молчаливых нет"
    assert spent < VERDICT_BUDGET, f"дошли за {spent:.1f} с при бюджете приговоров 15 с"


def test_expensive_verdicts_still_stop_the_walk_at_three(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Потолок не снят, а переведён в секунды: дорогие приговоры держат прежние три.

    Бюджет обнулён - значит каждый приговор «дорогой», и отбор обязан вести себя ровно
    как до TC-188: три приговора и честный отказ, даже когда ниже стоит играбельный.
    Иначе правка была бы не «считаем цену», а «подняли потолок».
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(5)]
    prober = _probes(ranked, "av1", "mpeg2video", "vc1")

    with pytest.raises(NotFoundError) as caught:
        # Бюджет приговоров обнулён - каждый из них «дорогой».
        bench = Bench(cast(Any, _FakeTorrServer()), prober=prober, verdict_budget=0.0)
        _resolve(bench, ranked)

    assert "годного релиза нет" in str(caught.value)
    assert len(re.findall(r"беру \d", capsys.readouterr().out)) == 2, "не больше MAX_TRIES"


def test_the_healthy_case_pays_nothing_for_the_deeper_walk(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Верх годен - очередь не трогается вовсе, и путь к картинке той же длины.

    Цена правки обязана быть нулевой там, где приговоров нет ни одного: секундомер
    считает только ожидание осуждённых, а годный верх не осуждается.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(5)]
    prober = _probes(ranked, "h264")

    began = time.monotonic()
    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)
    spent = time.monotonic() - began

    assert prep.number == 1
    assert "не годится" not in capsys.readouterr().out
    assert spent < 1.0, f"здоровый случай занял {spent:.2f} с"


def test_vp9_is_refused_at_the_pick_like_av1_and_never_reaches_the_packer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 VP9 - честный отказ отбора, а не молчаливая копия в mpegts.

    До этого VP9 не спасало ничто: в наборе кодеков на сплошной перекод стоял один
    ``hevc``, белого списка копии упаковка не спрашивала вовсе, и раздача уезжала на
    приёмник как есть - ``LOAD`` не взят, ``IDLE/ERROR``, чёрный экран.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "vp9", "h264")

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)

    assert (prep.number, prep.found.video) == (2, "h264"), "берём тот, про который знаем всё"
    assert "релиз 1 не годится (vp9) - беру 2" in capsys.readouterr().out


def test_warmup_leaves_in_torrserver_only_what_we_play() -> None:
    """Прогрев греет лишнее по определению — лишнее убирается до старта показа.

    Иначе две-три чужие раздачи продолжали бы качаться в RAM-кэш TorrServer рядом с
    показом и отъедать у него полосу.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "h264")
    torrserver = _FakeTorrServer()
    bench = Bench(cast(Any, torrserver), prober=prober)

    prep = _resolve(bench, ranked)
    # Запасной релиз греется в своём потоке, и resolve на подделках отвечает за
    # микросекунды - раньше, чем тот успевает дойти до TorrServer. Хэша в прогреве тогда
    # ещё нет, и keep_only нечего сносить: в полном прогоне планировщик изредка нарезал
    # потоки именно так, и проверка ниже валилась на ровном месте. Дожидаемся прогрева
    # явно: событие ready поток ставит всегда (_work, ветка finally), так что ожидание
    # конечное, а не гадание на таймере.
    for other in bench.preps.values():
        if other is not prep:
            assert other.ready.wait(timeout=10), "запасной прогрев обязан ответить"
    bench.keep_only(prep)

    assert len(bench.preps) > 1, "запасной релиз греется заранее"
    assert len(torrserver.dropped) == len(bench.preps) - 1
    assert prep.torrent_hash not in torrserver.dropped


def test_warmup_spares_a_release_a_parallel_show_holds(tmp_path: Path) -> None:
    """Рядом идёт показ, а параллельный ``cast`` греет ту же выдачу: ``add`` идемпотентен,
    и раздача живого показа попадает в прогрев. Уборка прогрева обязана её пощадить -
    снос выдернул бы источник из-под экрана. Хозяина видно по записи состояния.
    """
    from torrcast.adapters.filesystem.state.state import State
    from torrcast.domain.entry import Entry

    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    torrserver = _FakeTorrServer()
    bench = Bench(cast(Any, torrserver))
    chosen = _Prep(number=1, release=ranked[0], torrent_hash="hash-play")
    held = _Prep(number=2, release=ranked[1], torrent_hash="hash-parallel")
    cold = _Prep(number=3, release=ranked[2], torrent_hash="hash-cold")
    bench.preps = {("movie:кино:1999", p.number): p for p in (chosen, held, cold)}

    state = State()
    state.put("movie:кино:2022", Entry(title="Кино", magnet="m", torrent="hash-parallel"))
    state.save()

    bench.keep_only(chosen)

    assert "hash-parallel" not in torrserver.dropped, "раздачу живого показа не сносим"
    assert torrserver.dropped == ["hash-cold"], "холодный прогрев убираем как прежде"


def test_voice_cleanup_spares_a_release_a_parallel_show_holds() -> None:
    """``cast --voice`` на играющий фильм поднимает ту же раздачу (``add`` идемпотентен).
    Не пригодилась - убираем свою, но не ту, что держит живой показ.
    """
    from torrcast.adapters.filesystem.state.state import State
    from torrcast.domain.entry import Entry

    dropped: list[str] = []

    def release(_config: Any, hashes: list[str]) -> None:
        dropped.extend(hashes)

    config = load_config()

    state = State()
    state.put("movie:кино:2022", Entry(title="Кино", magnet="m", torrent="hash-live"))
    state.save()

    _Voiced(torrent_hash="hash-live").drop(config, release)
    assert dropped == [], "раздачу живого показа cast --voice не трогает"

    _Voiced(torrent_hash="hash-cold").drop(config, release)
    assert dropped == ["hash-cold"], "свою неиспользованную раздачу убираем как прежде"


def test_a_seeded_avi_no_longer_wins_the_top() -> None:
    """Живая выдача по «Моане 2»: 221 сид против 140 — и всё равно не дефолт.

    Первым стоял ``Моана 2 … WEB-DL] Dub (MovieDalen)``, 1.46 ГБ: в заголовке ни кодека,
    ни разрешения, а внутри ``Moana.2.2024.WEB-DLRip.ELEKTRI4KA.avi`` — mpeg4, который
    ffprobe закономерно отбраковывал, потратив 2–5 с живого старта.
    """
    avi = rel(
        name="Моана 2 / Moana 2 [2024, США, Канада, мультфильм, приключения,WEB-DL] Dub",
        codec=None,
        quality=None,
        size_gb=1.46,
        seeders=221,
    )
    avc = rel(
        name="Моана 2 / Moana 2 [2024, США, Канада, мультфильм, WEB-DL-AVC] 2x Dub",
        size_gb=3.14,
        seeders=140,
    )
    ranked = rank_releases([avi, avc], RUNTIME, 20.0)
    assert ranked[0] is avc, "верх - годный WEB-DL-AVC"
    assert ranked[1] is avi, "и всё же не выкинут: судья по-прежнему ffprobe"
    assert is_dated(avi, RUNTIME) and not is_dated(avc, RUNTIME)


def test_a_named_codec_no_longer_hides_an_sd_rip() -> None:
    """``BDRip-AVC`` на 1.46 ГБ — это 720×304, и названный кодек его больше не выгораживает.

    Замер по живой выдаче: ровно такие раздачи стояли верхом у «Тёмного рыцаря:
    Возрождение легенды» (58 сидов), «Форреста Гампа» (105) и «Зелёной мили» (64) —
    и у каждой рядом лежал названный 1080p. Про разрешение кодек не говорит ничего.
    """
    named = rel(name="BDRip-AVC", quality=None, size_gb=1.46, seeders=131)
    assert is_dated(named, RUNTIME)


def test_a_named_resolution_is_never_argued_with_by_size() -> None:
    """Разрешение в имени эвристику отключает: спорить с ним — работа ffprobe, не размера.

    Скромный битрейт при названном 720p — это законный компактный рип, а не старьё;
    а если имя всё-таки соврало, подмену сделает :func:`understated` по факту кадра.
    """
    named = rel(name="BDRip-AVC 720p", quality="720p", size_gb=1.46, seeders=131)
    assert not is_dated(named, RUNTIME)


def test_a_series_pack_is_judged_by_the_size_of_one_episode() -> None:
    """У сериала в раздаче лежит сезон целиком — делить надо на серии, а не на фильм.

    Пока делили целиком, .avi-эвристика для сериалов не работала вовсе: «6 ГБ» на восемь
    серий это 1.7 Мбит/с на серию, а как один фильм — 6.6, то есть выше порога SD, и
    старьё спокойно стояло верхом отбора. Счёт серий берётся из имени раздачи.
    """
    runtime = RUNTIME_GUESS["tv"]
    old = parse_release_name("Сериал / Series [01-08 of 8] (2001) SATRip")
    good = parse_release_name("Сериал / Series [01-08 of 8] (2001) WEB-DL")
    fat = parse_release_name("Сериал / Series [01-08 of 8] (2001) WEB-DL")
    fat = replace(fat, size=int(80 * GB), seeders=5)
    old, good = replace(old, size=int(2 * GB), seeders=900), replace(good, size=int(60 * GB))

    assert old.episode_count == 8 and good.episode_count == 8
    fat_rate = bitrate_of(fat, runtime)
    assert fat_rate is not None, "у раздачи с размером битрейт есть - иначе сравнивать нечего"
    assert bitrate_of(good, runtime) == pytest.approx(fat_rate * 0.75, rel=0.01), (
        "битрейт считается на серию: 60 ГБ на восьмерых против 80 ГБ на восьмерых"
    )
    assert is_dated(old, runtime), "0.25 ГБ на серию - это SD, сколько бы сидов ни было"
    assert not is_dated(good, runtime)
    assert rank_releases([old, good], runtime, 40.0)[0] is good


def test_a_film_collection_is_judged_by_the_part_that_will_play() -> None:
    """Вес сборника делится на фильмы, а не сравнивается с одним фильмом целиком."""
    trilogy = replace(
        parse_release_name("Матрица: Трилогия / The Matrix (1999-2003) BDRip 1080p"),
        size=int(28.6 * GB),
    )
    collection = replace(
        parse_release_name("Матрица: Коллекция / The Matrix (1999-2003) BDRip 1080p"),
        size=int(28.6 * GB),
    )
    assert trilogy.collection_count == 3
    assert bitrate_of(trilogy, 120 * 60) == pytest.approx(11.4, abs=0.1)
    assert bitrate_of(collection, 120 * 60) is None
    assert is_candidate(collection, 120 * 60, 16.0)


def test_a_series_pack_that_does_not_count_its_episodes_is_left_to_ffprobe() -> None:
    """Имя не считает серии — делить не на что, и оценки не будет: врать себе хуже.

    🔴 TC-344. Ответ прикидки тут - ``None``, «не знаю», а не ноль: ноль ворота
    читали как «ниже любого порога», то есть как «лёгкий и безопасный», и молчание
    имени выходило за подтверждённый вес. Такую раздачу («Локи [S01] WEB-DL», сколько
    внутри серий — знают только файлы) по-прежнему судит ffprobe уже после выбора, с
    отбраковкой и переходом к следующей - в отказ незнание не превращается нигде.
    """
    silent = replace(
        parse_release_name("Локи / Loki [S01] (2021) WEB-DL"), size=int(8 * GB), seeders=24
    )
    assert silent.kind == "tv" and silent.episode_count == 0
    assert bitrate_of(silent, RUNTIME_GUESS["tv"]) is None
    assert not is_dated(silent, RUNTIME_GUESS["tv"])
    assert is_candidate(silent, RUNTIME_GUESS["tv"], 16.0), "не знаю - это не отказ"


def test_unknown_weight_is_not_light_weight_at_the_extras_gate() -> None:
    """🔴 TC-344. У приложения-сериала без счёта серий вес молчит - и ворота молчат.

    Раньше прикидка отдавала ноль, и ворота приложений читали его как «лёгкий»:
    сериальная раздача с меткой приложения выкидывалась по весу, которого у неё нет.
    Метка сама по себе раздачу только топит под картину (:func:`rank_releases`).
    Однозначная метка («дополнительные материалы») судит и без веса - это TC-339.
    """
    tv = RUNTIME_GUESS["tv"]
    extra = replace(
        parse_release_name("Локи / Loki [S01] (2021) WEB-DL | за кадром"),
        size=int(0.4 * GB),
        seeders=3,
    )
    sure = replace(
        parse_release_name("Локи / Loki [S01] (2021) WEB-DL | Дополнительные материалы"),
        size=int(18 * GB),
        seeders=3,
    )
    assert extra.extras and bitrate_of(extra, tv) is None
    assert not is_extra(extra, tv), "вес молчит - ворота молчат, топит только порядок"
    assert sure.extras_sure and bitrate_of(sure, tv) is None
    assert is_extra(sure, tv), "однозначной метке вес не нужен ни в какую сторону"


def test_dated_sinks_below_candidates_but_above_hevc() -> None:
    """Ступень «старьё» вклинена МЕЖДУ годностью и сидами, группы местами не меняются.

    Случай живой: у «Матрицы: Перезагрузка» ``DVDRip-AVC`` на 47 сидов
    стоял первым и обгонял HDTV-мастер на 30. Кодек назван, значит релиз годный и из
    очереди не выпадает; но верхом ему быть больше не с чего.
    """
    dated = Release(
        raw_name="DVDRip-AVC", title="Кино", codec="H.264", source="DVDRip",
        size=3 * GB, seeders=900,
    )  # fmt: skip
    good = rel(name="web-dl", seeders=10)
    hevc = rel(name="hevc", codec="HEVC", seeders=800)
    disc = rel(name="Кино (1999) DVD-Video", seeders=999)
    order = [r.raw_name for r in rank_releases([disc, dated, hevc, good], RUNTIME, 20.0)]
    assert order == ["web-dl", "DVDRip-AVC", "hevc", "Кино (1999) DVD-Video"]
    assert is_candidate(dated, RUNTIME, 20.0), "старьё остаётся годным - судит ffprobe"


def test_a_name_that_admits_sd_sinks_below_any_hd() -> None:
    """«480p» в имени — не повод для спора: раздача сама сказала, что она не HD.

    SD играется, только если HD в каталоге нет вовсе; сиды этого не отменяют.
    """
    sd = rel(name="WEB-DL 480p", codec=None, quality="480p", size_gb=1.2, seeders=400)
    hd = rel(name="WEB-DL 720p", codec=None, quality="720p", size_gb=4.0, seeders=12)
    assert is_dated(sd, RUNTIME) and not is_dated(hd, RUNTIME)
    assert rank_releases([sd, hd], RUNTIME, 25.0)[0] is hd
    assert rank_releases([sd], RUNTIME, 25.0)[0] is sd, "другого нет - играем что есть"


def test_an_sd_rip_no_longer_outseeds_the_honest_1080p() -> None:
    """Живая выдача «Тёмного рыцаря»: 58 сидов на 1.47 ГБ против 14 на честном 1080p.

    Ровно этот случай и давал SD-фолбэк: в порядке участвовали одни сиды, а про
    разрешение никто не спрашивал.
    """
    sd = rel(name="BDRip-AVC", quality=None, size_gb=1.47, seeders=58)
    full = rel(name="BDRip 1080p", codec=None, size_gb=7.76, seeders=14)
    assert [r.raw_name for r in rank_releases([sd, full], RUNTIME, 25.0)] == [
        "BDRip 1080p",
        "BDRip-AVC",
    ]


def test_a_live_1080p_beats_a_more_seeded_720p() -> None:
    """«Мастер и Маргарита»: ``WEB-DL 720p`` со 146 сидами уступает ``WEB-DL 1080p`` с 59."""
    hd = rel(name="WEB-DL 720p", codec=None, quality="720p", size_gb=3.43, seeders=146)
    full = rel(name="WEB-DL 1080p", codec=None, size_gb=7.14, seeders=59)
    assert rank_releases([hd, full], RUNTIME, 25.0)[0] is full
    assert is_full_hd(full, alive=146) and not is_full_hd(hd, alive=146)


def test_a_dead_1080p_does_not_buy_a_step_with_rebuffering() -> None:
    """«Форрест Гамп»: 15 ГБ на двух сидах против 720p на сорока одном — ступень не стоит того.

    Плавность выше пиковой чёткости: поднять такой 1080p значило бы поменять
    разрешение на подгрузы.
    """
    hd = rel(name="BDRip 720p", codec=None, quality="720p", size_gb=14.88, seeders=41)
    full = rel(name="BDRip 1080p", codec=None, size_gb=15.18, seeders=2)
    assert rank_releases([hd, full], RUNTIME, 25.0)[0] is hd
    assert not is_full_hd(full, alive=41)


def test_a_live_1080p_is_not_priced_against_a_dated_pool_leader() -> None:
    """«История игрушек 3»: лидер пула — старьё, и его сиды не цена размена.

    Верх выдачи по сидам держал 126-сидовый ``BDRip-AVC`` на 1.5 ГБ, утопленный своей
    ступенью старья и в споре за верх не участвующий. А знаменатель живости считался
    по нему, и названный 1080p с 30 сидами проигрывал 720p с 55: 30 < 126 × 0.25.
    Против настоящего соперника у него 0.55 — ступень его, и дефолт обязан встать на 1080p.
    """
    dated = rel(name="BDRip-AVC", codec=None, quality=None, size_gb=1.5, seeders=126)
    hd = rel(name="BDRip 720p", codec=None, quality="720p", size_gb=5.3, seeders=55)
    full = rel(name="BDRip 1080p", codec=None, size_gb=7.2, seeders=30)
    assert is_dated(dated, RUNTIME), "лидер пула сидит на ступени старья"
    assert rank_releases([dated, hd, full], RUNTIME, 25.0)[0] is full


def test_a_barely_seeded_1080p_does_not_claim_the_step() -> None:
    """«Сёгун»: 1080p на трёх сидах против 720p на пяти — доля не оживляет не-рой.

    Против пятисидового соседа доля 0.60 формально проходит любой порог, а три сида —
    это подгрузы, и живой 720p честнее: рой, не играбельный сам по себе
    (:data:`~torrcast.domain.rank_settings.ALIVE_SEEDERS`), ступенью качества не лечится.
    """
    full = rel(name="BDRip 1080p", codec=None, size_gb=7.2, seeders=3)
    hd = rel(name="BDRip 720p", codec=None, quality="720p", size_gb=5.3, seeders=5)
    assert rank_releases([full, hd], RUNTIME, 25.0)[0] is hd
    assert not is_full_hd(full, alive=5)


def test_a_live_1080p_is_not_priced_against_a_pool_leader_on_the_recode_step() -> None:
    """«Тачки 2»: лидер пула — тяжеляк, играбельный только сплошным перекодом.

    Верх выдачи по сидам держал ремукс на 71 сид, утопленный своей ступенью веса
    (:func:`~torrcast.usecases.rank.needs_whole_recode.needs_whole_recode`) и в споре за верх не
    участвующий. А знаменатель живости считался по нему, и русский 1080p-дубляж с 11 сидами
    проигрывал русскому же 720p с тринадцатью: 11 < 71 × 0.25. Против настоящего соперника у него
    0.85 — ступень его, и дефолт обязан встать на 1080p.
    """
    heavy = rel(name="BDRemux 1080p", codec=None, size_gb=45.0, seeders=71)
    hd = rel(name="BDRip 720p", codec=None, quality="720p", size_gb=5.3, seeders=13)
    full = rel(name="BDRip 1080p", codec=None, size_gb=7.2, seeders=11)
    assert needs_whole_recode(heavy, RUNTIME, 25.0), "лидер пула сидит на ступени перекода"
    assert rank_releases([heavy, hd, full], RUNTIME, 25.0)[0] is full


def test_a_lying_1080p_is_still_swapped_by_ffprobe() -> None:
    """Ступень поднимает ОБЕЩАНИЕ, а судит по-прежнему кадр: 1080p в имени, 574p внутри."""
    liar = rel(name="BDRip 1080p", codec=None, size_gb=7.0, seeders=100)
    assert is_full_hd(liar, alive=100)
    assert understated(liar, Media(height=574, width=1150)) == "назван 1080p, на деле 574p"


def test_the_ceiling_is_checked_again_by_the_file_not_by_the_torrent_size() -> None:
    """Потолок 16 Мбит/с ловит «Моану 2» только после ffprobe — до него ловить нечем.

    Прикидка при выборе дефолта делит 13.3 ГБ на типовые два часа и даёт 14.8 Мбит/с,
    то есть релиз проходит как кандидат. А внутри фильм на 1:39:37 — честные
    17.8 Мбит/с, на которых Q70D встаёт в ребуфер. Названный руками
    (``--release N``) берётся по-прежнему: там человек выбрал сам.
    """
    from torrcast.domain.media import Media
    from torrcast.domain.torr_file import TorrFile

    heavy = rel(size_gb=13.3 * 1e9 / GB)  # 13.3 ГБ по-магазинному, как их считает трекер
    assert is_candidate(heavy, RUNTIME, 16.0), "прикидка по раздаче потолок не превышает"

    bench = Bench(cast(Any, _FakeTorrServer()))
    prep = _Prep(number=1, release=heavy)
    prep.video = TorrFile(0, "moana2.mkv", 13_300_000_000)
    prep.media = Media(duration=5977.0, video="h264")

    assert (
        bench._trouble(prep, pinned=False, warn_mbit=16.0)
        == "слишком тяжёлый для приёмника, ~18 Мбит/с"
    )
    assert bench._trouble(prep, pinned=True, warn_mbit=16.0) == "", "руками - берём"
    assert bench._trouble(prep, pinned=False, warn_mbit=20.0) == "", "прежний потолок брал"


def test_the_ceiling_weighs_the_video_track_not_the_ten_dubs_around_it() -> None:
    """Отбраковка считает от паспорта (``Entry.vbps``), а не от размера файла.

    Потолок спрашивает «сколько придётся перекодировать непрерывно», а перекодировать
    придётся картинку: десять озвучек и двенадцать субтитров на ТВ не уезжают вовсе.
    Числа живые: у «Моаны 2» контейнер 19.2 Мбит/с, а видеодорожка — 14.3.
    Паспорт молчит — считаем по размеру, как раньше, иначе 4K-ремукс проедет насквозь.
    """
    from torrcast.domain.media import Media
    from torrcast.domain.torr_file import TorrFile

    bench = Bench(cast(Any, _FakeTorrServer()))
    prep = _Prep(number=1, release=rel(size_gb=13.3 * 1e9 / GB))
    prep.video = TorrFile(0, "moana2.mkv", 13_300_000_000)
    prep.media = Media(duration=5977.0, video="h264", video_bps=14_333_000.0)
    assert bench._trouble(prep, pinned=False, warn_mbit=16.0) == "", "видео 14.3 - годится"

    prep.media = Media(duration=5977.0, video="h264", video_bps=49_900_000.0)
    assert (
        bench._trouble(prep, pinned=False, warn_mbit=25.0)
        == "слишком тяжёлый для приёмника, ~50 Мбит/с"
    )

    prep.media = Media(duration=5977.0, video="h264")  # паспорт молчит - по размеру
    assert (
        bench._trouble(prep, pinned=False, warn_mbit=16.0)
        == "слишком тяжёлый для приёмника, ~18 Мбит/с"
    )


def _franchise_plan(
    title: str, year: int | None, releases: list[Release], kind: Kind = "movie"
) -> Any:

    return Plan(
        picture=Picture(title=title, year=year, kind=kind, releases=releases),
        ranked=rank_releases(releases, RUNTIME, 20.0),
        runtime=RUNTIME,
        warn_mbit=20.0,
    )


def _moana_franchise() -> list[Any]:
    """Франшиза «моана» из живой выдачи, сведённая к верху отбора каждой картины."""
    return [
        _franchise_plan(
            "Моана: романтика золотого века",
            1926,
            [rel(name="vhs", codec=None, quality=None, size_gb=0.71, seeders=5)],
        ),
        _franchise_plan("Моана", 2016, [rel(name="web-dl 1080p", size_gb=4.17, seeders=222)]),
        _franchise_plan(
            "Моана 2", 2024, [rel(name="web-dl-avc", quality=None, size_gb=3.14, seeders=140)]
        ),
    ]


def _cars_franchise() -> list[Any]:
    """Франшиза «тачки» из живой выдачи: у каждой картины верх её отбора.

    «Тачки 2» стоят тут двумя релизами не для красоты: обсиженный BD-ремукс на 38.4 ГБ
    выше потолка отбора, а второй релиз - 0.4-гигабайтный HDRip «фильм о фильме» с одним
    сидом. Играть картине нечем, и сказать это обязаны ДВЕ ступени независимо: ворота
    отбора (🔴 TC-290: ролик о съёмках не кандидат вовсе) и порог живости
    (:data:`~torrcast.domain.rank_settings.ALIVE_SEEDERS`: один сид - не рой). Ступени намеренно не
    выброшены одна ради другой: у ворот на такой случай есть и другой ответ - раздача,
    которая и правда картина, просто мёртвая.
    """
    return [
        _franchise_plan(
            "Тачки", 2006, [rel(name="Cars 2006 BluRay 1080p x264", size_gb=7.06, seeders=66)]
        ),
        _franchise_plan(
            "Тачки: Мультачки. Байки Мэтра",
            2008,
            [rel(name="Cars Toon [DVD9]", codec=None, quality=None, size_gb=5.41, seeders=5)],
        ),
        _franchise_plan(
            "Тачки 2",
            2011,
            [
                rel(name="Cars 2 [HDRip] фильм о фильме", quality=None, size_gb=0.40, seeders=1),
                rel(name="Cars 2 [BDRemux 2160p]", quality="2160p", size_gb=38.4, seeders=126),
            ],
        ),
        _franchise_plan(
            "Тачки 3", 2017, [rel(name="Cars 3 WEB-DL 1080p", size_gb=4.59, seeders=121)]
        ),
    ]


def test_menu_default_is_the_first_living_picture_of_the_franchise() -> None:
    """Живая выдача по «тачкам»: смотреть начинают с первой части, и она жива.

    Прежний дефолт «самая живая» печатал `[4]` — «Тачки 3» с 121 сидом. Первая часть
    при этом вполне играбельна: 1080p BluRay на 66 сидов, 0.55 от лидера франшизы.
    """
    plans = _cars_franchise()
    # У «Тачек 2» вес нулевой: ремукс не проходит потолок, а «фильм о фильме» - ворота
    # (🔴 TC-290). Раньше он весил один сид, и картина держалась на ролике о съёмках.
    assert [liveliness(p) for p in plans] == [66, 0, 0, 121]
    assert liveliest(plans) == 4, "прежнее правило и правда уводило на третью часть"
    assert first_alive(plans) == 1


def test_menu_default_steps_over_a_dead_first_picture() -> None:
    """Живая выдача по «моане»: список хронологический, а дефолт — вторым пунктом.

    Первым в хронологии стоит «Моана: романтика золотого века» (1926) — немое
    документальное кино, один VHS-рип на 5 сидов. Enter на ней не давал ничего.
    """
    plans = _moana_franchise()
    assert [liveliness(p) for p in plans] == [0, 222, 140]
    assert liveliest(plans) == 2
    assert first_alive(plans) == 2


def test_a_faint_swarm_does_not_count_as_alive() -> None:
    """Один сид - это не «живая часть», а её отсутствие.

    Порог - свой рой картины (:data:`~torrcast.domain.rank_settings.ALIVE_SEEDERS`). Без него дефолт
    уходил бы на первую попавшуюся картину с хоть каким-то кандидатом.
    """
    plans = _cars_franchise()
    assert first_alive(plans[1:]) == 3, "«Мультачки» и «Тачки 2» мертвы, жива третья"


def _parts(*parts: tuple[str, int, int]) -> list[Any]:
    """Франшиза из троек «название, год, сиды лучшей ГОДНОЙ раздачи картины».

    Раздача у каждой части одна и заведомо играбельная (WEB-DL 1080p, 4.2 ГБ): вопрос
    теста - только про порядок частей и про живость, а не про отбор внутри картины.
    """
    return [
        _franchise_plan(
            title, year, [rel(name=f"{title} {year} WEB-DL 1080p", size_gb=4.2, seeders=seeders)]
        )
        for title, year, seeders in parts
    ]


#: Франшизы, на которых дефолт садился не на ту картину (карточка TC-196): свежая часть
#: с большим роем перевешивала классику, и та объявлялась мёртвой долей от лидера. Числа -
#: форма той поломки (сотни сидов у новинки против живых десятков у первой части), а не
#: расшифровка конкретного прогона; ожидание - номер пункта, который обязан стать дефолтом.
_FRANCHISES: list[tuple[str, list[Any], int]] = [
    (
        "мумия",
        _parts(
            ("Мумия", 1999, 47),
            ("Мумия возвращается", 2001, 33),
            ("Мумия: Гробница Императора Драконов", 2008, 21),
            ("Мумия", 2017, 58),
            ("Мумия", 2026, 604),
        ),
        1,
    ),
    (
        "хищник",
        _parts(
            ("Хищник", 1987, 39),
            ("Хищник 2", 1990, 24),
            ("Хищники", 2010, 31),
            ("Хищник", 2018, 44),
            ("Хищник: Добыча", 2022, 96),
            ("Хищник: Планета смерти", 2025, 488),
        ),
        1,
    ),
    (
        "голодные игры",
        _parts(
            ("Голодные игры", 2012, 52),
            ("Голодные игры: И вспыхнет пламя", 2013, 41),
            ("Голодные игры: Сойка-пересмешница. Часть I", 2014, 28),
            ("Голодные игры: Баллада о певчих птицах и змеях", 2023, 317),
        ),
        1,
    ),
    (
        "дюна",
        _parts(("Дюна", 1984, 26), ("Дюна", 2021, 190), ("Дюна: Часть вторая", 2024, 402)),
        1,
    ),
    (
        "безумный макс",
        _parts(
            ("Безумный Макс", 1979, 18),
            ("Безумный Макс 2: Воин дороги", 1981, 22),
            ("Безумный Макс 3: Под куполом грома", 1985, 15),
            ("Безумный Макс: Дорога ярости", 2015, 356),
        ),
        1,
    ),
    (
        "джуманджи",
        _parts(
            ("Джуманджи", 1995, 63),
            ("Джуманджи: Зов джунглей", 2017, 274),
            ("Джуманджи: Новый уровень", 2019, 198),
        ),
        1,
    ),
    ("тачки", _cars_franchise(), 1),
    ("моана", _moana_franchise(), 2),
]


@pytest.mark.parametrize(
    ("asked", "plans", "expected"), _FRANCHISES, ids=[f[0] for f in _FRANCHISES]
)
def test_the_franchise_default_is_the_first_playable_part(
    asked: str, plans: list[Any], expected: int
) -> None:
    """🔴 TC-196: на голое имя франшизы дефолтом встаёт ПЕРВАЯ ЖИВАЯ часть.

    «Живая» - это «есть чем играть» (свой рой картины), а не «раздаётся лучше всех».
    Прежний порог был долей от самой живой части франшизы, и один свежий релиз с большим
    роем выбивал из живых всю классику: «мумия» давала дефолтом картину 2026 года десять
    прогонов из десяти, «хищник» - «Планету смерти», «дюна» - «Часть вторую».
    """
    picked = first_alive(plans)
    assert picked == expected, f"«{asked}»: дефолт обязан быть [{expected}], а не [{picked}]"
    assert liveliness(plans[picked - 1]) >= ALIVE_SEEDERS or all(
        liveliness(p) < ALIVE_SEEDERS for p in plans
    ), "дефолт стоит на картине, которой нечем играть"


@pytest.mark.parametrize(
    ("asked", "plans", "expected"), _FRANCHISES, ids=[f[0] for f in _FRANCHISES]
)
def test_the_old_share_of_the_liveliest_would_have_missed_the_first_part(
    asked: str, plans: list[Any], expected: int
) -> None:
    """Тот же список под ОТКАЧЕННЫМ правилом: доля от лидера ошибается или совпадает.

    Тест не про будущее поведение, а про то, что фикстуры действительно воспроизводят
    поломку: у шести франшиз карточки первая часть не дотягивала до 0.25 от самой живой
    и дефолт уезжал, у «тачек» и «моаны» доля отвечала верно - их правка и не трогает.
    """
    best = max(liveliness(p) for p in plans)
    survivors = [
        n for n, p in enumerate(plans, start=1) if liveliness(p) >= best * FULL_HD_LIVENESS
    ]
    was_wrong = expected not in survivors
    assert was_wrong == (asked not in {"тачки", "моана"}), (
        f"«{asked}»: доля от лидера оставляла живыми {survivors}"
    )


def test_a_franchise_with_no_life_still_points_somewhere() -> None:
    """Живого нет вовсе — цифра в скобках всё равно обязана на что-то указывать."""
    dead = [
        _franchise_plan("Кино", 2001, [rel(name="dvd9 [DVD9]", quality=None, seeders=2)]),
        _franchise_plan("Кино 2", 2005, [rel(name="dvd5 [DVD5]", quality=None, seeders=1)]),
    ]
    assert [liveliness(p) for p in dead] == [0, 0]
    assert first_alive(dead) == 1


def test_a_picture_with_nothing_playable_weighs_nothing() -> None:
    """«Тачки» 2006 в живой выдаче — 41 ГБ 4K-ремукса (49.9 Мбит/с) и образы DVD.

    Играть нечего, сколько бы сидов ни было: дефолт обязан уйти на картину, которая
    реально запустится.
    """
    fat = _franchise_plan("Тачки", 2006, [rel(name="uhd bdremux", size_gb=41.8, seeders=106)])
    live = _franchise_plan("Тачки 3", 2017, [rel(name="web-dl 1080p", size_gb=4.59, seeders=121)])
    assert liveliness(fat) == 0
    assert liveliest([fat, live]) == 2


def test_an_equal_race_is_won_by_chronology() -> None:
    """Ничья по сидам — берём раннюю картину: список и так хронологический."""
    first = _franchise_plan("Кино", 2001, [rel(name="a", seeders=100)])
    second = _franchise_plan("Кино 2", 2005, [rel(name="b", seeders=100)])
    assert liveliest([first, second]) == 1


def test_a_half_walked_queue_is_not_a_dead_swarm() -> None:
    """Отказ обязан различать «пиров правда нет» и «перебрали три раздачи из пятнадцати».

    Прежняя строка была одна на все случаи - «рой у них мёртв, пиров нет». В замере
    каталога её получили 18 запросов из 225, и у девяти рой был живой: очередь отбора
    просто кончилась раньше выдачи. Числа в строке теперь всегда два.
    """
    pool = [rel(name=f"r{n}", seeders=7 * n) for n in range(15)]
    plan = _plan(pool)
    half = silent_swarm(plan, [1, 2, 3], 3, "1 - тишина")
    assert "раздач в выдаче 15, потрогали 3" in half
    assert "мёртв" not in half, "живой рой мёртвым не называем"
    assert "до 14 сид" in half and "cast releases" in half

    whole = silent_swarm(plan, list(range(1, 16)), 15, "1 - тишина")
    assert "раздач в выдаче 15, потрогали 15 (все)" in whole
    assert "ни одна не отозвалась" in whole and "числятся" in whole


def test_a_walk_cut_by_the_clock_counts_the_queue_it_did_not_reach() -> None:
    """🔴 TC-435. Обход, срезанный потолком фазы, называет оба числа: очередь и тронутых.

    Очередь взяла двенадцать раздач из пятнадцати, а часы кончились на третьей. Сказать
    «потрогали 3 (все)» тут значило бы записать в молчащие девять раздач, которых никто
    не спрашивал, а звать выбрать их номером - выдать за подсказку непроверенное: весь
    бюджет фазы ушёл на тех, кто стоял выше.
    """
    pool = [rel(name=f"r{n}", seeders=7 * n) for n in range(15)]
    said = silent_swarm(_plan(pool), list(range(1, 13)), 3, "1 - тишина")

    assert "раздач в выдаче 15, потрогали 3 из очереди 12" in said
    assert "на остальных не хватило времени" in said
    assert "(все)" not in said and "играть нечего" not in said
    assert "cast releases" not in said and "--release" not in said
    assert "зайди позже" in said, "ход остаётся, но честный"


def test_a_pool_without_a_single_peer_says_so_plainly() -> None:
    """Сидов не числится ни у одной раздачи - вот тут «пиров нет» и есть правда.

    Эталонная пара из живой выдачи: у «Зелёной границы» две раздачи и ноль сид, у
    «Двенадцати обезьян» тридцать раздач и до 105 сид. Формулировки обязаны отличаться.
    """
    border = _plan([rel(name=f"r{n}", seeders=0) for n in range(2)])
    monkeys = _plan([rel(name=f"r{n}", seeders=3 + n) for n in range(30)])
    dead = silent_swarm(border, [1, 2], 2, "1 - тишина")
    live = silent_swarm(monkeys, [1, 2, 3], 3, "1 - тишина")
    assert dead == (
        "раздач в выдаче 2, потрогали 2 - пиров нет ни у одной, показывать нечего: "
        "назови картину иначе или зайди позже - другой запрос соберёт другую выдачу, "
        "а рой может ожить (1 - тишина)"
    )
    assert "пиров нет" not in live
    assert dead != live


def test_every_refusal_leaves_the_person_a_move() -> None:
    """Отказ без хода - тупик: человеку остаётся гадать, что делать дальше.

    Ходы разные, потому что разное осталось непроверенным: пока в выдаче есть нетронутые
    раздачи, ход - ручной выбор; когда потрогали всё, ручной выбор врал бы надеждой, и
    честный ход другой - другой запрос или другое время.
    """
    pool = [rel(name=f"r{n}", seeders=7 * n) for n in range(15)]
    plan = _plan(pool)
    assert "cast releases" in silent_swarm(plan, [1, 2, 3], 3, "1 - тишина"), (
        "нетронутые есть - выбор"
    )
    for said in (
        silent_swarm(plan, list(range(1, 16)), 15, "1 - тишина"),
        silent_swarm(_plan([rel(name="r", seeders=0)]), [1], 1, "1 - тишина"),
    ):
        assert "назови картину иначе" in said and "зайди позже" in said
        assert "--release" not in said, "выбирать не из чего - надежду не предлагаем"


def test_the_seed_count_in_a_refusal_is_about_the_asked_not_the_listing() -> None:
    """🔴 TC-376. «Сидов числится до N» описывало всю выдачу, а спрашивали мы очередь.

    Максимум выдачи (25) лежит на раздаче, которую ворота в очередь не пустили, - и
    число выглядело уликой против роя («числится 25, а молчат»), уликой не будучи.
    Печатаемое число обязано описывать то, что мы правда спрашивали.
    """
    asked = rel(name="r1", seeders=10)
    outsider = rel(name="молчун", quality=None, codec=None, seeders=25)
    plan = _plan([asked, outsider])
    assert not is_candidate(outsider, RUNTIME, 20.0), "молчуна в очередь не пустили"
    said = silent_swarm(plan, [1], 1, "1 - тишина")
    assert "до 10 сид" in said and "25" not in said, "25 сид - не у тех, кого спрашивали"
    assert "cast releases" in said, "молчун пригоден по известным признакам - выбор есть"


def test_a_refusal_does_not_offer_a_pick_from_the_known_unplayable() -> None:
    """🔴 TC-375. Всё нетронутое непригодно по уже известным признакам - выбора нет.

    Замер по сохранённым прогонам (1131 запрос): у отказов с ручным выбором 132
    нетронутые раздачи из 195 не содержали запрошенной серии вовсе, а в семи отказах
    из 42 не содержали её ВСЕ нетронутые. Предлагать выбор из этого - отправить
    человека перебирать то, что играть нельзя, и он вернётся ни с чем.
    """
    pool = [rel(name="r1", seeders=9)]
    pool += [rel(name=f"remux {n}", size_gb=60, seeders=50) for n in range(3)]
    plan = _plan(pool)
    said = silent_swarm(plan, [1], 1, "1 - тишина")
    assert "тяжелее потолка - 3" in said
    assert "cast releases" not in said and "--release" not in said
    assert "назови картину иначе" in said, "ход остаётся, но честный"


def test_a_refusal_names_the_missing_episode_instead_of_a_manual_pick() -> None:
    """🔴 TC-375 для сериала: нетронутые с чужим сезоном - играть в них нечего."""
    first = rel(name="s1 pack", seeders=9)
    strangers = [replace(rel(name=f"s2 pack {n}", seeders=12), season=2) for n in range(2)]
    plan = _plan([first, *strangers])
    plan.series = _Series(want=Episode(1, 1))
    said = silent_swarm(plan, [1], 1, "1 - тишина")
    assert "нужной серии нет - 2" in said
    assert "cast releases" not in said and "--release" not in said
    assert "назови картину иначе" in said


def test_a_refusal_still_offers_a_pick_when_someone_untouched_is_playable() -> None:
    """Непригодна только ЧАСТЬ нетронутого - ручной выбор остаётся честным ходом."""
    asked = rel(name="r1", seeders=9)
    heavy = rel(name="remux", size_gb=60, seeders=50)
    quiet = rel(name="молчун", quality=None, codec=None, seeders=25)
    plan = _plan([asked, heavy, quiet])
    said = silent_swarm(plan, [1], 1, "1 - тишина")
    assert "cast releases" in said, "пригодный нетронутый есть - выбор предлагаем"


def test_a_refusal_after_a_manual_pick_offers_another_release() -> None:
    """``--release N`` уже выбрал релиз: повторить тот же ход отказ не предлагает."""
    asked = rel(name="r1", seeders=9)
    quiet = rel(name="молчун", quality=None, codec=None, seeders=25)
    plan = _plan([asked, quiet])

    said = silent_swarm(plan, [1], 1, "1 - тишина", picked=1)

    assert "выбери другой релиз" in said
    assert "выбери руками" not in said
    assert "cast releases" in said and "--release N" in said


def _series_plan(title: str, year: int, kind: Kind, releases: list[Release]) -> Any:
    """План картины, у которой запрос назвал серию: тип сказан вслух (``s1e1``)."""

    return Plan(
        picture=Picture(title=title, year=year, kind=kind, releases=releases),
        ranked=rank_releases(releases, RUNTIME, 20.0),
        runtime=RUNTIME,
        warn_mbit=20.0,
        asked_series=True,
    )


def test_liveliness_counts_the_best_playable_release_not_the_queue_top() -> None:
    """«Мальтийский сокол» 1941 из живой выдачи: наверху очереди не самая живая раздача.

    Очередь сортируется не сидами одними: 1080p и русская дорожка стоят выше. Наверху
    у картины оказался релиз на 5 сидов, а годный сосед ниже держал 28 - и картина с
    двадцатью двумя раздачами весила меньше однораздачной тёзки 1931 года на 16 сид.
    """
    falcon = _franchise_plan(
        "Мальтийский сокол",
        1941,
        [
            rel(name="Мальтийский сокол BDRip 1080p Дубляж", size_gb=8.0, seeders=5),
            rel(name="The Maltese Falcon BDRip 720p", quality="720p", size_gb=4.0, seeders=28),
        ],
    )
    assert falcon.ranked[0].seeders == 5, "наверху очереди - то, что лучше смотреть"
    assert liveliness(falcon) == 28, "а весит картина по лучшей ГОДНОЙ раздаче"


def test_default_steps_over_a_picture_backed_by_a_single_release() -> None:
    """Живая выдача по «мальтийскому соколу»: дефолт садился на 1931 год одной раздачей.

    Порог живости она проходила честно - 16 сид против 28 у лучшей годной раздачи
    соседки, - но играть ею нечего: одно обещание индексера и никакой очереди за ним.
    Рядом стоит картина 1941 года с двадцатью двумя раздачами.
    """
    thin = _franchise_plan(
        "Мальтийский сокол", 1931, [rel(name="Мальтийский сокол 1931 BDRip", seeders=16)]
    )
    deep = _franchise_plan(
        "Мальтийский сокол",
        1941,
        [
            rel(name="Мальтийский сокол BDRip 1080p Дубляж", size_gb=8.0, seeders=5),
            rel(name="The Maltese Falcon BDRip 720p", quality="720p", size_gb=4.0, seeders=28),
        ],
    )
    assert alive_numbers([thin, deep], [1, 2]) == [1, 2], "по сидам живы обе"
    assert first_alive([thin, deep]) == 2
    assert "всего одна раздача" in default_note([thin, deep])


def _asked_parts(*parts: tuple[str, int, Kind, int]) -> list[Any]:
    """Франшиза, у которой запрос назвал серию: тип сказан вслух (``s2e7``)."""
    return [
        _series_plan(
            title,
            year,
            kind,
            [rel(name=f"{title} {year} WEB-DL 1080p", size_gb=4.2, seeders=seeders)],
        )
        for title, year, kind, seeders in parts
    ]


#: Спорные запросы из замера каталога (карточка TC-198), где картина менялась молча.
#: Расклад каждого - ФОРМА его смены (тёзка по году / мёртвая первая часть / гейт типа),
#: а не расшифровка прогона: живой выдачи у теста нет. Третий элемент - слова, без которых
#: строка не сказала бы, ЧТО именно поменяли.
_SWAPS: list[tuple[str, list[Any], list[str]]] = [
    (
        "мумия",
        _parts(
            ("Мумия", 1999, 47),
            ("Мумия возвращается", 2001, 33),
            ("Мумия", 2017, 58),
            ("Мумия", 2026, 604),
        ),
        ["Мумия (1999)", "Мумия (2026)"],
    ),
    (
        "хищник",
        _parts(("Хищник", 1987, 39), ("Хищник", 2018, 44), ("Хищник: Планета смерти", 2025, 488)),
        ["Хищник (1987)", "Хищник (2018)"],
    ),
    (
        "дюна",
        _parts(("Дюна", 1984, 26), ("Дюна", 2021, 190), ("Дюна: Часть вторая", 2024, 402)),
        ["Дюна (1984)", "Дюна (2021)"],
    ),
    ("оно", _parts(("Оно", 1990, 37), ("Оно", 2017, 214)), ["Оно (1990)", "Оно (2017)"]),
    (
        "москва слезам не верит",
        _parts(("Москва слезам не верит", 1979, 88), ("Москва слезам не верит", 2019, 12)),
        ["Москва слезам не верит (1979)", "Москва слезам не верит (2019)"],
    ),
    (
        "гарри поттер",
        _parts(
            ("Гарри Поттер и философский камень", 2001, 2),
            ("Гарри Поттер и Тайная комната", 2002, 61),
        ),
        ["Гарри Поттер и Тайная комната (2002)", "Гарри Поттер и философский камень (2001)"],
    ),
    (
        "медведь s2e7",
        _asked_parts(("Медведь", 1938, "movie", 22), ("Медведь", 2022, "tv", 95)),
        ["Медведь (2022, сериал)", "Медведь (1938)", "спросили серию"],
    ),
    (
        "доктор кто s5e10",
        _asked_parts(("Доктор Кто", 1963, "tv", 14), ("Доктор Кто", 2005, "tv", 268)),
        ["Доктор Кто (1963, сериал)", "Доктор Кто (2005, сериал)"],
    ),
]


@pytest.mark.parametrize(("asked", "plans", "words"), _SWAPS, ids=[s[0] for s in _SWAPS])
def test_a_swapped_picture_is_said_out_loud_in_one_line(
    asked: str, plans: list[Any], words: list[str]
) -> None:
    """🔴 TC-198: взяли не то, что назвали, - одна честная строка «спросили X - беру Y».

    В замере каталога десять спорных запросов из четырнадцати сменили картину МОЛЧА, а
    ещё у четырёх строка была не про то: у «гарри поттера» человек читал про оригинальное
    имя и добор сезона, пока менялась часть франшизы.
    """
    note = default_note(plans, asked)
    assert note, f"«{asked}»: смена картины прошла молча"
    assert "\n" not in note, "строка одна"
    assert note.startswith(f"спросили «{asked}» - беру "), note
    for word in words:
        assert word in note, f"«{asked}»: строка не говорит про «{word}» - {note}"


@pytest.mark.parametrize(
    ("asked", "plans"),
    [
        ("голодные игры", _FRANCHISES[2][1]),
        ("безумный макс", _FRANCHISES[4][1]),
        ("джуманджи", _FRANCHISES[5][1]),
        ("тачки", _cars_franchise()),
    ],
)
def test_taking_exactly_what_was_asked_is_not_worth_a_line(asked: str, plans: list[Any]) -> None:
    """Взято ровно запрошенное - строки нет: счастливый путь остаётся без лишних слов.

    Три из четырнадцати спорных запросов после TC-196 перестают быть сменой вовсе:
    дефолтом встаёт первая часть, то есть та самая картина, чьё имя человек и назвал.
    Говорить о решении, которого не принимали, - такой же шум, как молчать о принятом.
    """
    assert default_note(plans, asked) == ""


def test_the_line_belongs_to_the_default_not_to_the_human_choice() -> None:
    """Человек ответил на меню сам - подмены не было, и говорить ему «беру не то» нельзя."""
    plans = _parts(("Оно", 1990, 37), ("Оно", 2017, 214))
    assert swap_note(plans, plans[0], "оно"), "дефолт - строка есть"
    assert swap_note(plans, plans[1], "оно") == "", "выбрал человек - строки нет"
    assert swap_note(plans[:1], plans[0], "оно") == "", "картина одна - выбора не было"


def test_the_default_pictures_year_is_checked_against_the_reference() -> None:
    """🔴 TC-199/TC-200. Год дефолтной картины сверяется со справкой - как год добора.

    Год склеивается из ИМЕНИ раздачи, а имя врёт: «Оно» уезжает раздачей 2014 года при
    фильме 2017-го, «Медведь» - 2026-го. Гейт подмены сверял год только вокруг добора, а у
    картины, вставшей дефолтом, год не сверялся нигде - и человек молча получал не тот год.
    """
    from torrcast.domain.facts.origin import Origin

    plan = _franchise_plan("Оно", 2014, [rel(name="Оно 2014 BDRip 1080p")])
    note = year_note(plan, Origin(title="It", year=2017), asked="оно")
    assert note, "год расходится со справкой - решение обязано прозвучать"
    assert "\n" not in note, "строка одна"
    assert note.startswith("спросили «оно» - "), note
    assert "2014" in note and "2017" in note, note


def test_the_year_gate_stays_silent_where_it_should() -> None:
    """🔴 TC-199/TC-200. Ограждения гейта года: молчим, где сверять нечем или год верен.

    Право у строки одно - сказать вслух; блокировать показ или менять год картины она не
    вправе. Молчим в трёх случаях: справка пуста/неуверенна (не подменять её молчанием год
    из имени), год картины неизвестен (опровергать нечего), год сошёлся или это ремейк.
    """
    from torrcast.domain.facts.origin import Origin

    plan = _franchise_plan("Оно", 2017, [rel(name="a")])
    assert year_note(plan, Origin()) == "", "справка пуста - молчим и НЕ блокируем"
    assert year_note(plan, Origin(title="It", year=None)) == "", "год справке неведом - молчим"
    unknown = _franchise_plan("Оно", None, [rel(name="a")])
    assert year_note(unknown, Origin(title="It", year=2017)) == "", "года картины нет - молчим"
    assert year_note(plan, Origin(title="It", year=2017)) == "", "год сошёлся - строки нет"
    near = _franchise_plan("Оно", 2016, [rel(name="a")])
    assert year_note(near, Origin(title="It", year=2017)) == "", "±1 год (прокат) - не подмена"
    releases = [rel(name="a")]
    remake = Plan(
        picture=Picture(
            title="Корзинка фруктов", year=2019, original="Fruits Basket", releases=releases
        ),
        ranked=rank_releases(releases, RUNTIME, 20.0),
        runtime=RUNTIME,
        warn_mbit=20.0,
    )
    assert year_note(remake, Origin(title="Fruits Basket", year=2006)) == "", "ремейк - та же вещь"


def test_the_year_line_belongs_to_the_default_not_to_the_human_choice() -> None:
    """Гейт года живёт там же, где гейт картины: у дефолта, а не у выбора человека.

    Человек, ответивший на меню сам, ничего не подменял - говорить ему «беру не тот год»
    было бы враньём (:func:`~torrcast.usecases.choice.swap_note._is_default`, общий с
    :func:`~torrcast.usecases.choice.swap_note.swap_note`).
    """
    plans = _parts(("Оно", 2014, 37), ("Оно", 2017, 214))
    assert _is_default(plans, plans[0]), "первая часть по хронологии - дефолт"
    assert not _is_default(plans, plans[1]), "вторую выбрал человек - не дефолт"
    assert not _is_default(plans[:1], plans[0]), "картина одна - выбора не было"


def test_the_year_gate_catches_a_fresh_namesake_hiding_under_an_old_name() -> None:
    """🔴 TC-192. «Брат 2» уезжал на «Брат (2025)» - год выбранной картины и ловит гейт.

    Картину по номеру части выбирает разбор, и выбирает верно (см. тест
    ``test_brother_two_is_the_year_two_thousand_and_not_a_fresh_namesake`` в
    ``test_parse``). Но год картины склеен из ИМЁН раздач, а имя подписывает переиздание
    свежим годом - и остаток подмены ловится ровно там же, где «Оно» и «Медведь»: вторым
    независимым словом справки. Переделывать под этот случай нечего, случай фиксируется.
    """
    from torrcast.domain.facts.origin import Origin

    plan = _franchise_plan("Брат 2", 2025, [rel(name="Брат 2 (2025) WEB-DL 1080p")])
    note = year_note(plan, Origin(title="Brat 2", year=2000), asked="брат 2")
    assert note and "2025" in note and "2000" in note, note
    honest = _franchise_plan("Брат 2", 2000, [rel(name="Брат 2 (2000) BDRip 1080p")])
    assert year_note(honest, Origin(title="Brat 2", year=2000), asked="брат 2") == ""


def test_a_film_is_not_swapped_for_a_same_name_series_with_a_deeper_queue() -> None:
    """🔴 TC-192. «Нелюбовь» - это фильм Звягинцева, а не сериал «НЕлюбовь [S01]».

    Однораздачная картина уступает дефолт соседке, у которой и очередь глубже, и рой
    живее (:func:`~torrcast.usecases.choice.backed.backed`). Через границу типа это правило врёт: у
    фильма раздача одна на всё кино, у сериала - на каждый сезон, и общей линейкой фильм объявлялся
    «формально живым» ровно за то, что он фильм. Замер: фильм 2017 года одной раздачей на 40 сид
    против сериала двумя на 120 - дефолтом молча вставал сериал.
    """
    film = _franchise_plan("Нелюбовь", 2017, [rel(name="Нелюбовь 2017 BDRip 1080p", seeders=40)])
    series = _franchise_plan(
        "НЕлюбовь",
        2022,
        [
            rel(name="НЕлюбовь S01 WEBRip 720p", quality="720p", size_gb=5.0, seeders=120),
            rel(name="НЕлюбовь S01 WEB-DL 1080p", size_gb=6.0, seeders=60),
        ],
        kind="tv",
    )
    plans = [film, series]
    assert [liveliness(p) for p in plans] == [40, 120], "рой у сериала и правда живее"
    assert backed(plans, [1, 2]) == [1, 2], "глубина сериала фильму не судья"
    assert first_alive(plans) == 1
    assert "НЕлюбовь" in default_note(plans, "нелюбовь"), "о тёзке другого типа - вслух"


def test_a_lone_release_still_yields_to_a_deeper_queue_of_its_own_kind() -> None:
    """Ограждение к правке выше: внутри одного типа ступень работает как работала.

    «Мальтийский сокол» 1931 года - одно обещание индексера на 16 сид, а у тёзки 1941
    года двадцать две раздачи и лучшая годная живее. Обе - полнометражки, мерить их одной
    линейкой и надо.
    """
    thin = _franchise_plan(
        "Мальтийский сокол", 1931, [rel(name="Мальтийский сокол 1931 BDRip", seeders=16)]
    )
    deep = _franchise_plan(
        "Мальтийский сокол",
        1941,
        [
            rel(name="Мальтийский сокол BDRip 1080p Дубляж", size_gb=8.0, seeders=5),
            rel(name="The Maltese Falcon BDRip 720p", quality="720p", size_gb=4.0, seeders=28),
        ],
    )
    assert backed([thin, deep], [1, 2]) == [2]
    assert first_alive([thin, deep]) == 2


def test_default_leaves_a_dead_end_picture_for_its_living_namesake() -> None:
    """🔴 TC-246. «Призраки»: 190 строк в пуле, 58 HD - а дефолт вставал на тупик.

    Тупик тут дословный: одна SD-раздача, порог живости она проходит (8 сид), очереди за
    ней нет, и нужного сезона тоже. Рядом стоит картина ровно того же имени с тридцатью
    раздачами в 1080p. :func:`~torrcast.usecases.choice.backed.backed` за неё не берётся - тип
    другой (TC-192),
    - и дефолтом молча вставал тупик. Тот же расклад у «Ангела», «Убийства», «Родины».
    """
    stub = _franchise_plan(
        "Призраки", 2014, [rel(name="Призраки 2014 HDRip", quality=None, size_gb=1.4, seeders=8)]
    )
    live = _franchise_plan(
        "Призраки",
        2021,
        [
            rel(name=f"Призраки / Ghosts S01 WEB-DL 1080p {i}", size_gb=6.0, seeders=40 + i)
            for i in range(30)
        ],
        kind="tv",
    )
    plans = [stub, live]

    assert alive_numbers(plans, [1, 2]) == [1, 2], "по сидам жива и та, и другая"
    assert fitness(stub) == 0, "играть по-человечески тупику нечем"
    assert playable(plans, [1, 2]) == [2]
    assert first_alive(plans) == 2
    assert "живого HD у неё нет" in default_note(plans, "призраки"), "смена картины - вслух"


def test_a_living_namesake_of_another_name_never_takes_the_default() -> None:
    """Ограждение к правке выше: уступают только ТЁЗКИ, соседи по франшизе - никогда.

    Дефолт франшизы - первая живая часть, и это решение отдельное от качества: «Тачки»,
    у которых в каталоге одни DVD-образы, обязаны остаться первым пунктом, а не уступить
    третьей части за её живой 1080p.
    """
    first = _franchise_plan(
        "Тачки", 2006, [rel(name="Тачки 2006 DVDRip", quality=None, size_gb=1.4, seeders=66)]
    )
    third = _franchise_plan(
        "Тачки 3", 2017, [rel(name="Тачки 3 2017 WEB-DL 1080p", size_gb=4.6, seeders=121)]
    )
    plans = [first, third]

    assert fitness(first) == 0 and fitness(third) == 121
    assert playable(plans, [1, 2]) == [1, 2], "это другая картина, а не тёзка"
    assert first_alive(plans) == 1


def test_all_namesakes_in_a_dead_end_keep_their_places() -> None:
    """Уступать некому - список остаётся как был: выбирать всё равно не из чего."""
    early = _franchise_plan(
        "Призраки", 2014, [rel(name="Призраки 2014 HDRip", quality=None, size_gb=1.4, seeders=8)]
    )
    late = _franchise_plan(
        "Призраки", 2021, [rel(name="Призраки 2021 DVDRip", quality=None, size_gb=1.3, seeders=40)]
    )
    plans = [early, late]

    assert [fitness(p) for p in plans] == [0, 0]
    assert playable(plans, [1, 2]) == [1, 2]
    assert first_alive(plans) == 1


def _numbered_cars(first_dead: bool = True) -> list[Any]:
    """Нумерованная франшиза «тачки»: первая часть и два сиквела с явными номерами.

    Мёртвая первая часть - живой случай: у «Тачек» в каталоге одни DVD-образы, играть
    ими нечего, и порог живости такой рой не считает.
    """
    plans = [
        _franchise_plan(
            "Тачки",
            2006,
            [
                rel(
                    name="Тачки 2006 DVD5",
                    codec=None,
                    quality=None,
                    size_gb=4.4,
                    seeders=3 if first_dead else 66,
                )
            ]
            if first_dead
            else [rel(name="Тачки 2006 BDRip 1080p", size_gb=4.4, seeders=66)],
        ),
        _franchise_plan(
            "Тачки 2", 2011, [rel(name="Тачки 2 2011 WEB-DL 1080p", size_gb=4.6, seeders=71)]
        ),
        _franchise_plan(
            "Тачки 3", 2017, [rel(name="Тачки 3 2017 WEB-DL 1080p", size_gb=4.6, seeders=121)]
        ),
    ]
    plans[0].picture.original = "Cars"
    plans[1].picture.original = "Cars 2"
    plans[1].picture.part = 2
    plans[2].picture.original = "Cars 3"
    plans[2].picture.part = 3
    return plans


def test_the_default_never_switches_to_another_part_of_the_franchise() -> None:
    """🔴 TC-373. Спрошенная часть не играет - дефолт на другую часть не встаёт.

    Живой случай: запрос «тачки», у первой части одни DVD-образы, и Enter включал
    «Тачки 2» - другое кино той же франшизы, которого не просили. Строка теперь
    называет, что с первой частью, а показ другой части начинает только сам человек.
    """
    plans = _numbered_cars()

    note = part_one_swap(plans, "тачки")
    assert "«Тачки (2006)» не играет" in note
    assert "другую часть сам не включаю" in note

    assert part_one_swap(plans, "тачки 2") == "", "номер назван явно - дефолт честен"
    assert part_one_swap(plans, "форсаж") == "", "запрос не про эту франшизу"
    assert part_one_swap(_moana_franchise(), "моана") == "", "франшиза без номеров"
    alive = _numbered_cars(first_dead=False)
    assert part_one_swap(alive, "тачки") == "", "первая часть жива - дефолт на ней"


def test_the_original_name_of_the_franchise_reads_the_same() -> None:
    """Франшизу назвали оригинальным именем («cars») - правило то же, что для «тачки»."""
    plans = _numbered_cars()

    assert "не играет" in part_one_swap(plans, "cars")
    assert "первой части в выдаче нет" in part_one_swap(plans[1:], "cars")


def test_the_default_is_no_default_when_the_first_part_is_absent() -> None:
    """Первой части нет в выдаче вовсе (добор за ней не состоялся) - об этом вслух."""
    plans = _numbered_cars()[1:]

    assert "первой части в выдаче нет" in part_one_swap(plans, "тачки")


def test_the_namesake_relaxation_stays() -> None:
    """Ограждение: тёзка первой части - не другая часть, и дефолт на неё остаётся.

    «Оно» 1990 и «Оно» 2017 - одна вещь, снятая дважды: имя человек назвал верно, и
    послабление для однофамильца не тронуто. А вот «Оно 2» - другая часть, и встань
    дефолт на неё - строка была бы.
    """
    first = _franchise_plan(
        "Оно",
        1990,
        [rel(name="Оно 1990 DVDRip", codec=None, quality=None, size_gb=1.4, seeders=9)],
    )
    twin = _franchise_plan(
        "Оно", 2017, [rel(name="Оно 2017 WEB-DL 1080p", size_gb=4.6, seeders=80)]
    )
    second = _franchise_plan(
        "Оно 2", 2019, [rel(name="Оно 2 2019 WEB-DL 1080p", size_gb=4.6, seeders=60)]
    )
    second.picture.part = 2

    assert part_one_swap([first, twin, second], "оно") == "", "тёзка - та же вещь"
    assert "не играет" in part_one_swap([first, second], "оно"), "а часть - нет"


def test_a_chapter_of_one_picture_is_not_a_part_of_the_franchise() -> None:
    """«Дары Смерти: Часть I» - глава одной картины, а не первая часть франшизы.

    Живой случай из корпуса: номер главы попадает в ``part``, и без ограждения
    «первая часть не играет» собиралась из глав одного фильма 2010 года - при живом
    «философском камне» 2001 года, стоящем дефолтом. Пока в меню есть картина старше
    «первой части» линейки, это нумерация внутри одной вещи, и дефолт честен.
    """
    stone = _franchise_plan(
        "Гарри Поттер и философский камень",
        2001,
        [rel(name="Гарри Поттер и философский камень 2001 BDRip 1080p", size_gb=2.5, seeders=40)],
    )
    hallows_one = _franchise_plan(
        "Гарри Поттер и Дары Смерти: Часть I",
        2010,
        [rel(name="Гарри Поттер и Дары Смерти Часть I 2010 BDRip 1080p", size_gb=2.6, seeders=30)],
    )
    hallows_one.picture.part = 1
    hallows_two = _franchise_plan(
        "Гарри Поттер и Дары Смерти: Часть II",
        2011,
        [rel(name="Гарри Поттер и Дары Смерти Часть II 2011 BDRip 1080p", size_gb=2.6, seeders=30)],
    )
    hallows_two.picture.part = 2
    doc = _franchise_plan(
        "Гарри Поттер: История магии",
        2017,
        [rel(name="Гарри Поттер История магии 2017 WEB-DL 1080p", size_gb=1.4, seeders=9)],
    )

    assert part_one_swap([stone, hallows_one, hallows_two, doc], "гарри поттер") == ""


def test_a_numbered_book_series_is_not_a_franchise_line() -> None:
    """Книжная серия с номером тома рядом с кинокартиной - не линейка франшизы.

    Живой случай из корпуса: «Homo Ludens 1. Класс: Сталкер» (``kind="other"``)
    попадает в меню фильма «Сталкер», и без ограждения том считался «первой частью»,
    которая якобы не играет. Картины линейку образуют, чужие носители - нет.
    """
    book = _franchise_plan(
        "Дан Лебэл - Homo Ludens 1. Класс: Сталкер",
        2019,
        [rel(name="Homo Ludens 1 fb2", codec=None, quality=None, size_gb=0.01, seeders=2)],
        kind="other",
    )
    book.picture.part = 1
    film = _franchise_plan(
        "Сталкер", 1979, [rel(name="Сталкер 1979 BDRip 1080p", size_gb=4.4, seeders=50)]
    )

    assert part_one_swap([book, film], "сталкер") == ""


def test_the_menu_asks_without_a_default_when_another_part_would_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Спрошенной части нет - Enter другую часть не включает: номер называет человек."""
    plans = _numbered_cars()[1:]
    environment = FakeChoiceEnvironment(answers=[1])

    plan = _pick_plan(plans, asked="тачки", environment=cast(Any, environment))

    assert environment.questions == [("Что смотрим?", 2, None)], "дефолта у вопроса нет"

    out = capsys.readouterr().out
    assert "первой части в выдаче нет" in out
    assert "Enter -" not in out, "дефолта нет: другую часть по Enter не включаем"
    assert plan.picture.title == "Тачки 2", "номер назвал сам человек"


def test_the_menu_default_stays_on_the_living_first_part(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ограждение: первая часть жива - дефолт «первая живая часть» не тронут.

    Сказать о таком дефолте нечего, поэтому вопроса нет вовсе: строка называет взятую
    картину и ход к соседним частям, а показ начинается сам.
    """
    plans = _numbered_cars(first_dead=False)
    environment = FakeChoiceEnvironment()

    plan = _pick_plan(plans, asked="тачки", environment=cast(Any, environment))

    assert "беру «Тачки (2006)» - подошло картин 3" in capsys.readouterr().out
    assert environment.questions == [], "спрашивать не о чем"
    assert plan.picture.title == "Тачки"


def test_a_missing_part_answer_lists_what_the_franchise_has() -> None:
    """Отказ «номера нет» перечисляет, что во франшизе есть: молчаливого отказа нет."""
    pictures = [
        Picture(title="Тачки 2", year=2011, part=2, releases=[rel(name="c2", seeders=9)]),
        Picture(title="Тачки 3", year=2017, part=3, releases=[rel(name="c3", seeders=26)]),
    ]

    text = _nothing("тачки", 1, pictures)

    assert "картин во франшизе 2, номера 1 нет" in text
    assert "Тачки 2 (2011)" in text and "Тачки 3 (2017)" in text


def _invisible_man() -> list[Any]:
    """Меню «человек-невидимка»: 1933 год формально жив, а играть им нечем.

    Одна раздача на девять сид - порог живости она проходит, очереди за ней нет. Рядом
    стоит тёзка 2020 года: две раздачи, 210 и 90 сид.
    """
    return [
        _franchise_plan(
            "Человек-невидимка",
            1933,
            [rel(name="The Invisible Man 1933 BDRip", size_gb=1.5, seeders=9)],
        ),
        _franchise_plan(
            "Человек-невидимка",
            2020,
            [
                rel(name="Человек-невидимка 2020 WEB-DL 1080p", size_gb=4.2, seeders=210),
                rel(name="Человек-невидимка 2020 BDRip 1080p", size_gb=8.0, seeders=90),
            ],
        ),
    ]


def test_the_show_moves_to_a_live_namesake_when_the_chosen_picture_cannot_play() -> None:
    """🔴 TC-203. У выбранной картины играть нечем, а тёзка рядом жива - уходим к ней.

    Шесть отказов из 115 в замере каталога выглядели так: все раздачи выбранной картины
    негодны, а в том же меню стоит живая одноимённая. «Человек-невидимка» садился на 1933
    год при живой картине 2020-го - и отказ был честен про картину и неправдой про вечер.
    """
    plans = _invisible_man()
    spare = understudy(plans, plans[0])
    assert spare is not None and spare.picture.year == 2020
    note = understudy_note(plans[0], spare, "годного релиза нет")
    assert "\n" not in note, "строка одна"
    assert "1933" in note and "2020" in note, note
    assert "годного релиза нет" in note, "причина названа, а не «просто ухожу»"


def test_the_understudy_is_a_namesake_and_never_someone_elses_picture() -> None:
    """🔴 TC-203. Ограждения ухода: тёзка по году - да, соседка по франшизе - никогда.

    «Тачки 2» вместо «Тачек» - это другое кино, и уходить туда самому нельзя ни при каком
    отказе: о таких соседях говорит подсказка
    (:func:`~torrcast.usecases.discover.kin_line.kin_line`), и подсказкой она и остаётся. Тип обязан
    совпасть по той же причине, по какой его не меняет дефолт. Мёртвая тёзка дублёром не бывает:
    играть ею нечем ровно так же.
    """
    cars = _parts(("Тачки", 2006, 66), ("Тачки 3", 2017, 121))
    assert understudy(cars, cars[0]) is None, "соседка по франшизе - другое кино"

    film = _franchise_plan("Нелюбовь", 2017, [rel(name="кино", seeders=9)])
    series = _franchise_plan(
        "Нелюбовь",
        2022,
        [rel(name="s01", seeders=120), rel(name="s02", seeders=60)],
        kind="tv",
    )
    assert understudy([film, series], film) is None, "сериал вместо фильма - подмена"

    dead = _parts(("Мумия", 1999, 47), ("Мумия", 2017, 2))
    assert understudy(dead, dead[0]) is None, "тёзка мертва - уходить некуда"
    assert understudy(_invisible_man()[:1], _invisible_man()[0]) is None, "меню из одной"


class _SwitchBench:
    """Скамейка, у которой играет только картина 2020 года: 1933-я отказывает как в жизни."""

    def __init__(self) -> None:
        self.asked: list[int | None] = []
        self.kept: list[int | None] = []

    def resolve(self, plan: Any, args: Any, progress: Any) -> Any:
        self.asked.append(plan.picture.year)
        if plan.picture.year != 2020:
            raise NotFoundError(
                "годного релиза нет (1 - тяжёлый): выбери руками - cast releases <запрос>"
                "\nв каталоге есть Человек-невидимка (2020) - cast человек-невидимка"
            )
        return cast(Any, plan.picture.year)

    def reorder(self, plan: Any, fresh: Any) -> Any:
        return fresh

    def keep_plan(self, plan: Any) -> None:
        self.kept.append(plan.picture.year)


def test_the_switch_to_the_understudy_happens_by_itself_and_is_said_out_loud(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-203. Играть выбранной картиной нечем - показ сам уходит к живой тёзке.

    Уход не молчаливый и не безграничный: строка печатается ОБЯЗАТЕЛЬНО (это смена
    картины), а кругов ровно два - выбранная и одна тёзка. Совет «выбери руками» из
    отказа в строку не переезжает: после автоматического ухода он был бы неправдой.
    """
    plans = _invisible_man()
    bench = _SwitchBench()
    args = Args(query=["человек-невидимка"])

    plan, prep = _played(
        cast(Any, bench), plans, plans[0], args, cast(Any, None), None, load_config(), CAUTIOUS
    )

    assert plan.picture.year == 2020 and cast(Any, prep) == 2020
    assert bench.asked == [1933, 2020], "круга ровно два"
    assert bench.kept == [2020], "прогретое чужих картин убирается уже под новую картину"
    said = capsys.readouterr().out.strip()
    assert said.count("\n") == 0, "строка одна"
    assert "1933" in said and "2020" in said and "годного релиза нет" in said, said
    assert "cast releases" not in said, "ход руками после автоматического ухода - неправда"


def test_without_a_live_namesake_the_refusal_stays_the_refusal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ограждение: тёзки нет - отказ доезжает до человека ровно таким, каким родился.

    Уход к соседке по франшизе или к одноимённому сериалу тут был бы подменой картины,
    и молчание отказа подменять его нечем: подсказку про соседей отказ несёт сам
    (:func:`~torrcast.usecases.discover.kin_line.kin_line`).
    """
    plans = _parts(("Тачки", 2006, 66), ("Тачки 3", 2017, 121))
    bench = _SwitchBench()

    with pytest.raises(NotFoundError, match="годного релиза нет"):
        _played(
            cast(Any, bench),
            plans,
            plans[0],
            Args(query=["тачки"]),
            cast(Any, None),
            None,
            load_config(),
            CAUTIOUS,
        )
    assert bench.asked == [2006], "лишнего круга нет"
    assert capsys.readouterr().out == "", "никакого ухода не было - и говорить не о чем"


def test_a_lone_release_still_wins_when_the_whole_franchise_is_lone() -> None:
    """Все живые картины об одной раздаче - список остаётся как был.

    Ступень отбрасывает однораздачные, только пока в живых есть кто-то ещё: иначе она
    молчаливо превращала бы «живую» картину в мёртвую, а выбирать всё равно не из чего.
    Здесь же и защита от «дефолт = самая раздаваемая»: первая часть франшизы остаётся
    дефолтом, даже когда у сиквела раздач больше.
    """
    first = _franchise_plan("Кино", 2001, [rel(name="a", seeders=100)])
    second = _franchise_plan("Кино 2", 2005, [rel(name="b", seeders=90), rel(name="c", seeders=80)])
    assert first_alive([first, second]) == 1
    assert default_note([first, second]) == "", "решения не принимали - и строки нет"


def test_asked_series_outweighs_a_namesake_film() -> None:
    """«хорошая жена s1e1» - просьба про сериал, а дефолтом вставал фильм 1987 года.

    У фильма три раздачи и ни одной живой, у сериала 2015 года - тридцать раздач и 18
    сид. Тип, названный запросом, весит больше одноимённого соседа другого типа.
    """
    film = _series_plan(
        "Хорошая жена",
        1987,
        "movie",
        [rel(name="film", seeders=6), rel(name="film dvd", quality="720p", seeders=4)],
    )
    show = _series_plan(
        "Хорошая жена",
        2015,
        "tv",
        [rel(name="s01", seeders=12), rel(name="s01 web", quality="720p", seeders=18)],
    )
    assert first_alive([film, show]) == 2
    note = default_note([film, show])
    assert "спросили серию" in note and "2015" in note and "1987" in note


def test_a_film_only_catalogue_keeps_the_default_where_it_was() -> None:
    """Сериалов в выдаче нет вовсе - гейт типа молчит: он не судья тому, чего не видел."""
    first = _series_plan("Кино", 2001, "movie", [rel(name="a", seeders=100)])
    second = _series_plan("Кино 2", 2005, "movie", [rel(name="b", seeders=100)])
    assert asked_kind([first, second]) == [1, 2]
    assert first_alive([first, second]) == 1
    assert default_note([first, second]) == ""


def test_the_default_names_itself_for_a_menu_that_does_not_fit_the_screen() -> None:
    """🔴 TC-204. «Ван Пис»: дефолт стоял строкой 33 из 35, а человек видел только `[33]`.

    Порядок меню хронологический и таким остаётся - меняется показ дефолта, а не порядок:
    список по-прежнему начинается с самой ранней картины, а что случится по Enter,
    сказано словами - названием и годом, а не одной цифрой.
    """
    plans = [
        _franchise_plan("Ван Пис", 1990 + n, [rel(name=f"rip {n}", seeders=0 if n < 33 else 20)])
        for n in range(1, 36)
    ]
    default = first_alive(plans)

    assert default == 33, "живой в этой выдаче стала только тридцать третья картина"
    assert default_line(plans, default) == "Enter - «Ван Пис (2023)», пункт 33 из 35"
    assert menu_blocks(plans, width=80)[0][0].startswith("  1. Ван Пис (1991)"), (
        "список не переупорядочивается: хронология - осознанное решение"
    )


def test_prewarm_starts_with_the_default_not_with_the_earliest() -> None:
    """Греем то, во что попадёт Enter: иначе прогрев под меню греет чужую картину.

    У «моаны» дефолт - вторая картина, а под меню греются только первые
    :data:`~torrcast.domain.prewarm_settings.PREWARM`.
    """
    plans = _moana_franchise()
    assert [p.picture.year for p in warm_order(plans)] == [2016, 1926, 2024]


def test_enter_picks_the_picture_the_honest_line_is_about(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Enter берёт дефолт, а не верх списка, и о смене картины говорит вслух.

    Верх списка тут - сериал с мёртвым роем: нажми человек Enter на нём, он не получил
    бы ничего. Дефолт уходит на живую картину, но уходит НЕ молча - строка называет обе
    картины и причину, а список с номерами остаётся на экране.
    """
    top = _franchise_plan("Наруто", 2002, [rel(name="Naruto 001-220", seeders=4)])
    movie = _franchise_plan(
        "Наруто 8: Кровавая тюрьма",
        2011,
        [
            rel(name="Naruto Blood Prison 1080p", seeders=5),
            rel(name="Naruto Blood Prison BDRip", seeders=3),
        ],
    )
    plans = [top, movie]
    assert first_alive(plans) == 2, "рой верхней картины мёртв"

    picked = _pick_plan(plans, asked="naruto", environment=cast(Any, FakeChoiceEnvironment()))

    assert menu_blocks(plans)[0][0].startswith("  1. Наруто (2002)")
    assert "Enter - «Наруто 8: Кровавая тюрьма (2011)», пункт 2 из 2" in capsys.readouterr().out
    assert picked is movie
    assert swap_note(plans, picked, "naruto") == (
        "спросили «naruto» - беру «Наруто 8: Кровавая тюрьма (2011)», "
        "а не «Наруто (2002)»: рой у неё мёртв - сидов 4"
    ), "картина сменилась - и об этом сказано"


def test_the_spare_release_goes_up_next_to_the_first_one() -> None:
    """Запасной релиз выбранной картины греется вместе с верхом, а не после его брака.

    Номер у него ровно тот же, который возьмёт
    :meth:`~torrcast.usecases.select_bench.bench.Bench.resolve`, - следующий в очереди
    (:meth:`~torrcast.usecases.select.plan.Plan.candidates`). Отличается только время: раньше он
    поднимался в отборе, теперь - пока на экране висит меню.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "h264")
    bench = Bench(cast(Any, _FakeTorrServer()), prober=prober)
    plan = _plan(ranked)

    bench.start(plan, plan.candidates(Args(query=["кино"]))[0])
    spare = bench.spare(plan, Args(query=["кино"]))

    assert [prep.number for prep in spare] == [plan.candidates(Args(query=["кино"]))[1]]
    assert sorted(number for _, number in bench.preps) == [1, 2]


def test_a_release_named_by_hand_has_no_spare() -> None:
    """``--release N`` - выбор человека: подменять нечем, и лишней раздачи не поднимаем."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(3)]
    prober = _probes(ranked, "h264")
    torrserver = _FakeTorrServer()
    bench = Bench(cast(Any, torrserver), prober=prober)

    assert bench.spare(_plan(ranked), Args(query=["кино"], release=2)) == []
    assert not bench.preps


# --- Честное качество: заявка имени против того, что прочитал ffprobe -----------------


def _reads(releases: list[Release], *media: Media) -> _Prober:
    """Подсунуть ffprobe: по :class:`Media` на релиз, считая от лучшего.

    То же, что :func:`_probes`, только с высотой кадра: тут проверяется не кодек, а
    разрыв между тем, что раздача обещает именем, и тем, что лежит внутри.
    """

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        for number, release in enumerate(releases):
            if f"hash-{release.magnet}/" in url and number < len(media):
                return media[number]
        return Media(3600.0, (), "h264", 1080, 1920)

    return read


def test_launch_line_shows_the_confirmed_resolution_not_the_claim() -> None:
    """«Моана 2»: имя обещает 1080p, ffprobe читает 1150×574 — печатаем факт."""
    assert quality_text(rel(quality="1080p"), Media(5977.0, (), "h264", 574, 1150)) == "574p"
    assert quality_text(rel(quality="1080p"), Media(5977.0, (), "h264", 1080, 1920)) == "1080p"
    # ffprobe высоту не отдал - врать нечем, остаётся заявка имени и честный «?».
    assert quality_text(rel(quality="720p"), Media(5977.0, (), "h264", 0)) == "720p"
    assert quality_text(rel(quality=None), Media(5977.0, (), "h264", 0)) == "?"


def test_cropped_widescreen_is_not_a_liar() -> None:
    """1080p с обрезанными чёрными полями — это 800 строк при 1920 в ширину, и релиз
    честен: судить по одной высоте нельзя, иначе каждый скоуп-фильм объявляется враньём.
    """
    scope = Media(5977.0, (), "h264", 800, 1920)
    assert scope.quality == "1080p" and understated(rel(quality="1080p"), scope) == ""
    liar = Media(5977.0, (), "h264", 574, 1150)  # живая «Моана 2», верх выдачи
    assert liar.quality == "574p" and understated(rel(quality="1080p"), liar) != ""
    # Имя не назвало ничего, а внутри HD - придираться не к чему.
    assert understated(rel(quality=None), Media(5977.0, (), "h264", 720, 1280)) == ""
    assert understated(rel(quality=None), liar) != ""


def test_an_interlaced_file_is_named_what_it_is() -> None:
    """Названный «1080p» чересстрочник печатается «1080i»: гребёнку не подписывают прогрессивом.

    Развёртка читается из потока (:attr:`torrcast.domain.media.Media.field_order`), а не из имени:
    по имени такой релиз не поймать вовсе - «1080p» в заголовке и ``tb`` внутри.
    """
    inter = Media(5977.0, (), "h264", 1080, 1920, field_order="tb")
    assert quality_text(rel(quality="1080p"), inter) == "1080i"
    assert quality_text(rel(quality="1080i"), inter) == "1080i"
    assert understated(rel(quality="1080p"), inter) == "назван 1080p, на деле 1080i"
    assert understated(rel(quality="1080i"), inter) == "", "имя и так говорило правду"
    prog = Media(5977.0, (), "h264", 1080, 1920, field_order="progressive")
    assert quality_text(rel(quality="1080p"), prog) == "1080p"
    assert understated(rel(quality="1080p"), prog) == ""
    # Паспорт о развёртке молчит - решаем как раньше: занизить по догадке - та же ложь.
    assert quality_text(rel(quality="1080p"), Media(5977.0, (), "h264", 1080, 1920)) == "1080p"


def test_a_top_that_turns_out_to_be_sd_gives_way_to_a_confirmed_1080p(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Живая выдача по «Моане 2»: верх ``WEB-DL-AVC`` 3.14 ГБ / 140 сидов — 1150×574,
    а вторым лежит настоящий 1080p 13.3 ГБ со 121 сидом. Играть обязан второй, и вслух.
    """
    ranked = [
        rel(name="Моана 2 [WEB-DL-AVC] 2x Dub", quality=None, size_gb=3.14, seeders=140),
        rel(name="Моана 2 [WEB-DL 1080p] Dub", codec=None, size_gb=13.33, seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, (), "h264", 574, 1150),
        Media(5977.0, (), "h264", 1080, 1920),
    )
    torrserver = _FakeTorrServer()

    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 2, "среди честных обсиженность решает, но 574p - не честный 1080p"
    assert "релиз 1 на деле 574p - беру 2 (настоящий 1080p)" in printed
    assert torrserver.dropped, "отвергнутый верх не доедает полосу роя"


def test_an_honest_top_is_played_without_a_word(capsys: pytest.CaptureFixture[str]) -> None:
    """Верх подтвердил своё имя — никаких проверок соседей и никаких лишних строк.

    Обсиженность остаётся главным критерием среди честных: 1080p со 140
    сидами не уступает 1080p со 121, сколько бы тот ни весил.
    """
    ranked = [
        rel(name="Кино [WEB-DL 1080p] a", size_gb=3.14, seeders=140),
        rel(name="Кино [BDRemux 1080p] b", size_gb=13.33, seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, (), "h264", 1080, 1920),
        Media(5977.0, (), "h264", 1080, 1920),
    )

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)

    assert prep.number == 1
    assert not re.search(r"беру \d", capsys.readouterr().out)


def test_when_the_neighbour_lies_too_we_play_the_truth_out_loud(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Сосед обещал 1080p, а внутри такой же SD: подмены нет — но и молчания тоже нет."""
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=3.20, seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, (), "h264", 574, 1150),
        Media(5977.0, (), "h264", 576, 1024),
    )

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 1, "лучше 574p рядом нет - играем то, что есть"
    assert "релиз 2 не лучше (576p)" in printed
    assert "релиз 1 на деле 574p - честнее рядом нет, играю его" in printed


def test_a_named_release_is_never_second_guessed_for_quality(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--release N`` неприкосновенен и здесь: человек выбрал сам."""
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=13.33, seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, (), "h264", 574, 1150),
        Media(5977.0, (), "h264", 1080, 1920),
    )

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked, release=1)

    assert prep.number == 1
    assert not re.search(r"беру \d", capsys.readouterr().out)


def test_a_slow_neighbour_does_not_hold_up_the_show(capsys: pytest.CaptureFixture[str]) -> None:
    """Честный сосед не ответил за бюджет — играем то, что готово, и говорим об этом.

    Лишние секунды старта хуже, чем 574p, а молчаливо ждать «а вдруг» — это ровно тот
    случай, из-за которого показ когда-то вставал насмерть.
    """
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=13.33, seeders=121),
    ]
    slow = threading.Event()

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        if f"hash-{ranked[1].magnet}/" in url:  # честный сосед на холодном рое
            slow.wait(5.0)
            return Media(5977.0, (), "h264", 1080, 1920)
        return Media(5977.0, (), "h264", 574, 1150)

    try:
        bench = Bench(cast(Any, _FakeTorrServer()), prober=read, honest_budget=0.3)
        prep = _resolve(bench, ranked)
    finally:
        slow.set()  # поток прогрева отпускаем, чтобы не висел до конца прогона

    assert prep.number == 1
    assert "релиз 2 не успел ответить" in capsys.readouterr().out


# --- Честный звук: неназванный язык против соседа, обещавшего русскую дорожку ---------

#: Дорожка без тега языка и без заголовка: ffprobe про язык не сказал ничего. Ровно так
#: выглядят «Оставленные», «Зона интересов», «Жить» и «В поисках Сахарного Человека» -
#: одна безымянная дорожка на весь файл.
UNNAMED = (AudioTrack(0, "und", None, "ac3", 6),)
#: Тот же файл, но с подтверждённой русской дорожкой.
RUSSIAN = (AudioTrack(0, "rus", "Дубляж (Jaskier)", "ac3", 6),)
#: ...и с чужой: имя обещало русскую, а внутри английская.
FOREIGN = (AudioTrack(0, "eng", "Original", "ac3", 6),)


def test_an_unnamed_language_does_not_stop_the_queue_at_the_top(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-492. Верх про язык звука не сказал ничего - идём дальше по очереди.

    Живой случай: «Оставленные» уезжают с единственной дорожкой без тега языка, а ниже в
    той же очереди стоит нетронутая раздача «от Scarabey» с двумя русскими дорожками. До
    правки гейт такой верх пропускал - и очередь до подтверждённой русской не доходила
    вовсе, потому что показ уже начался. Незнание годностью не считается, и очередь
    доходит сама: ни одного лишнего ffprobe это не стоит, спрашивается уже прочитанный
    паспорт.
    """
    ranked = [
        rel(name="Кино [WEB-DL 1080p] тихий", voices=(), seeders=140),
        rel(name="Кино [BDRip 1080p] от Scarabey | D", seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, UNNAMED, "h264", 1080, 1920),
        Media(5977.0, RUSSIAN, "h264", 1080, 1920),
    )
    torrserver = _FakeTorrServer()

    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 2, "незнание меняем на знание, а не на догадку"
    assert "релиз 1 без русской озвучки (не назван) - беру 2" in printed
    assert torrserver.dropped, (
        "запасным ходом безымянный паспорт не станет (TC-741), а держать раздачу под ход, "
        "которого не будет, значит доедать полосу роя у того, кого мы и играем"
    )


def test_an_unnamed_language_falls_back_to_the_existing_mute_move(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-741. Русской не нашлось ни у кого - играет тот, чей язык назван вслух.

    Хода тут не заводится нового: работает тот же
    :meth:`~torrcast.usecases.select_bench.bench.Bench._mute_fallback`, что и всегда, одной
    строкой на всё решение. А выбирает он не «того, про кого меньше известно плохого»:
    безымянный паспорт играл под строку «звук не назван», то есть отбор возвращался ровно
    к тому релизу, который сам же забраковал, и зритель узнавал о дорожке одно - что она
    первая в файле. Незнание запасным ходом не бывает; годным остаётся только
    подтверждённый русский, а честным ответом - названный английский или отказ.
    """
    ranked = [
        rel(name="Кино [WEB-DL 1080p] тихий", voices=(), seeders=140),
        rel(name="Кино [BDRip 1080p] обещал | D", seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, UNNAMED, "h264", 1080, 1920),
        Media(5977.0, FOREIGN, "h264", 1080, 1920),
    )

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 2
    assert "релиз 1 без русской озвучки (не назван) - беру 2" in printed
    assert "релиз 2 без русской озвучки (английский)" in printed
    assert "русской озвучки нет ни в одной из проверенных раздач (2)" in printed
    assert "включаю релиз 2, звук английский" in printed
    assert "играю его" not in printed, "второй строки под тот же случай не заводится"


def test_a_confirmed_russian_track_asks_nobody(capsys: pytest.CaptureFixture[str]) -> None:
    """Паспорт назвал русскую - вопросов нет, лишних секунд тоже.

    И обратная половина того же (🔴 TC-492): раздача, обещавшая русскую своим ИМЕНЕМ,
    основанием не считается. Имя не гарантирует дорожки (TC-191), и «[RUS(int)]» с пустым
    тегом языка - то же самое незнание, что и молчаливое имя: очередь идёт дальше.
    """
    ranked = [
        rel(name="Кино [WEB-DL 1080p] a", seeders=140),
        rel(name="Кино [BDRip 1080p] b | D", seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, RUSSIAN, "h264", 1080, 1920),
        Media(5977.0, RUSSIAN, "h264", 1080, 1920),
    )
    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)
    assert prep.number == 1
    assert not re.search(r"беру \d", capsys.readouterr().out)

    promised = [
        rel(name="Аниме [TV] [RUS(int), JAP+Sub] [1080p] a", seeders=140),
        rel(name="Аниме [TV] [RUS(int)] [1080p] b", seeders=121),
    ]
    prober = _reads(
        promised,
        Media(5977.0, UNNAMED, "h264", 1080, 1920),
        Media(5977.0, RUSSIAN, "h264", 1080, 1920),
    )
    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), promised)
    assert prep.number == 2, "обещание имени русской дорожкой не становится"


def test_the_passport_has_three_answers_about_the_language() -> None:
    """«Да», «нет» и «не знаю» - и годен только первый (:func:`voice_unproven`)."""
    assert not voice_unproven(Media(5977.0, RUSSIAN, "h264", 1080, 1920)), "паспорт: да"
    assert voice_unproven(Media(5977.0, FOREIGN, "h264", 1080, 1920)), "паспорт: нет"
    assert voice_unproven(Media(5977.0, UNNAMED, "h264", 1080, 1920)), "паспорт: не знаю"
    assert not voice_unproven(Media(5977.0, (), "h264", 1080, 1920)), "звук не прочитан вовсе"


# --- Прогрев соседа по звуку: обещавшая русскую раздача греется под меню (TC-309) ------


def test_a_dubbed_neighbour_warms_under_the_menu_when_the_top_promises_nothing() -> None:
    """🔴 TC-309. Верх именем русскую не обещает - ближайший обещавший греется заодно.

    Проверка честности спросит этого соседа первым же вопросом, если дорожка верха
    окажется без тега языка (:meth:`~torrcast.usecases.select_bench.bench.Bench._honest`, повод
    «язык звука не назван»), а с нуля - метаданные роя плюс чтение дорожек - он в
    :data:`~torrcast.domain.pick_settings.HONEST_BUDGET` укладывался не всегда. Пауза под меню при
    этом простаивает.
    """
    ranked = [
        rel(name="Кино [WEB-DL 1080p] тихий", voices=(), seeders=140),
        rel(name="Кино [WEB-DL 1080p] запасной", voices=(), seeders=130),
        rel(name="Кино [BDRip 1080p] от Scarabey | D", seeders=121),
    ]
    prober = _reads(ranked, *([Media(5977.0, (), "h264", 1080, 1920)] * 3))
    bench = Bench(cast(Any, _FakeTorrServer()), prober=prober)

    preps = bench.spare(_plan(ranked), Args(query=["кино"]))

    assert {prep.number for prep in preps} == {2, 3}, "запасной и обещавший русскую сосед"


def test_a_dubbed_neighbour_warms_when_a_front_candidate_promises_nothing() -> None:
    """Верх обещал, но второй кандидат молчит - сосед по звуку греется всё равно.

    Проверка честности спрашивает того, кого отбор реально взял, а это не обязан быть
    верх: верх забракуют (мёртвый рой, чужой язык в паспорте), и повод «язык звука не
    назван» всплывёт на втором-третьем кандидате. Гейт поэтому смотрит первых
    :data:`~torrcast.domain.pick_settings.MAX_TRIES` кандидатов, а не одного верха.
    """
    ranked = [
        rel(name="Кино [BDRip 1080p] верх | D", seeders=140),
        rel(name="Кино [WEB-DL 1080p] тихий", voices=(), seeders=130),
        rel(name="Кино [BDRip 1080p] от Scarabey | D", seeders=121),
    ]
    prober = _reads(ranked, *([Media(5977.0, (), "h264", 1080, 1920)] * 3))
    bench = Bench(cast(Any, _FakeTorrServer()), prober=prober)

    preps = bench.spare(_plan(ranked), Args(query=["кино"]))

    assert {prep.number for prep in preps} == {2, 3}


def test_a_picture_whose_front_candidates_all_promise_russian_warms_no_sound_neighbour() -> None:
    """Все первые кандидаты обещали русскую - вопроса о звуке не будет, раздачи лишней нет.

    Прогрев обещавшего соседа - это ещё одна раздача в рое, и платить её надо ровно за
    тот случай, который она спасает: вопрос «язык звука не назван» релизу, обещавшему
    русскую своим именем, не задаётся вовсе (:func:`voice_unproven`).
    """
    ranked = [rel(name=f"Кино [BDRip 1080p] р{i} | D", seeders=100 - i) for i in range(3)]
    prober = _reads(ranked, *([Media(5977.0, (), "h264", 1080, 1920)] * 3))
    bench = Bench(cast(Any, _FakeTorrServer()), prober=prober)

    preps = bench.spare(_plan(ranked), Args(query=["кино"]))

    assert {prep.number for prep in preps} == {2}, "только обычный запасной"
    assert len(bench.preps) == 1, "и лишней раздачи в TorrServer нет"


def test_no_dubbed_neighbour_in_the_pool_means_nothing_extra_to_warm() -> None:
    """Обещанной русской в очереди нет вовсе - греть нечего, лишней раздачи не появляется."""
    ranked = [rel(name=f"Кино [WEB-DL 1080p] р{i}", voices=(), seeders=100 - i) for i in range(3)]
    prober = _reads(ranked, *([Media(5977.0, (), "h264", 1080, 1920)] * 3))
    bench = Bench(cast(Any, _FakeTorrServer()), prober=prober)

    preps = bench.spare(_plan(ranked), Args(query=["кино"]))

    assert {prep.number for prep in preps} == {2}
    assert len(bench.preps) == 1


def test_a_dubbed_spare_is_not_warmed_twice() -> None:
    """Ближайший обещавший русскую - это и есть обычный запасной: одна раздача, а не две."""
    ranked = [
        rel(name="Кино [WEB-DL 1080p] тихий", voices=(), seeders=140),
        rel(name="Кино [BDRip 1080p] от Scarabey | D", seeders=121),
    ]
    prober = _reads(ranked, *([Media(5977.0, (), "h264", 1080, 1920)] * 2))
    bench = Bench(cast(Any, _FakeTorrServer()), prober=prober)

    preps = bench.spare(_plan(ranked), Args(query=["кино"]))

    assert {prep.number for prep in preps} == {2}
    assert len(bench.preps) == 1, "та же подготовка, а не вторая раздача того же релиза"


def test_a_named_release_still_has_no_spare_at_all() -> None:
    """``--release N``: человек выбрал сам, и ни запасного, ни соседа по звуку не греется."""
    ranked = [
        rel(name="Кино [WEB-DL 1080p] тихий", voices=(), seeders=140),
        rel(name="Кино [BDRip 1080p] от Scarabey | D", seeders=121),
    ]
    prober = _reads(ranked, *([Media(5977.0, (), "h264", 1080, 1920)] * 2))
    bench = Bench(cast(Any, _FakeTorrServer()), prober=prober)

    assert bench.spare(_plan(ranked), Args(query=["кино"], release=2)) == []
    assert not bench.preps


@pytest.mark.parametrize(
    "title",
    [
        "Бригада",
        "Мосгаз",
        "Тайны следствия",
        "Улицы разбитых фонарей",
        "Три кота",
        "Барбоскины",
    ],
)
def test_a_native_picture_accepts_its_only_unnamed_track(title: str) -> None:
    """У отечественной картины пустой оригинал - паспорт происхождения, а не пробел."""
    release = rel(name=f"{title} [WEB-DL 1080p]", voices=())
    media = Media(5977.0, UNNAMED, "h264", 1080, 1920)

    assert not voice_unproven(media, native=True)
    assert sound_note(media, 0, [release], release, native=True) == ""


def test_a_foreign_picture_does_not_call_its_only_unnamed_track_russian() -> None:
    """У иностранной картины безымянная дорожка остаётся неизвестной, не русской."""
    release = rel(name="The Holdovers [WEB-DL 1080p]", voices=())
    media = Media(5977.0, UNNAMED, "h264", 1080, 1920)

    assert voice_unproven(media, native=False)
    assert "русская" not in sound_note(media, 0, [release], release, native=False)


def test_a_refusal_names_the_living_parts_of_the_franchise(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Годного релиза нет - но соседки по франшизе в каталоге живые, и о них говорят.

    Раньше отказ отправлял человека разбираться руками (`cast releases <запрос>`), молча
    зная, что в той же выдаче лежат другие части с живыми раздачами. Подсказка - строка,
    и только: сама она ничего не запускает, подмена картины была бы обманом.
    """
    from torrcast.domain.picture import Picture

    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(5)]
    prober = _probes(ranked, *REFUSED)
    plan = _plan(ranked)
    plan.kin = [
        Picture(title="Тачки 2", year=2011, releases=[rel(name="c2", seeders=30)]),
        Picture(title="Тачки 3", year=2017, releases=[rel(name="c3", seeders=40)]),
    ]
    args = Args(query=["тачки"])
    with pytest.raises(NotFoundError) as caught, Progress(out=io.StringIO()) as progress:
        Bench(cast(Any, _FakeTorrServer()), prober=prober).resolve(plan, args, progress)

    assert "годного релиза нет" in str(caught.value)
    assert "в каталоге есть Тачки 2 (2011), Тачки 3 (2017) - cast тачки 2" in str(caught.value)
    capsys.readouterr()


def test_a_refusal_stays_silent_when_the_franchise_has_no_other_parts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Предлагать нечего - и строки нет: пустой подсказки человек не заслужил."""
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(5)]
    prober = _probes(ranked, *REFUSED)
    with pytest.raises(NotFoundError) as caught:
        _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)

    assert "в каталоге есть" not in str(caught.value)
    capsys.readouterr()


def test_only_parts_that_stayed_out_of_the_menu_are_offered() -> None:
    """Подсказка не пересказывает меню: там человек эти картины уже видел.

    А вот часть франшизы, до меню не доехавшая (запрос попал в свою половину двуязычной
    франшизы либо у картины не осталось прошедших отбор релизов), - ровно то новое, что
    отказу есть сказать. Мёртвую, без единой раздачи, не предлагаем и её.
    """
    from torrcast.domain.cluster import cluster
    from torrcast.domain.picture import Picture

    pictures = cluster(
        [
            _named_release("Тачки", 2006),
            _named_release("Тачки 2", 2011),
            _named_release("Тачки 3", 2017),
        ]
    )
    lead = next(p for p in pictures if p.year == 2006)

    kin = _kin(lead, pictures, {lead.key})
    assert [p.title for p in kin] == ["Тачки 2", "Тачки 3"]
    # Показанное в меню не повторяем.
    shown = {p.key for p in pictures if p.year != 2017}
    assert [p.title for p in _kin(lead, pictures, shown)] == ["Тачки 3"]
    # Картина без раздач в каталоге не «живая» - о ней молчим.
    assert _kin(lead, [*pictures, Picture(title="Тачки 4", year=2029)], {lead.key}) == kin
    assert kin_line([]) == ""


def _named_release(title: str, year: int) -> Release:
    """Раздача с настоящим именем картины: кластеру нужно именно оно, а не «Кино»."""
    from torrcast.domain.parse_release_name import parse_release_name

    return parse_release_name(f"{title} ({year}) BDRip 1080p")


# --- Потолок одновременных раздач (TC-145) -------------------------------------------


def test_a_picture_we_did_not_choose_stops_being_warmed_the_moment_we_choose() -> None:
    """Картина выбрана - прогревы ОСТАЛЬНЫХ картин убираются сразу, а не после отбора.

    Раньше они доживали до :meth:`~torrcast.usecases.select_bench.bench.Bench.keep_only`, то есть до
    конца отбора: до :data:`~torrcast.domain.pick_settings.PICK_BUDGET` секунд две-три чужие раздачи
    тянули куски у той единственной, которую мы вот-вот покажем.

    Внутри выбранной картины не убирается ничего: запасной релиз греется параллельно
    верху намеренно, и распорядиться им вправе только сам отбор.
    """
    torrserver = _FakeTorrServer()
    bench = Bench(cast(Any, torrserver))
    mine = _franchise_plan("Кино", 1999, [rel(name=f"a{i}", seeders=100 - i) for i in range(3)])
    other = _franchise_plan("Кино 2", 2005, [rel(name=f"b{i}", seeders=100 - i) for i in range(3)])
    bench.start(mine, 1)
    bench.spare(mine, Args(query=["кино"]))
    bench.start(other, 1)
    assert len(bench.live()) == 3

    bench.keep_plan(mine)

    assert sorted(prep.number for prep in bench.live()) == [1, 2], "верх и запасной - живы"
    assert [key[0] for key, _ in bench.preps.items() if not _.dropped] == [
        mine.picture.key,
        mine.picture.key,
    ]
    assert torrserver.dropped, "чужая картина убрана по своему хэшу, а не «всё из списка»"


def test_we_never_hold_more_torrents_at_once_than_the_ceiling() -> None:
    """Жёсткий потолок: сколько бы ни длился перебор, одновременно держим не больше
    :data:`~torrcast.domain.prewarm_settings.MAX_LIVE` раздач.

    TorrServer падает по таймеру раз в 15 минут тем вероятнее, чем больше раздач
    он тянет; до потолка очередь перебора поднимала по раздаче за попытку, а убиралось
    всё разом только перед стартом показа.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(12)]
    prober = _probes(ranked, *(["h264"] * 11), "h264")
    torrserver = _FakeTorrServer()
    bench = Bench(cast(Any, torrserver), prober=prober)
    plan = _plan(ranked)
    peak = 0

    # Прогрев под меню: три картины и запасной (первые кандидаты фикстуры русскую
    # обещают сами, поэтому соседа по звуку нет - :data:`PREWARM_DUB` тут не срабатывает).
    for number in range(1, PREWARM + 1):
        bench.start(plan, number)
    bench.spare(plan, Args(query=["кино"]))
    peak = max(peak, len(bench.live()))
    for number in range(PREWARM + 1, len(ranked) + 1):
        bench.needed = {(plan.picture.key, number)}
        bench.start(plan, number)
        peak = max(peak, len(bench.live()))

    assert peak == MAX_LIVE == 5
    assert len(bench.preps) == len(ranked), "греть перестали не потому, что не начинали"


def test_the_ceiling_never_kills_the_warmup_someone_is_waiting_for() -> None:
    """Потолок убирает самый СТАРЫЙ ненужный прогрев и никогда - нужный.

    Запасной релиз греется параллельно верху намеренно (замеренный выигрыш 5 с), и
    убить его потолком значило бы вернуть человеку полную цену подъёма второй раздачи.
    """
    ranked = [rel(name=f"r{i}", seeders=100 - i) for i in range(6)]
    prober = _probes(ranked, *(["h264"] * 6))
    bench = Bench(cast(Any, _FakeTorrServer()), prober=prober)
    plan = _plan(ranked)
    for number in (1, 2, 3, 4, 5):
        bench.start(plan, number)
    bench.needed = {(plan.picture.key, 1), (plan.picture.key, 2)}

    bench.start(plan, 6)

    live = sorted(prep.number for prep in bench.live())
    assert 1 in live and 2 in live, "тех, чьего ответа ждут, потолок не трогает"
    assert 3 not in live, "самый старый из ненужных и уходит"
    assert 6 in live


def test_a_neighbour_asked_about_honesty_is_dropped_once_it_has_answered(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Проверка «честного HD» спрашивает соседей по одному - и отпускает их сразу.

    До сих пор отвергнутый сосед доживал до старта показа: до трёх лишних раздач
    (:data:`~torrcast.domain.pick_settings.MAX_TRIES`) в тот самый момент, когда полоса роя нужна
    показу.
    """
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=3.20, seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, (), "h264", 574, 1150),
        Media(5977.0, (), "h264", 576, 1024),
    )
    torrserver = _FakeTorrServer()

    prep = _resolve(Bench(cast(Any, torrserver), prober=prober), ranked)

    assert prep.number == 1, "лучше 574p рядом нет - играем то, что есть"
    assert "не лучше" in capsys.readouterr().out
    assert torrserver.dropped == [f"hash-{ranked[1].magnet}"], "сосед отпущен по своему хэшу"


def test_a_neighbour_that_missed_its_budget_is_let_go_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Сосед не успел ответить за свой бюджет - раздача его тоже больше не нужна.

    Ждать перестали - значит, ответ не нужен, а раздача осталась бы висеть до общей
    уборки, доедая полосу роя у того, кого мы прямо сейчас играем. Подъём, который в его
    потоке ещё идёт, убирает себя сам: хэш к тому моменту известен только этому потоку.
    """
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=3.20, seeders=121),
    ]
    slow = f"hash-{ranked[1].magnet}"
    honest = Media(5977.0, (), "h264", 574, 1150)

    def read(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        if f"{slow}/" in url:
            time.sleep(0.6)  # сосед отвечает дольше, чем ему отмерено
            return Media(5977.0, (), "h264", 1080, 1920)
        return honest

    torrserver = _FakeTorrServer()

    prep = _resolve(Bench(cast(Any, torrserver), prober=read, honest_budget=0.05), ranked)

    assert prep.number == 1, "ответа не дождались - играем то, что уже прочитано"
    assert "не успел ответить" in capsys.readouterr().out
    deadline = time.monotonic() + 5.0
    while slow not in torrserver.dropped and time.monotonic() < deadline:
        time.sleep(0.05)
    assert torrserver.dropped == [slow], "и его раздача убрана по своему хэшу, а не по списку"


# --- Пак, который считает сезоны, но не серии (TC-139) --------------------------------


def _series_release(name: str, size_gb: float, seeders: int) -> Release:
    """Раздача сериала прямо из живой выдачи «Чёрных парусов» - именем и размером."""
    from torrcast.domain.parse_release_name import parse_release_name

    return replace(
        parse_release_name(name), size=int(size_gb * 1e9), seeders=seeders, magnet=f"magnet:{name}"
    )


def test_a_multi_season_pack_that_hides_its_bitrate_stops_outranking_the_live_one() -> None:
    """🟡 «Чёрные паруса»: перебор упирался в старьё, у которого имя молчит обо всём.

    ``[S01-04] (2014-2017) HDTV-AlexFilm`` не называет ни разрешения, ни кодека и серий
    не считает - :func:`~torrcast.usecases.rank.bitrate_of.bitrate_of` на таком молчит (``None``,
    TC-344), и раздача с ОДНИМ сидом вставала в очереди выше сериала на 61 сид. Три таких верха
    подряд - это три приговора ``mpeg4``, весь :data:`~torrcast.domain.pick_settings.MAX_TRIES` и
    130 секунд, после которых показ говорит «годного релиза нет» при живом каталоге.
    """
    from torrcast.usecases.rank.is_dated import is_dated
    from torrcast.usecases.rank.pack_mbit import pack_mbit

    tv = RUNTIME_GUESS["tv"]
    pda = _series_release(
        "Чёрные паруса / Black Sails [S01-04] (2014-2017) HDRip, WEB-DL, HDTV | КПК", 10.24, 1
    )
    hdtv = _series_release(
        "Чёрные паруса / Black Sails [S01-04] (2014-2017) HDTV-AlexFilm", 27.24, 1
    )
    honest = _series_release(
        "Черные паруса / Black Sails [S01-04] (2014-2017) BDRip 720p-AlexFilm", 114.21, 1
    )

    assert round(pack_mbit(pda, tv), 1) == 1.3
    assert round(pack_mbit(hdtv, tv), 1) == 3.4
    assert round(pack_mbit(honest, tv)) == 14
    assert is_dated(pda, tv) and is_dated(hdtv, tv)
    assert not is_dated(honest, tv), "114 ГБ на четыре сезона - настоящий 720p, не старьё"


def test_the_pack_ceiling_never_judges_a_release_only_orders_it() -> None:
    """Потолок пака - это ПОРЯДОК и только он: ворота отбора считают, как считали.

    Отдельно от :func:`~torrcast.usecases.rank.bitrate_of.bitrate_of` он живёт нарочно: тот кормит
    :func:`~torrcast.usecases.rank.is_candidate.is_candidate`, и потолок в воротах означал бы
    «слишком тяжёлый», то есть отказ показывать честный 114-гигабайтный пак.
    """
    from torrcast.usecases.rank.bitrate_of import bitrate_of
    from torrcast.usecases.rank.is_candidate import is_candidate
    from torrcast.usecases.rank.pack_mbit import pack_mbit

    tv = RUNTIME_GUESS["tv"]
    honest = _series_release(
        "Черные паруса / Black Sails [S01-04] (2014-2017) BDRip 720p-AlexFilm", 114.21, 1
    )
    assert bitrate_of(honest, tv) is None, "серий имя не считает - ворота молчат, как молчали"
    assert is_candidate(honest, tv, 16.0), "и кандидатом он остаётся"
    assert round(pack_mbit(honest, tv)) == 14, "а порядок при этом знает про него больше"

    # Имя, которое серии ПОСЧИТАЛО, потолком не судится вовсе: там есть настоящее число.
    counted = _series_release(
        "Чёрные Паруса / Black Sails / S1E1-8 of 8 (2014) [HDRip] MVO (LostFilm)", 8.91, 9
    )
    assert counted.episode_count == 8
    assert pack_mbit(counted, tv) == 0.0


def test_the_live_series_climbs_over_the_silent_one_seed_packs() -> None:
    """Порядок очереди на живой выдаче «Чёрных парусов»: 61 сид поднимается с 5-го на 3-е.

    Требований это не смягчает ни на знак - mpeg4 как отбраковывался ffprobe, так и
    отбраковывается. Меняется только то, до какого места очереди перебор доходит,
    прежде чем упрётся в бюджет попыток.
    """
    tv = RUNTIME_GUESS["tv"]
    releases = [
        _series_release(
            "Черные паруса / Black Sails [S01-04] (2014-2017) BDRip 720p-AlexFilm", 114.21, 1
        ),
        _series_release("Чёрные паруса / Black Sails [S01-04] (2014-2017) HDTV-AlexFilm", 27.24, 1),
        _series_release("Чёрные Паруса / Black Sails [S01] (2014) HDTV 720p-BaibaKo", 17.32, 1),
        _series_release(
            "Чёрные паруса / Black Sails [S01-04] (2014-2017) HDRip, WEB-DL, HDTV | КПК", 10.24, 1
        ),
        _series_release(
            "Чёрные Паруса / Black Sails / Сезоны: 1-4 / E1-38 of 38 (2014-2017) "
            "[HDRip] MVO (LostFilm)",
            32.53,
            61,
        ),
    ]

    order = [r.size for r in rank_releases(releases, tv, 16.0)]

    assert order.index(int(32.53 * 1e9)) == 2, "живой сериал третий, а не пятый"
    assert order.index(int(27.24 * 1e9)) > 2, "молчаливые односидные паки ушли ниже него"
    assert order.index(int(10.24 * 1e9)) > 2
    assert order[0] == int(114.21 * 1e9), "честный 720p с верха не сходит"


def test_a_4k_entry_is_refused_before_the_unit_only_when_there_is_nothing_to_shrink_it_with() -> (
    None
):
    """🔴 TC-222: 2160p мимо отбора (``--release N``) играется - если перекод включён.

    До TC-222 отказ был безусловным: 4К приёмник не берёт (TC-157), а перекод менял кодек,
    но не кадр. Теперь перекод ужимает и кадр, поэтому отказ остался ровно в одном
    случае - ``recode: false``, где ужимать нечем. Отказ по-прежнему стоит ДО юнита:
    ни ffmpeg, ни раздача не поднимаются, человек читает строку за доли секунды.
    """
    from torrcast.domain.entry import Entry

    config = load_config()
    uhd = Entry(title="Матрица", magnet="m", codec="hevc", depth=10, frame=2160, quality="2160p")
    assert config.recode, "умолчание - перекод включён"
    # Перекод включён - ужмём и сыграем, отказа нет ни на HEVC, ни на посильном h264.
    _refuse_hopeless(config, uhd)
    _refuse_hopeless(config, replace(uhd, codec="h264", depth=8))

    with pytest.raises(NotFoundError) as refusal:
        _refuse_hopeless(replace(config, recode=False), uhd)
    assert "2160p" in str(refusal.value) and "1080p" in str(refusal.value)

    # 1080p тем же кодеком - ровно то, ради чего сплошной перекод и заведён.
    _refuse_hopeless(replace(config, recode=False), replace(uhd, frame=1080, quality="1080p"))
    # Кадра не спрашивали (запись прежней версии) - молчим и играем как раньше.
    _refuse_hopeless(replace(config, recode=False), replace(uhd, frame=0))


def test_releases_table_uses_true_duration_and_matches_explicit_release(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """У картины с длительностью сильно больше двух часов таблица cast releases
    и последующий --release N дают одну и ту же раздачу под одним и тем же номером.
    """
    from torrcast.domain.config import Config

    # Обе раздачи взяты ВЫШЕ потолка приёмника (10 Мбит/с) и на двух часах, и на трёх:
    # ступень :func:`fits_receiver` тут обязана молчать, иначе меряется она, а не
    # знаменатель. Лёгкая при этом остаётся кандидатом на двух часах, тяжёлая - нет,
    # и ровно на этой разнице таблица и ловится.
    lighter = rel(name="lighter", size_gb=13.2, seeders=50)
    heavy = rel(name="heavy", size_gb=20, seeders=100)

    config = Config(bitrate_warn_mbit=16.0)
    # На 2 часах heavy (20 ГБ) улетает за потолок 16 Мбит/с.
    ranked_guess = rank_releases([lighter, heavy], 120.0 * 60.0, config.bitrate_warn_mbit)

    from torrcast.domain.picture import Picture

    plan = Plan(
        picture=Picture(title="Кино", year=1999, releases=[lighter, heavy]),
        ranked=ranked_guess,
        runtime=120.0 * 60.0,
        warn_mbit=config.bitrate_warn_mbit,
    )

    def fake_search(*args: Any, **kwargs: Any) -> list[Any]:
        return [plan]

    class FakeFacts(_Facts3h):
        """Та же справка «3 ч», но объявленная рядом с прогоном, который её зовёт."""

    _cmd_releases(
        Args(query=["releases", "кино"]),
        search=fake_search,
        settings=lambda: config,
        facts_source=FakeFacts,
    )
    printed = capsys.readouterr().out

    # Таблица должна перестроить план на 3 часах и показать heavy первым,
    # так как на 3 часах его битрейт падает ниже 16 Мбит/с.
    import re

    assert re.search(r"1\s+1080p\s+20.0 ГБ", printed), (
        "таблица должна строиться на настоящей длительности"
    )

    args = Args(query=["кино"], release=1)
    assert args.release is not None
    fresh_plan = _timed(plan, cast(Any, FakeFacts([])), args, config)
    assert fresh_plan.ranked[args.release - 1].raw_name == "heavy", (
        "отбор не должен расходиться с таблицей"
    )


class _Facts3h(Facts):
    """Справка, которая на любую картину отвечает хронометражем «3 ч»."""

    def __init__(self, pictures: Iterable[tuple[str, int | None]]) -> None:
        super().__init__(pictures, 0.0, store=FakeBlurbStore(), source=FakeBlurbSource())

    def start(self) -> None:
        pass

    def finish(self) -> None:
        pass

    def get(self, title: str, year: int | None) -> Fact:
        return Fact(runtime="3 ч")


def _releases_output(capsys: pytest.CaptureFixture[str], profile_choice: Any = None) -> str:
    """Прогон ``cast releases`` над одной раздачей 18 ГБ; отдаёт напечатанное.

    Поиск и справка подменены, а вот определение профиля и сборка таблицы - настоящие:
    тест про то, по ЧЬЕМУ профилю судит таблица. 18 ГБ на трёх часах - это ~14 Мбит/с:
    осторожный профиль (порог перекода 10) подписывает такую «перекодируем», а приставка
    Android TV (порог 28) играет её копией - ровно случай TC-241.
    """
    from torrcast.domain.config import Config

    heavy = rel(name="Кино / Movie (1999) BDRip 1080p", size_gb=18, seeders=100)
    plan = Plan(
        picture=Picture(title="Кино", year=1999, releases=[heavy]),
        ranked=[heavy],
        runtime=RUNTIME,
        warn_mbit=16.0,
    )
    _cmd_releases(
        Args(query=["releases", "кино"]),
        search=lambda *args: [plan],
        settings=Config,
        facts_source=_Facts3h,
        profile_choice=profile_choice,
    )
    return capsys.readouterr().out


def test_releases_table_judges_by_the_detected_receiver_profile(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-241. Таблица обязана судить по тому приёмнику, на который поедет показ:
    обнаруженной приставке Android TV раздача на 18 ГБ едет копией, и пометка
    «перекодируем» рядом с ней - ложь, которой в таблице быть не должно."""
    from torrcast.domain.choice import Choice
    from torrcast.domain.profile import ANDROID_TV

    printed = _releases_output(
        capsys, lambda config: Choice(ANDROID_TV, "по паспорту: Xiaomi TV Stick")
    )

    assert "профиль приёмника: приставка Android TV" in printed, (
        "человек видит, по какому профилю судит таблица"
    )
    assert "перекодируем" not in printed, "приставка играет 18 ГБ копией - пометка врала"


def test_releases_table_says_by_which_profile_it_judges_without_a_receiver(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Приёмника нет вовсе - таблица не молчит, по какому профилю судит: она говорит,
    что судит по осторожному, и тогда та же раздача честно подписана «перекодируем»."""
    printed = _releases_output(capsys)

    assert "профиль приёмника: осторожный" in printed
    assert "перекодируем" in printed, "осторожный профиль такие куски перекодирует"


# --- 🔴 TC-194: экран и след говорят про одни и те же решения ------------------


def _turned_down_on_screen(printed: str) -> list[str]:
    """Номера релизов, которым на экране сказали «нет», в порядке появления.

    Строк отказа три вида, и все три - решение отбора: приговор ffprobe, «не лучше» после
    проверки честности и «не успел ответить». Ловится номер, а не формулировка: тест про
    ДУБЛЬ и ПРОПУСК, а не про то, какими словами отказ объяснён.
    """
    return re.findall(r"релиз (\d+) не (?:годится|лучше|успел ответить)", printed)


def _turned_down_in_trace() -> list[str]:
    """Те же отказы, как их видит недельная лента (`cast log` печатает эти же записи)."""
    from torrcast.adapters.filesystem.trace_journal.records import records
    from torrcast.adapters.filesystem.trace_journal.shutdown import shutdown

    shutdown()
    return [str(rec.get("release")) for rec in records() if rec.get("event") == "drop"]


def test_a_release_already_judged_is_not_turned_down_twice_on_screen(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """🔴 TC-194. Кого забраковала очередь отбора, того проверка честности не судит заново.

    Замер, с которого началось: у «Сталкера» в недельной ленте два отказа, а на экране
    человек прочитал четыре строки. Подготовка забракованного релиза остаётся в
    :attr:`~torrcast.usecases.select_bench.bench.Bench.preps` готовой - ``ffprobe`` прочитан, ответ
    есть, - и проверка честности переспрашивала её тем же
    :meth:`~torrcast.usecases.select_bench.bench.Bench._trouble` с теми же порогами. Приговор
    выходил тот же, строка печаталась вторая, а записи не было ни одной новой: экран и лента
    расходились ровно на этот дубль.
    """
    ranked = [
        rel(name="Кино [WEB-DL 1080p] a", size_gb=3.20, seeders=140),
        rel(name="Кино [WEB-DL] b", quality=None, size_gb=3.14, seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, (), "av1", 1080, 1920),  # верх обещает 1080p, а внутри av1
        Media(5977.0, (), "h264", 574, 1150),  # годен, но занижен - зовётся проверка честности
    )

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 2, "годным оказался второй - его и играем"
    assert _turned_down_on_screen(printed) == ["1"], "один отказ - одна строка, а не две"
    assert _turned_down_in_trace() == ["1"], "экран и лента обязаны сойтись число в число"


def test_a_release_turned_down_by_the_honesty_check_is_written_to_the_trace(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """🔴 TC-194. Отказ проверки честности - решение, и в ленте оно обязано лежать.

    Второй замер: у «Наруто» строка отказа на экране одна, а событий за сеанс НОЛЬ - по
    следу выходило, что отбор прошёл без единой осечки. Запись рождалась только в очереди
    отбора, а :meth:`~torrcast.usecases.select_bench.bench.Bench._honest` печатал свои отказы мимо
    неё.
    """
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", size_gb=3.20, seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, (), "h264", 574, 1150),  # верх годен, но занижен
        Media(5977.0, (), "av1", 1080, 1920),  # сосед обещает больше, а внутри av1
    )

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 1, "сосед не годится - играем то, что есть"
    assert _turned_down_on_screen(printed) == ["2"], "отказ соседа сказан человеку"
    assert _turned_down_in_trace() == ["2"], "и он же обязан лежать в недельной ленте"


def test_a_neighbour_that_is_no_better_is_a_record_of_the_trace_too(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """🔴 TC-194. «Не лучше» - тоже отказ: сосед поднят, прочитан и отвергнут.

    Отличие от негодного только в причине: этот релиз играбелен, просто врёт именем так
    же, как верх. Для разбора недели разницы нет - раздачу трогали и от неё отказались.
    """
    ranked = [
        rel(name="Кино [WEB-DL] a", quality=None, size_gb=3.14, seeders=140),
        rel(name="Кино [WEB-DL 1080p] b", codec=None, size_gb=3.20, seeders=121),
    ]
    prober = _reads(
        ranked,
        Media(5977.0, (), "h264", 574, 1150),
        Media(5977.0, (), "h264", 576, 1024),  # обещал 1080p, а внутри такой же SD
    )

    prep = _resolve(Bench(cast(Any, _FakeTorrServer()), prober=prober), ranked)

    printed = capsys.readouterr().out
    assert prep.number == 1 and "релиз 2 не лучше" in printed
    assert _turned_down_on_screen(printed) == _turned_down_in_trace() == ["2"]


class _Silent(_Spent):
    """Клиент второго круга: остаток цели тот, а индексеры молчат."""

    def search(self, query: str) -> list[Any]:
        return []


def _asked_reference(found: list[Picture], args: Args, spare: float = 9.0) -> tuple[Any, ...]:
    """Чем и с каким потолком добор спросил справку. Круг при этом пустой."""
    from torrcast.domain.facts.origin import Origin

    calls: list[tuple[Any, ...]] = []

    def _spy(name: str, series: bool | None = False, budget: float = 0.0) -> Origin:
        calls.append((name, series, budget))
        return Origin()

    with Progress(out=io.StringIO()) as progress:
        _second_language(
            cast(Any, _Silent(spare)), "клиника", args, [], found, progress, passport=_spy
        )
    return calls[0]


def test_добор_без_картины_спрашивает_справку_всерьёз() -> None:
    """🔴 TC-243. Картины не нашлось - тут справка единственная опора, и зовут её всерьёз.

    Две наши причины разом. Первая: тип картины брать было неоткуда, и справка шла самым
    слабым режимом «оба типа, верить лишь согласию» - а согласия у сериала с одноимённым
    фильмом не бывает, и имя терялось («Дедвуд», «Клиника»). Теперь тип называет сам
    запрос, если человек назвал серию. Вторая: полутора секунд на шаги 2-3 справки не
    хватает физически, поэтому безнадёжному пути отдаётся весь остаток цели.

    Счастливый путь не удлиняется: картина найдена - потолок прежний, а тип берётся у неё.
    """
    from torrcast.domain.facts.settings import FACTS_BUDGET
    from torrcast.domain.goal_spare import CIRCLE_SHARE

    empty = _asked_reference([], Args(query=["клиника", "s1e1"]))
    assert empty == ("клиника", True, pytest.approx(9.0 - CIRCLE_SHARE))

    lean = Picture(title="Клиника", year=2001, kind="tv", releases=[rel(name="Клиника s01e01")])
    thin = _asked_reference([lean], Args(query=["клиника", "s1e1"]))
    assert thin == ("клиника", True, FACTS_BUDGET), "картина есть - потолок прежний, тип от неё"


class _Ceiling(_Spent):
    """Клиент второго круга: индексер упёрся в потолок, ответ уточнения заготовлен."""

    capped = ("RuTor",)

    def __init__(self, spare: float, rows: list[Any]) -> None:
        super().__init__(spare)
        self._rows = rows
        self.asked: list[str] = []

    def search(self, query: str) -> list[Any]:
        self.asked.append(query)
        return self._rows


class _LateSecond(_Ceiling):
    """Второй круг пуст, но хвост первого уже завершился."""

    def __init__(self, rows: list[Any]) -> None:
        super().__init__(9.0, [])
        self._late_rows = rows

    def late(self) -> list[Any]:
        rows, self._late_rows = self._late_rows, []
        return rows


def test_добор_учитывает_готовую_опоздавшую_выдачу() -> None:
    """TC-410. Хвост первого круга участвует в отборе до показа списка.

    У раздачи нет латинской подписи, поэтому пустой второй круг её не повторит. Она уже
    доехала к окончанию добора - ждать сверх бюджета не требуется.
    """
    from torrcast.domain.facts.origin import Origin
    from torrcast.domain.raw_result import RawResult

    late = [RawResult("Клиника S01 1080p", "e" * 40, 15 * 1024**3, 30)]
    client = _LateSecond(late)

    with Progress(out=io.StringIO()) as progress:
        raw, _pictures, found = _second_language(
            cast(Any, client),
            "клиника",
            Args(query=["клиника", "s1e1"]),
            [],
            [],
            progress,
            passport=lambda *a, **k: Origin(title="Scrubs", year=2001, name="Клиника"),
        )

    assert client.asked == ["Scrubs"], "добор вторым именем действительно состоялся"
    assert len(raw) == 1
    assert [picture.title for picture in found] == ["Клиника"]
    assert client.late() == [], "готовый хвост забирается один раз"


def test_короткое_имя_берёт_картину_из_первого_пула_по_паспорту() -> None:
    """TC-411. Полное паспортное имя выбирает уже приехавшую картину без нового круга.

    Короткое ``lain`` само указывает на журнал, поэтому вес выдачи не может быть
    разрешением на подмену. Паспорт независимо называет сериал и его год - только эта
    пара даёт право выбрать сериал из того же пула.
    """
    from torrcast.adapters.prowlarr.to_releases import to_releases
    from torrcast.domain.cluster import cluster
    from torrcast.domain.facts.origin import Origin
    from torrcast.domain.pick_franchise import pick_franchise
    from torrcast.domain.raw_result import RawResult

    raw = [
        RawResult("lainzine 1-5 (2024) PDF", "a" * 40, 100 * 1024**2, 2),
        RawResult("Serial Experiments Lain (1998) BDRip 1080p", "b" * 40, 12 * 1024**3, 40),
    ]
    pictures = cluster(to_releases(raw))
    found = pick_franchise("lain", pictures)
    client = _Ceiling(9.0, [])
    passport = Origin(title="Serial Experiments Lain", year=1998, name="Эксперименты Лэйн")

    with Progress(out=io.StringIO()) as progress:
        _raw, _pictures, rescued = _second_language(
            cast(Any, client),
            "lain",
            Args(query=["lain"]),
            raw,
            found,
            progress,
            passport=lambda *a, **k: passport,
        )

    assert [picture.title for picture in found] == ["lainzine 1-5"], "короткое имя неоднозначно"
    assert [(picture.title, picture.year) for picture in rescued] == [
        ("Serial Experiments Lain", 1998)
    ]
    assert client.asked == [], "картина уже в первом пуле - новый круг не нужен"


def test_паспортное_имя_не_подменяет_картину_при_споре_года() -> None:
    """Короткое имя не получает права выбрать тёзку с годом вопреки паспорту."""
    from torrcast.adapters.prowlarr.to_releases import to_releases
    from torrcast.domain.cluster import cluster
    from torrcast.domain.facts.origin import Origin
    from torrcast.domain.pick_franchise import pick_franchise
    from torrcast.domain.raw_result import RawResult

    raw = [
        RawResult("lainzine 1-5 (2024) PDF", "c" * 40, 100 * 1024**2, 2),
        RawResult("Serial Experiments Lain (2025) WEB-DL 1080p", "d" * 40, 8 * 1024**3, 9),
    ]
    pictures = cluster(to_releases(raw))
    client = _Ceiling(9.0, [])
    passport = Origin(title="Serial Experiments Lain", year=1998)

    with Progress(out=io.StringIO()) as progress:
        _raw, _pictures, found = _second_language(
            cast(Any, client),
            "lain",
            Args(query=["lain"]),
            raw,
            pick_franchise("lain", pictures),
            progress,
            passport=lambda *a, **k: passport,
        )

    assert [picture.title for picture in found] == ["lainzine 1-5"], (
        "спор года сильнее совпавшего длинного имени"
    )


def _nine_yards_pool() -> tuple[list[Any], list[Picture], list[Picture]]:
    """Пул запроса «девять»: сотня строк про соседей, самой «Девять» в ней нет."""
    from torrcast.adapters.prowlarr.to_releases import to_releases
    from torrcast.domain.cluster import cluster
    from torrcast.domain.pick_franchise import pick_franchise
    from torrcast.domain.raw_result import RawResult

    raw = [
        RawResult(
            "Девять ярдов / The Whole Nine Yards (2000) BDRip 1080p", "a" * 40, 8 * 1024**3, 50
        )
    ]
    pictures = cluster(to_releases(raw))
    return raw, pictures, pick_franchise("девять", pictures)


def _refined(
    about: Any,
    rows: list[Any],
) -> tuple[_Ceiling, io.StringIO, tuple[list[Any], list[Picture], list[Picture]]]:
    raw, pictures, found = _nine_yards_pool()
    client = _Ceiling(9.0, rows)
    out = io.StringIO()
    with Progress(out=out) as progress:
        result = _ceiling_reinforce(
            cast(Any, client),
            "девять",
            Args(query=["девять"]),
            raw,
            pictures,
            found,
            progress,
            passport=lambda *a, **k: about,
        )
    return client, out, result


def test_потолок_прячет_картину_и_добор_её_достаёт() -> None:
    """🔴 TC-331. Выдача упёрлась в потолок, самой картины в ней нет - уточняем запрос.

    Живой случай: по запросу «девять» 21 раздача картины «Девять» (2009) лежит за
    сотней строк потолка индексера, каталог её не видит вовсе, и в меню человек
    получает «Девять ярдов». Уточнённый запрос «девять 2009» (год - из справки) сужает
    выдачу так, что картина влезает под потолок, и встаёт в меню ВПЕРЕДИ соседей по
    подстроке - с честной строкой о том, что произошло.
    """
    from torrcast.domain.facts.origin import Origin
    from torrcast.domain.raw_result import RawResult

    rows = [RawResult("Девять / Nine (2009) BDRip 1080p | D", "b" * 40, 9 * 1024**3, 7)]
    client, out, (_raw, _pictures, found) = _refined(
        Origin(title="Nine", year=2009, name="Девять"), rows
    )

    assert client.asked == ["девять 2009"], "второй круг - уточнённым запросом"
    assert [p.title for p in found] == ["Девять", "Девять ярдов"], (
        "картина с именем запроса встаёт впереди соседей по подстроке"
    )
    assert found[0].year == 2009
    assert "упёрлась в потолок" in out.getvalue(), "подмена не молчаливая"


def test_уточнение_не_идёт_за_именем_без_поручительства() -> None:
    """🔴 Гейт TC-253: имя, лишь признанное похожим, второго круга не заказывает."""
    from torrcast.domain.facts.origin import Origin
    from torrcast.domain.raw_result import RawResult

    rows = [RawResult("Девять / Nine (2009) BDRip 1080p | D", "b" * 40, 9 * 1024**3, 7)]
    about = Origin(title="Nine", year=2009, name="Девять", guessed=True)
    client, _out, (raw, _pictures, found) = _refined(about, rows)

    assert client.asked == [], "имени без поручительства второй круг не достаётся"
    assert [p.title for p in found] == ["Девять ярдов"], "выдача остаётся прежней"
    assert len(raw) == 1


def test_уточнению_нужен_год_справки() -> None:
    """Года у справки нет - уточнять нечем, и второго круга нет вовсе."""
    from torrcast.domain.facts.origin import Origin
    from torrcast.domain.raw_result import RawResult

    rows = [RawResult("Девять / Nine (2009) BDRip 1080p | D", "b" * 40, 9 * 1024**3, 7)]
    client, _out, (_raw, _pictures, found) = _refined(Origin(title="Nine", name="Девять"), rows)

    assert client.asked == []
    assert [p.title for p in found] == ["Девять ярдов"]


def test_уточнение_не_берёт_картину_с_чужим_именем_и_годом() -> None:
    """Уточнённый круг привёз соседей - прежняя выдача остаётся, подмены нет."""
    from torrcast.domain.facts.origin import Origin
    from torrcast.domain.raw_result import RawResult

    rows = [
        RawResult(
            "Десять ярдов / The Whole Ten Yards (2004) BDRip 1080p", "c" * 40, 8 * 1024**3, 15
        )
    ]
    about = Origin(title="Nine", year=2009, name="Девять")
    client, out, (_raw, _pictures, found) = _refined(about, rows)

    assert client.asked == ["девять 2009"], "круг был - но ничего подписанного «девять»"
    assert [p.title for p in found] == ["Девять ярдов"], "соседи добором не считаются"
    assert "упёрлась в потолок" not in out.getvalue(), "не случилось - не говорим"


def test_повод_потолка_узок() -> None:
    """Три условия разом: потолок у индексера, пул не пуст, имени запроса в каталоге нет."""
    _raw, pictures, found = _nine_yards_pool()
    spare = cast(Any, _Spent(9.0))
    capped = cast(Any, _Ceiling(9.0, []))

    assert not ceiling_hides_name(spare, "девять", pictures, found), "нет потолка - нет повода"
    assert not ceiling_hides_name(capped, "девять", pictures, []), (
        "пустая выдача - это тощий пул, а не потолок: там отвечает добор вторым языком"
    )
    assert not ceiling_hides_name(capped, "девять ярдов", pictures, found), (
        "имя в каталоге есть - обрезан лишь хвост, и это не повод"
    )
    assert ceiling_hides_name(capped, "девять", pictures, found)


def test_потолок_не_принимает_сиквел_за_спрошенную_первую_часть() -> None:
    pictures = cluster(
        [
            parse_release_name("Лёд 3 (2024) WEB-DL 1080p"),
            parse_release_name("Замёрзшие мертвецы / Лёд / Glacé (2016) WEB-DL 1080p"),
        ]
    )
    found = pick_franchise("лёд", pictures)
    capped = cast(Any, _Ceiling(9.0, []))
    assert ceiling_hides_name(capped, "лёд", pictures, found)


def test_two_pictures_under_one_name_and_year_are_named_out_loud() -> None:
    """🔴 TC-371. Развести пару нечем - значит человек читает о ней строкой.

    Именем «Девять» и годом 2009 в русском прокате подписаны мюзикл ``Nine`` и мультфильм
    ``9``. Оба признака отбора - имя и год - у них совпадают, и в одну кучку их сводит сам
    каталог: больше в раздачах не сказано ничего. Молчаливой подмены тут быть не должно, а
    развести пару может только независимый источник - справка знает обе картины.
    """
    from torrcast.domain.facts.origin import Origin

    plan = _franchise_plan("Девять", 2009, [rel(name="Девять / Nine (2009) BDRip 1080p")])
    about = Origin(title="Nine", year=2009, namesake="9 (мультфильм, 2009)")
    note = namesake_note(plan, about)

    assert note and "\n" not in note, "строка одна"
    assert "«9 (мультфильм, 2009)»" in note and "2009" in note, note


def test_the_namesake_line_stays_silent_where_it_should() -> None:
    """Ограждения строки про двусмысленность: тёзки нет, года нет, год разъехался.

    Год, разошедшийся со справкой, - самый важный случай: паспорт приехал про ДРУГУЮ
    картину, и её тёзка к выбранной отношения не имеет. Про сам разъезд человек читает
    своей строкой (:func:`~torrcast.usecases.choice.year_note.year_note`), и валить их в кучу
    нельзя.
    """
    from torrcast.domain.facts.origin import Origin

    plan = _franchise_plan("Девять", 2009, [rel(name="Девять / Nine (2009) BDRip 1080p")])
    assert namesake_note(plan, Origin(title="Nine", year=2009)) == "", "тёзки нет - молчим"
    assert namesake_note(plan, Origin(namesake="9 (мультфильм, 2009)")) == "", (
        "года справка не назвала - сверять нечем"
    )
    other = Origin(title="Nine", year=1957, namesake="Девять дней одного года")
    assert namesake_note(plan, other) == "", "справка про другую картину - и тёзка её"
    unknown = _franchise_plan("Девять", None, [rel(name="Девять BDRip")])
    assert namesake_note(unknown, Origin(title="Nine", year=2009, namesake="9")) == ""
