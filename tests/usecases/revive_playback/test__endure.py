"""Зеркало терпения к жалобе упаковки: обрыв источника пережидают, а не хоронят показ."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.swarm_session import SESSION_DUR, THIN_SWARM, SwarmSession
from tests.usecases.revive_playback.world import FakeSupply, feed_with_segments
from torrcast.adapters.stream_probe.supply import Supply
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.revive_playback._endure import _endure


def test_a_silent_source_is_waited_out_and_said_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Источник не читается - показ ждёт и говорит об этом один раз, а не каждые две секунды."""
    supply = FakeSupply(silence="TorrServer не отвечает")
    feed = feed_with_segments(tmp_path)
    clock = FakeClock(now=100.0)

    said = _endure(feed, cast(StreamSource, supply), clock, "оборвано", False)
    first = capsys.readouterr().out
    again = _endure(feed, cast(StreamSource, supply), clock, "оборвано", said)
    second = capsys.readouterr().out

    assert (said, again) == (True, True)
    assert phrase("revive.source_unreadable_wait", why="TorrServer не отвечает") in first
    assert second == "", "об одной аварии говорят один раз"
    assert clock.sleeps == [2.0, 2.0], "показ ждёт возврата источника, а не крутится вхолостую"
    assert str(feed.offline) == "TorrServer не отвечает"


def test_a_source_that_just_came_back_is_given_another_try(tmp_path: Path) -> None:
    """Раздача вернулась магнитом ровно сейчас - хоронить показ было бы враньём."""
    supply = FakeSupply(restored=True)
    feed = feed_with_segments(tmp_path)
    feed.offline = "сети нет"
    clock = FakeClock(now=100.0)

    said = _endure(feed, cast(StreamSource, supply), clock, "оборвано", True)

    assert said is True
    assert str(feed.offline) == "", "обрыв снят: упаковка попробует ещё"
    assert clock.sleeps == [2.0]


def test_a_dead_packer_with_a_healthy_source_ends_the_show(tmp_path: Path) -> None:
    """Источник цел, а упаковка сдалась - за убитый ffmpeg не выдумываем, честно падаем."""
    with pytest.raises(InfraError, match=phrase("revive.pack_broke", trouble="сигнал 9")):
        _endure(
            feed_with_segments(tmp_path),
            cast(StreamSource, FakeSupply()),
            FakeClock(),
            "сигнал 9",
            False,
        )


def test_a_swarm_sagging_mid_show_is_waited_out_and_not_buried(tmp_path: Path) -> None:
    """🔴 TC-1009. Просадка ПОСРЕДИ показа - переживаемый обрыв, а не смерть показа.

    Источник тут настоящий, и спрашивают его боевой проводкой: окно наблюдений сеанса,
    поставленное в живой ответ, эту ветку убивало. Рой, доказавший себя втрое, отвечал
    «всё в порядке», а пустой ответ ведёт мимо ожидания прямо в `pack_broke`: замерено на
    той же улике - показ, который на master ждал возврата, умирал строкой упаковки.
    """
    supply = Supply(
        server=SwarmSession([64.3, 53.4, 57.0, 0.20]), torrent_hash="h", magnet="magnet:?xt=1"
    )
    supply.duration = SESSION_DUR
    for _ in range(3):  # по ходу показа рой вёз втрое сверх нужного
        supply.check()
    feed = feed_with_segments(tmp_path)
    clock = FakeClock(now=100.0)

    died, said = "", False
    try:
        said = _endure(feed, cast(StreamSource, supply), clock, "оборвано", False)
    except InfraError as exc:
        died = str(exc)

    assert died == "", "просадка посреди показа - ожидание источника, а не конец показа"
    assert said and str(feed.offline) == THIN_SWARM
    assert clock.sleeps == [2.0], "показ ждёт возврата роя, а не крутится вхолостую"
