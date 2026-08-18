"""Решение об упаковке: где ждать, где перепаковать и где честно сказать «не будет»."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import FakeProc, feed, grid, lay, packer, tract, vault
from torrcast.usecases.feed_pack.feed_steer import _steer

if TYPE_CHECKING:
    from pathlib import Path


def test_a_finished_show_is_never_diagnosed_again(tmp_path: Path) -> None:
    """Показ кончился - разбираться не с чем, а труп прогона не новость.

    Проверка стоит первой намеренно: на стыке серий сюда приходит приёмник с живого
    keep-alive прошлой серии и раньше получал «упаковка оборвалась» про наш же ffmpeg.
    """
    asked: list[int] = []
    show = feed(tmp_path)
    show.fatal = "показ окончен"

    assert _steer(show, 1, asked.append) is False and asked == []


def test_a_skipped_place_is_kept_silent_and_never_repacked(tmp_path: Path) -> None:
    """🔴 TC-501. Пропущенное место отвечается тишиной: 404 приёмник переживает хуже.

    И перепаковку такое ожидание не поднимает: тяжёлый кусок детерминирован, и второй
    прогон над ним получит ровно ту же копию.
    """
    asked: list[int] = []
    show = feed(tmp_path)
    show.skipped.add(4)

    assert _steer(show, 4, asked.append) is True and asked == []


def test_a_piece_finished_by_this_very_publish_is_not_a_seek_back(tmp_path: Path) -> None:
    """Кусок допаковался ровно этим publish - обычный ход показа, а не перемотка назад.

    Без этой проверки он был бы «ниже края, а файла нет»: замер - перезапуск на
    каждом четвёртом сегменте.
    """
    tract()
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 0)
    lay(show.packer.run, 1)

    assert _steer(show, 0, asked.append) is True
    assert asked == [] and (show.out / "v0.ts").exists()


def test_a_run_that_read_the_input_to_the_end_promises_nothing_beyond_its_edge(
    tmp_path: Path,
) -> None:
    """Упаковка честно дошла до конца входа - за краем файла не будет, и это не 404 зря."""
    tract()
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out, proc=FakeProc(code=0))

    assert _steer(show, 5, asked.append) is False and asked == []


def test_the_wait_is_measured_in_seconds_of_film_and_not_in_segments(
    tmp_path: Path, journal: Path
) -> None:
    """«Вот-вот» - это про ВРЕМЯ: семь сегментов вперёд - это семьдесят секунд чтения.

    Замер на живом Q70D: перемотка +116 с внутри прогона стоила 57.8 с чёрного экрана,
    пока показ считал её обычным ходом.
    """
    fake = tract(now=100.0)
    asked: list[int] = []
    show = feed(tmp_path, grid=grid(600.0, 10.0), jump=15.0)
    show.packer = packer(
        tmp_path,
        first=0,
        edge=0,
        out=show.out,
        rate=1.0,
        burst=0.0,
        at=0.0,
        began=100.0,
        now=fake.monotonic,
    )

    # Планка чтения стоит на нуле фильма: сегмент 1 (10 с) достанут через 10 с - ждём.
    assert _steer(show, 1, asked.append) is True and asked == []
    # Сегмент 5 (50 с) - это пятьдесят секунд ожидания, дешевле перепаковать.
    fake.now = 100.0
    show.restarted = 0.0
    assert _steer(show, 5, asked.append) is True and asked == [5]


def test_neighbours_never_restart_the_packing_all_at_once(tmp_path: Path) -> None:
    """После перемотки приёмник просит куски пачкой: перезапустить обязан ровно первый."""
    fake = tract(now=100.0)
    asked: list[int] = []
    show = feed(tmp_path)

    assert _steer(show, 3, asked.append) is True and asked == [3]
    assert show.restarted == 100.0

    fake.now = 101.5
    assert _steer(show, 4, asked.append) is True and asked == [3], "сосед толкнул упаковку"

    fake.now = 103.0
    assert _steer(show, 4, asked.append) is True and asked == [3, 4]


def test_a_published_piece_means_the_source_reads_again(tmp_path: Path) -> None:
    """Прогон что-то выложил - значит сеть вернулась: признак обрыва снимается сам."""
    tract(now=500.0)
    asked: list[int] = []
    show = feed(tmp_path, vault=vault(tmp_path))
    show.offline = "источник молчит"
    show.moved = 0.0
    show.packer = packer(tmp_path, first=0, edge=0, out=show.out)

    _steer(show, 9, asked.append)

    assert show.offline == "" and show.moved == 500.0


def test_a_silent_source_on_a_dead_network_is_not_pushed_every_two_seconds(tmp_path: Path) -> None:
    """Пока источник не читается, подъём ffmpeg стоит секунды и не даёт ничего: ждём дольше."""
    fake = tract(now=100.0)
    asked: list[int] = []
    show = feed(tmp_path, vault=vault(tmp_path))
    show.offline = "источник не читается"
    show.restarted = 97.0

    assert _steer(show, 1, asked.append) is True and asked == []

    fake.now = 103.0
    assert _steer(show, 1, asked.append) is True and asked == [1]
