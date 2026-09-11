"""Проверяет приёмник-вкладку: задание, снятие и обе границы молчания страницы."""

from __future__ import annotations

from pathlib import Path

from tests.fakes.clock import FakeClock
from torrcast.adapters.browser.browser_receiver import (
    GONE_AFTER,
    LEFT_AFTER,
    LOST_AFTER,
    BrowserReceiver,
)
from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_position import write_web_position
from torrcast.domain.position import Position


def test_the_tab_keeps_its_silence_limits_without_a_profile_of_its_own() -> None:
    """Сроки молчания - свойство вкладки: профиля, который бы их нёс, у неё больше нет."""
    receiver = BrowserReceiver(Path("/nonexistent"))

    assert (receiver.lost_after, receiver.gone_after, receiver.left_after) == (15.0, 60.0, 5.0)
    assert LEFT_AFTER < LOST_AFTER < GONE_AFTER


def test_play_writes_a_fresh_mailbox_and_forgets_the_last_session(tmp_path: Path) -> None:
    receiver = BrowserReceiver(tmp_path)
    write_web_position(tmp_path, key="old", pos=1.0, dur=2.0, phase="playing", wall=0.0)

    receiver.play("http://x/out.m3u8", title="Interstellar", at=42.0)

    box = read_web_box(tmp_path)
    assert box["url"] == "http://x/out.m3u8"
    assert box["title"] == "Interstellar"
    assert box["at"] == 42.0
    assert box["key"]
    assert read_web_position(tmp_path) is None


def test_stop_clears_both_the_mailbox_and_the_position(tmp_path: Path) -> None:
    receiver = BrowserReceiver(tmp_path)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=1.0, dur=2.0, phase="playing", wall=0.0)

    receiver.stop()

    assert read_web_box(tmp_path) == {}
    assert read_web_position(tmp_path) is None


def test_before_the_page_has_reported_anything_it_reads_as_buffering_and_alive(
    tmp_path: Path,
) -> None:
    """Пустой держатель показа не должен решить, что показ сорвался - страница ещё грузится."""
    receiver = BrowserReceiver(tmp_path)
    receiver.play("http://x/out.m3u8", title="t", at=12.0)

    assert receiver.position() == Position(12.0, 0.0, True, "BUFFERING")


def test_a_stale_key_from_a_past_session_reads_the_same_as_no_report_yet(tmp_path: Path) -> None:
    receiver = BrowserReceiver(tmp_path)
    receiver.play("http://x/out.m3u8", title="t", at=5.0)
    write_web_position(
        tmp_path, key="not-the-current-key", pos=90.0, dur=100.0, phase="playing", wall=0.0
    )

    assert receiver.position() == Position(5.0, 0.0, True, "BUFFERING")


def test_a_fresh_report_of_playing_is_read_through(tmp_path: Path) -> None:
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=30.0, dur=120.0, phase="playing", wall=clock.wall())

    assert receiver.position() == Position(30.0, 120.0, True, "PLAYING")


def test_a_paused_report_is_read_through(tmp_path: Path) -> None:
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=30.0, dur=120.0, phase="paused", wall=clock.wall())

    assert receiver.position() == Position(30.0, 120.0, False, "PAUSED")


def test_an_ended_report_is_read_as_idle_not_playing(tmp_path: Path) -> None:
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=119.0, dur=120.0, phase="ended", wall=clock.wall())

    assert receiver.position() == Position(119.0, 120.0, False, "IDLE")


def test_silence_short_of_lost_after_is_not_yet_declared_lost(tmp_path: Path) -> None:
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=30.0, dur=120.0, phase="playing", wall=clock.wall())

    clock.now += LOST_AFTER - 1.0

    assert receiver.position() == Position(30.0, 120.0, True, "PLAYING")


def test_silence_past_lost_after_but_short_of_gone_after_holds_the_session_alive(
    tmp_path: Path,
) -> None:
    """15 с молчания - «lost», но показ ещё жив: _hold не должен пытаться его поднять."""
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=30.0, dur=120.0, phase="playing", wall=clock.wall())

    clock.now += LOST_AFTER

    position = receiver.position()
    assert position == Position(30.0, 120.0, True, "lost", stale=True)
    assert position.playing is True


def test_silence_past_gone_after_closes_the_session_by_reporting_not_playing(
    tmp_path: Path,
) -> None:
    """60 с молчания - «gone»: держатель показа встречает playing=False и закрывает сеанс."""
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=30.0, dur=120.0, phase="playing", wall=clock.wall())

    clock.now += GONE_AFTER

    position = receiver.position()
    assert position == Position(30.0, 120.0, False, "lost", stale=True)
    assert position.playing is False


def test_a_fresh_left_report_still_waits_out_the_grace_period(tmp_path: Path) -> None:
    """Словом «ухожу» страница не закрывает показ сама - решает только срок (TC-1124)."""
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=30.0, dur=120.0, phase="left", wall=clock.wall())

    position = receiver.position()
    assert position == Position(30.0, 120.0, True, "BUFFERING")
    assert position.playing is True


def test_left_within_the_grace_period_still_waits(tmp_path: Path) -> None:
    """Обновление страницы (F5) шлёт то же слово - закрывать сеанс до срока нельзя."""
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=30.0, dur=120.0, phase="left", wall=clock.wall())

    clock.now += LEFT_AFTER - 1.0

    position = receiver.position()
    assert position == Position(30.0, 120.0, True, "BUFFERING")
    assert position.playing is True


def test_left_past_the_grace_period_closes_the_session_by_reporting_not_playing(
    tmp_path: Path,
) -> None:
    """Срок вышел, свежего отчёта не пришло - настоящий уход, показ закрывается (TC-1124)."""
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=30.0, dur=120.0, phase="left", wall=clock.wall())

    clock.now += LEFT_AFTER

    position = receiver.position()
    assert position == Position(30.0, 120.0, False, "lost", stale=True)
    assert position.playing is False


def test_left_past_the_grace_period_is_overridden_by_a_fresh_refresh_report(
    tmp_path: Path,
) -> None:
    """Свежий отчёт после ``left`` (F5 успела переприцепиться) отменяет уход."""
    clock = FakeClock()
    receiver = BrowserReceiver(tmp_path, clock=clock)
    receiver.play("http://x/out.m3u8", title="t", at=0.0)
    key = read_web_box(tmp_path)["key"]
    write_web_position(tmp_path, key=key, pos=30.0, dur=120.0, phase="left", wall=clock.wall())

    clock.now += 1.0
    write_web_position(tmp_path, key=key, pos=31.0, dur=120.0, phase="playing", wall=clock.wall())
    clock.now += LEFT_AFTER - 0.5

    assert receiver.position() == Position(31.0, 120.0, True, "PLAYING")
