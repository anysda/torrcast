"""Отбор до каста: чем считается битрейт, куда девается пул и что мы не досказали.

Три дефекта, найденные на замере тысячи запросов, и все три - молчаливые:

* битрейт релиза считался от ПРИКИДКИ «фильм это два часа», и у «Интерстеллара»
  (2 ч 49 мин) знаменатель занижен в 1.41 раза - честный 1080p отсекался потолком,
  которого он не переходил;
* 895 раздач из 3164 не доезжали до очереди отбора вообще: ни строки на экране,
  ни события в недельном следе;
* показ уезжал в 720p при живом 1080p в той же выдаче, и об этом не говорилось ни слова.

Имена раздач тут короткие и синтетические, а числа - живые: размеры подобраны так,
чтобы разница между прикидкой и настоящей длительностью решала исход.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from torrcast import trace
from torrcast.cli import (
    Args,
    _Bench,
    _plan_for,
    _Prep,
    _timed,
    bitrate_of,
    drop_reason,
    is_candidate,
    queue_drops,
    stepdown_note,
)
from torrcast.facts import Fact, Facts, hms, minutes_of
from torrcast.parse import Picture, Release, parse_release_name
from torrcast.state import Config
from torrcast.stream import RUNTIME_GUESS, Media

GB = 1024**3
GUESS = RUNTIME_GUESS["movie"]
#: «Интерстеллар»: 2 ч 49 мин против прикидки в два часа - знаменатель врёт в 1.41 раза.
INTERSTELLAR = 169 * 60.0


def named(name: str, *, size_gb: float, seeders: int) -> Release:
    return replace(parse_release_name(name), size=int(size_gb * GB), seeders=seeders)


def facts_with(title: str, year: int | None, runtime: str) -> Facts:
    """Справка, которая уже приехала: сети тут нет и не будет."""
    facts = Facts([])
    facts.start()
    facts.found[(title, year)] = Fact(rating="IMDb 8.6", runtime=runtime)
    return facts


# --- TC-185: знаменатель битрейта -------------------------------------------


@pytest.mark.parametrize(
    "text, minutes",
    [("2 ч 49 мин", 169), ("2 ч", 120), ("47 мин", 47), ("", 0), ("около двух часов", 0)],
)
def test_runtime_string_reads_back_as_minutes(text: str, minutes: int) -> None:
    """Хронометраж справки - готовая строка, и число из неё достаётся обратно."""
    assert minutes_of(text) == minutes
    if minutes:
        assert minutes_of(hms(minutes)) == minutes


def test_the_guess_inflates_the_bitrate_of_a_long_film() -> None:
    """Один и тот же файл: по прикидке 19.7 Мбит/с, по настоящей длительности 14.0."""
    release = named("Интерстеллар / Interstellar (2014) BDRip 1080p | D", size_gb=16.5, seeders=90)

    assert bitrate_of(release, GUESS) == pytest.approx(19.7, abs=0.1)
    assert bitrate_of(release, INTERSTELLAR) == pytest.approx(14.0, abs=0.1)
    assert not is_candidate(release, GUESS, 16.0), "прикидка выкидывает честный 1080p"
    assert is_candidate(release, INTERSTELLAR, 16.0), "настоящая длительность его возвращает"


def test_the_reference_runtime_returns_an_honest_1080p_to_the_queue() -> None:
    """Справка назвала 2 ч 49 мин - и 1080p, отсеянный арифметикой, снова в очереди.

    Потолок при этом не двигается ни на знак: и до, и после он тот же самый, меняется
    только знаменатель, которым считают битрейт.
    """
    full = named("Интерстеллар / Interstellar (2014) BDRip 1080p | D", size_gb=16.5, seeders=90)
    small = named("Интерстеллар / Interstellar (2014) WEB-DL 720p | D", size_gb=4.0, seeders=120)
    picture = Picture(title="Интерстеллар", year=2014, releases=[full, small])
    args = Args(query=["интерстеллар"])
    config = Config(recode=False)  # потолок отбора - ровно bitrate_warn_mbit

    blind = _plan_for(picture, args, config)
    assert not blind.runtime_known
    assert blind.candidates(args) == [1], "по прикидке годен только 720p"
    assert blind.ranked[0] is small

    plan = _timed(blind, facts_with("Интерстеллар", 2014, "2 ч 49 мин"), args, config)

    assert plan.runtime == INTERSTELLAR
    assert plan.runtime_known
    assert plan.warn_mbit == blind.warn_mbit, "чинится знаменатель, а не потолок"
    assert plan.ranked[0] is full, "живой 1080p вернулся и встал верхом"
    assert len(plan.candidates(args)) == 2


def test_without_a_reference_the_guess_stays_but_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Справка молчит - план остаётся на прикидке, и это видно в следе, а не молча."""
    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setenv(trace.SID_ENV, "test-runtime")
    picture = Picture(
        title="Нелюбовь",
        year=2017,
        releases=[named("Нелюбовь (2017) BDRip 1080p | D", size_gb=8.0, seeders=40)],
    )
    args = Args(query=["нелюбовь"])
    before = _plan_for(picture, args, Config())

    plan = _timed(before, facts_with("Нелюбовь", 2017, ""), args, Config())
    trace.shutdown()

    assert plan is before, "пересобирать план не на чем"
    assert not plan.runtime_known
    rows = trace.records()
    runtime = [r for r in rows if r.get("event") == "runtime"]
    assert runtime and runtime[-1]["src"] == "guess"
    assert "прикидка" in trace.digest(rows)


def test_already_warmed_releases_move_with_the_new_order() -> None:
    """Порядок пересобрали - прогрев переехал вместе с ним, а не остался на цифре.

    Прогрев под меню заводится по номеру релиза, и без переезда ключей номер 1 после
    пересборки отдал бы показу совсем другую раздачу: та же цифра, другой магнит.
    """
    full = named("Интерстеллар / Interstellar (2014) BDRip 1080p | D", size_gb=16.5, seeders=90)
    small = named("Интерстеллар / Interstellar (2014) WEB-DL 720p | D", size_gb=4.0, seeders=120)
    picture = Picture(title="Интерстеллар", year=2014, releases=[full, small])
    args = Args(query=["интерстеллар"])
    config = Config(recode=False)
    blind = _plan_for(picture, args, config)
    bench = _Bench(cast(Any, None))
    warmed = _Prep(number=1, release=blind.ranked[0])
    bench.preps[(picture.key, 1)] = warmed

    plan = bench.reorder(
        blind, _timed(blind, facts_with("Интерстеллар", 2014, "2 ч 49 мин"), args, config)
    )

    assert plan.ranked[0] is full, "верх сменился - иначе проверять нечего"
    assert warmed.number == 2, "прогретый 720p переехал на своё новое место"
    assert bench.preps[(picture.key, 2)] is warmed
    assert (picture.key, 1) not in bench.preps


def test_a_hand_picked_release_keeps_the_number_the_table_showed() -> None:
    """``--release N`` играет ровно ту раздачу, что стояла под номером N в таблице.

    🔴 TC-216. Держится этот инвариант теперь не заслонкой, а тем, что ОБЕ стороны
    считают битрейт по одной длительности: ``cast releases`` спрашивает справку так же,
    как путь показа. Раньше таблица строилась на прикидке «фильм это два часа», и
    заслонка в :func:`_timed` запрещала пересобирать порядок под названный номер -
    порядок сходился ценой того, что таблица врала про битрейт.
    """
    full = named("Интерстеллар / Interstellar (2014) BDRip 1080p | D", size_gb=16.5, seeders=90)
    small = named("Интерстеллар / Interstellar (2014) WEB-DL 720p | D", size_gb=4.0, seeders=120)
    picture = Picture(title="Интерстеллар", year=2014, releases=[full, small])
    config = Config(recode=False)
    facts = facts_with("Интерстеллар", 2014, "2 ч 49 мин")

    shown = _timed(
        _plan_for(picture, Args(query=["интерстеллар"]), config),
        facts,
        Args(query=["интерстеллар"]),
        config,
    )
    named_by_hand = Args(query=["интерстеллар"], release=2)
    played = _timed(_plan_for(picture, named_by_hand, config), facts, named_by_hand, config)

    assert [r.title for r in played.ranked] == [r.title for r in shown.ranked], (
        "номер из таблицы означает ту же раздачу на показе"
    )
    assert played.runtime == shown.runtime, "длительность у таблицы и у показа одна"


# --- TC-186: счёт отсева сходится с пулом -----------------------------------


def _mixed_picture() -> Picture:
    """Пул, в котором есть каждая причина отсева сразу - и годные тоже."""
    return Picture(
        title="Кино",
        year=1999,
        releases=[
            named("Кино / Movie (1999) BDRip 1080p | D", size_gb=8.0, seeders=200),
            named("Кино / Movie (1999) WEB-DL 720p | D", size_gb=4.0, seeders=140),
            named("Кино / Movie (1999) BDRemux 2160p | D", size_gb=80.0, seeders=30),
            named("Кино / Movie (1999) BDRip 1080p HEVC | D", size_gb=6.0, seeders=25),
            named("Кино / Movie (1999) DVD9 ISO", size_gb=7.5, seeders=12),
            named("Кино / Movie (1999) DVDRip | D", size_gb=1.4, seeders=60),
            named("Кино / Movie (1999) Complete", size_gb=5.0, seeders=9),
        ],
    )


def test_every_release_of_the_pool_is_either_queued_or_counted_out() -> None:
    """Сумма «в очереди + выкинуто по причинам» сходится с пулом картины - до штуки."""
    picture = _mixed_picture()
    args = Args(query=["кино"])
    plan = _plan_for(picture, args, Config())
    queue = plan.candidates(args)

    drops = queue_drops(plan, queue)

    assert len(queue) + sum(drops.values()) == len(picture.releases)
    assert drops, "выкинутые есть, и они названы"
    assert all(count > 0 for count in drops.values())


def test_a_single_film_outranks_a_more_seeded_collection() -> None:
    """Дилогия остаётся запасной: одиночная раздача не требует угадывать файл части."""
    collection = named("Брат. Дилогия (1997-2000) WEB-DL 1080p", size_gb=13.1, seeders=7)
    single = named("Брат (1997) WEB-DL 1080p", size_gb=5.4, seeders=5)
    picture = Picture(title="Брат", year=1997, releases=[collection, single])

    plan = _plan_for(picture, Args(query=["брат"]), Config())

    assert plan.ranked == [single, collection]


def test_a_dropped_release_is_named_by_the_reason_it_was_dropped() -> None:
    """У каждой причины своё имя, и это имя того шага, на котором раздачу выкинули."""
    picture = _mixed_picture()
    args = Args(query=["кино"])
    plan = _plan_for(picture, args, Config())

    reasons = {r.raw_name: drop_reason(r, plan) for r in plan.ranked}

    assert reasons["Кино / Movie (1999) DVD9 ISO"] == "образ диска"
    assert reasons["Кино / Movie (1999) BDRip 1080p HEVC | D"].startswith("hevc")
    assert reasons["Кино / Movie (1999) DVDRip | D"] == "источник не HD"
    assert reasons["Кино / Movie (1999) Complete"] == "имя молчит о качестве"


def test_releases_without_the_asked_season_are_counted_too() -> None:
    """Раздачи, отсеянные сезонным фильтром, тоже в счёте: до сих пор их не было нигде."""
    first = named("Сериал / Series S01 (2019) WEB-DL 1080p | D", size_gb=20.0, seeders=80)
    second = named("Сериал / Series S02 (2020) WEB-DL 1080p | D", size_gb=20.0, seeders=70)
    picture = Picture(title="Сериал", year=2019, kind="tv", releases=[first, second])
    args = Args(query=["сериал", "s1e1"])
    plan = _plan_for(picture, args, Config())
    queue = plan.candidates(args)

    drops = queue_drops(plan, queue)

    assert plan.off_season == 1, "второй сезон в план не попал вовсе"
    assert drops["нужного сезона нет"] == 1
    assert len(queue) + sum(drops.values()) == len(picture.releases)


def test_the_drop_summary_is_readable_in_the_log() -> None:
    """`cast log` показывает пул, очередь и отсев одной строкой, а не сотней событий."""
    rows = [
        {
            "at": 1.0,
            "sid": "s",
            "phase": "select",
            "event": "queue",
            "pool": 41,
            "queued": 12,
            "dropped": {"образ диска": 4, "тяжелее потолка": 25},
        }
    ]

    text = trace.digest(rows)

    assert "пул 41: в очереди 12, выкинуто 29" in text
    assert "образ диска 4" in text


# --- TC-187: строка о снижении ступени --------------------------------------


def _stepdown_plan() -> tuple[Picture, Args]:
    """«Форрест Гамп»: живой 720p верхом и живые 1080p ниже - ровно как в выдаче."""
    picture = Picture(
        title="Форрест Гамп",
        year=1994,
        releases=[
            named("Форрест Гамп / Forrest Gump (1994) WEB-DL 720p | D", size_gb=4.0, seeders=41),
            named("Форрест Гамп / Forrest Gump (1994) BDRip 1080p | D", size_gb=9.0, seeders=2),
        ],
    )
    return picture, Args(query=["форрест гамп"])


def test_taking_a_lower_step_says_so_in_one_line() -> None:
    """Взяли 720p при живом 1080p в очереди - строка называет релиз, сиды и причину."""
    picture, args = _stepdown_plan()
    plan = _plan_for(picture, args, Config())
    assert plan.ranked[0].height == 720, "верхом стоит обсиженный 720p"

    line = stepdown_note(plan, 1, Media(height=720, width=1280), [1, 2], {}, 1)

    assert line == "взял 720p, рядом был 1080p (релиз 2, сидов 2) - не дошли"


def test_a_rejected_neighbour_is_named_with_its_verdict() -> None:
    """Лучшего трогали и отбраковали - в строке стоит его приговор, а не «не дошли»."""
    picture, args = _stepdown_plan()
    plan = _plan_for(picture, args, Config())

    line = stepdown_note(plan, 1, Media(height=720, width=1280), [2, 1], {2: "рой молчит"}, 2)

    assert "отбраковали (рой молчит)" in line


def test_a_silent_neighbour_is_not_called_rejected() -> None:
    """До ответа роя приговора релизу нет: кончилось только наше ожидание."""
    picture, args = _stepdown_plan()
    plan = _plan_for(picture, args, Config())

    line = stepdown_note(plan, 1, Media(height=720, width=1280), [2, 1], {}, 2)

    assert line.endswith("не ответил")
    assert "отбраковали" not in line


def test_a_dead_swarm_above_is_named_dead() -> None:
    """1080p в выдаче есть, а сидов у него ноль: это не «не дошли», это мёртвый рой."""
    top = named("Зелёная миля (1999) WEB-DL 720p | D", size_gb=4.0, seeders=38)
    dead = named("Зелёная миля (1999) BDRip 1080p | D", size_gb=9.0, seeders=0)
    picture = Picture(title="Зелёная миля", year=1999, releases=[top, dead])
    args = Args(query=["зелёная миля"])
    plan = _plan_for(picture, args, Config())

    line = stepdown_note(plan, 1, Media(height=720, width=1280), [1], {}, 1)

    assert "рой мёртв" in line


def test_the_step_is_judged_by_the_passport_not_by_the_name() -> None:
    """Имя обещало 1080p, ffprobe увидел 574p - ступень считается по паспорту.

    И обратный случай: паспорт подтвердил 1080p, и говорить не о чем - строки нет.
    """
    top = named("Кино / Movie (2024) WEB-DL 1080p | D", size_gb=6.0, seeders=140)
    rival = named("Кино / Movie (2024) BDRip 1080p | D", size_gb=13.0, seeders=121)
    picture = Picture(title="Кино", year=2024, releases=[top, rival])
    args = Args(query=["кино"])
    plan = _plan_for(picture, args, Config())

    lied = stepdown_note(plan, 1, Media(height=574, width=1150), [1, 2], {}, 1)
    honest = stepdown_note(plan, 1, Media(height=1080, width=1920), [1, 2], {}, 1)

    assert lied.startswith("взял 574p, рядом был 1080p")
    assert honest == "", "паспорт подтвердил обещанное - сообщать нечего"


def test_nothing_is_said_when_nothing_better_was_there() -> None:
    """Лучшего в выдаче не было - лишней строки на показе нет."""
    only = named("Кино / Movie (2024) WEB-DL 720p | D", size_gb=4.0, seeders=40)
    worse = named("Кино / Movie (2024) DVDRip | D", size_gb=1.4, seeders=90)
    picture = Picture(title="Кино", year=2024, releases=[only, worse])
    args = Args(query=["кино"])
    plan = _plan_for(picture, args, Config())

    assert stepdown_note(plan, 1, Media(height=720, width=1280), [1], {}, 1) == ""
