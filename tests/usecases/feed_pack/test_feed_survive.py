"""Два вида обрыва: молчащий вход при живом ffmpeg и мёртвый ffmpeg при живой сети."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import FakeProc, feed, lay, packer, tract, vault
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.hls_settings import MUTE_SECONDS
from torrcast.usecases.feed_pack.feed_survive import _mute, _survive
from torrcast.usecases.feed_pack.feed_sweep import _sweep

if TYPE_CHECKING:
    from pathlib import Path


def test_a_source_silent_longer_than_the_clock_is_the_same_break_as_a_dead_ffmpeg(
    tmp_path: Path,
) -> None:
    """Пропавший интернет при живом TorrServer вход не рвёт: ffmpeg висит, а показ молчал.

    Замер на живом Q70D: показ доел прогретое, встал в BUFFERING и 2.5 минуты не сказал
    ни слова, после чего приёмник сам перегрузил фильм с нуля.
    """
    fake = tract(now=1000.0)
    said: list[str] = []
    show = feed(tmp_path, vault=vault(tmp_path), log=said.append)
    show.moved = 1000.0

    fake.now = 1000.0 + MUTE_SECONDS
    _mute(show)
    assert show.offline == "" and said == [], "молчание короче срока - это ещё не обрыв"

    fake.now = 1001.0 + MUTE_SECONDS
    _mute(show)

    assert show.offline == phrase("feed.source_mute_reason", secs=MUTE_SECONDS)
    assert said == [phrase("feed.source_unreadable", why=show.offline)]


def test_without_the_warmed_film_the_silence_is_indistinguishable_from_a_slow_swarm(
    tmp_path: Path,
) -> None:
    """Идти показу всё равно некуда: тут работает счёт обрывов, а не часы молчания."""
    tract(now=99999.0)
    said: list[str] = []
    show = feed(tmp_path, log=said.append)
    show.moved = 0.0

    _mute(show)

    assert show.offline == "" and said == []


def test_warmed_pieces_do_not_move_the_source_silence_clock(tmp_path: Path) -> None:
    """Часы идут от последнего байта источника, пока показ берёт прогретое."""
    fake = tract(now=900.0)
    said: list[str] = []
    show = feed(tmp_path, vault=vault(tmp_path), log=said.append)
    show.packer = packer(tmp_path, first=7, out=show.out)
    lay(show.packer.run, 7, size=100)

    fake.now = 1000.0
    _sweep(show, lambda _slot: None)
    assert show.moved == 1000.0

    fake.now += MUTE_SECONDS
    _sweep(show, lambda _slot: None)
    assert show.offline == "" and said == []

    fake.now += 1.0
    _sweep(show, lambda _slot: None)
    assert show.offline == phrase("feed.source_mute_reason", secs=MUTE_SECONDS)


def test_the_same_corpse_is_counted_once_and_not_five_times_a_second(
    tmp_path: Path,
) -> None:
    """Считаются ПРОГОНЫ, а не опросы: потоки раздачи приходят сюда каждые 0.2 с."""
    show = feed(tmp_path)
    run = packer(tmp_path, proc=FakeProc(code=1))

    assert _survive(show, run) is True and show.crashes == 1
    assert _survive(show, run) is True and show.crashes == 1


def test_a_run_we_took_down_ourselves_never_spends_an_attempt(tmp_path: Path) -> None:
    """Прогон сняли мы сами - это не обрыв: перемотка не имеет права тратить попытки."""
    show = feed(tmp_path)
    run = packer(tmp_path, proc=FakeProc(code=255), stopped="перемотка")

    assert _survive(show, run) is True and show.crashes == 0


def test_three_breaks_in_a_row_without_a_film_on_the_disk_are_a_verdict(
    tmp_path: Path,
) -> None:
    """Источника нет и показывать нечего - честная ошибка, а не бесконечный круг."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append)
    show.crashes = 3

    assert _survive(show, packer(tmp_path, proc=FakeProc(code=1))) is False
    assert show.trouble() == "silent, code 1" and said == []


def test_a_film_on_the_disk_turns_the_verdict_into_a_wait_for_the_network(
    tmp_path: Path,
) -> None:
    """Прогретое меняет смысл обрыва: «сети нет, а фильм есть» - умирать тут нельзя."""
    said: list[str] = []
    show = feed(tmp_path, vault=vault(tmp_path), log=said.append)
    show.crashes = 3

    assert _survive(show, packer(tmp_path, proc=FakeProc(code=1))) is True
    assert show.fatal == "" and show.crashes == 0
    assert show.offline == "silent, code 1"
    assert said == [phrase("feed.source_unreadable", why=show.offline)]


def test_a_zero_on_a_torn_input_is_told_as_a_fact_and_not_as_a_forecast(
    tmp_path: Path,
) -> None:
    """Ноль на оборванном прогоне - это «вход умер», а не «фильм кончился».

    Замер 15-08-2026: 80 обрывов входа на 457 прогонах дали код 0 во ВСЕХ 457.
    Обещать починку строка права не имеет: миры «вернулся» и «не вернулся» разошлись
    начисто, а на первом обрыве неизвестно, который перед нами.
    """
    said: list[str] = []
    show = feed(tmp_path, log=said.append)

    _survive(show, packer(tmp_path, proc=FakeProc(code=0)))
    torn = phrase("feed.input_torn")
    assert said == [phrase("feed.retrying", what=torn, attempt=1)]

    said.clear()
    _survive(show, packer(tmp_path, proc=FakeProc(code=-9)))
    broke = phrase("feed.pack_broke_off", why="killed by signal 9")
    assert said == [phrase("feed.retrying", what=broke, attempt=2)]
