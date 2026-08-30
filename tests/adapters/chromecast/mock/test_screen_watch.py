"""Зеркало :mod:`torrcast.adapters.chromecast.mock.screen_watch`."""

from __future__ import annotations

from tests.conftest import FakeProc
from tests.fakes.clock import FakeClock
from torrcast.adapters.chromecast.mock.hls_decoder import HlsDecoder
from torrcast.adapters.chromecast.mock.screen_watch import ScreenWatch
from torrcast.domain.patience import Patience
from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.reception_report import ReceptionReport
from torrcast.domain.watch_ratios import ENDING_RATIO

WHOLE = 7200.0


class _Screen:
    """Экран с декодером на бумаге: позиция ставится рукой, повторы записываются."""

    def __init__(self, patience: float = 30.0, retries: int = 2) -> None:
        self.clock = FakeClock(1000.0)
        self.report = ReceptionReport(duration=WHOLE)
        self.decoder = HlsDecoder(self.report)
        self.reopened: list[float] = []
        self.watch = ScreenWatch(
            self.decoder,
            self.report,
            CAUTIOUS,
            Patience(patience, retries),
            self.clock,
            self.reopened.append,
        )

    def at(self, pos: float, playing: bool = True) -> None:
        self.decoder.pos = Position(pos, WHOLE, playing)

    def exited(self, pos: float) -> None:
        """Декодер закрыл вход нулём на секунде ``pos``."""
        self.decoder.proc = FakeProc(0)  # type: ignore[assignment]
        self.at(pos, playing=False)


def test_a_moving_picture_with_the_buffer_gathered_is_playing() -> None:
    """Указатель поехал и запас набран - на экране картинка."""
    screen = _Screen()
    screen.at(300.0)

    seen = screen.watch.read(front=400.0)

    assert (seen.state, seen.pos, seen.playing) == ("PLAYING", 300.0, True)
    assert screen.watch.shown, "первый кадр этого показа уже был"


def test_a_standing_picture_is_waited_out_and_then_the_show_is_dropped() -> None:
    """Пока терпение идёт - ``BUFFERING`` и показ жив; кончилось - ``IDLE`` и позиции нет."""
    screen = _Screen(patience=30.0, retries=0)
    screen.at(300.0)
    screen.watch.read(front=400.0)  # картинка была, дальше она стоит

    assert screen.watch.read(front=400.0).state == "BUFFERING"
    screen.clock.now += 29.9
    assert screen.watch.read(front=400.0).state == "BUFFERING"
    screen.clock.now += 0.1

    seen = screen.watch.read(front=400.0)

    assert (seen.state, seen.pos, seen.playing) == ("IDLE", 0.0, False)
    assert screen.watch.dead, "сессии больше нет - поднимать показ теперь только заново"


def test_the_receiver_retakes_the_piece_itself_before_it_gives_up() -> None:
    """Внутри терпения приёмник перезабирает кусок сам, не гася показ.

    Что каждый такой перезабор уходит в ленту, держит отдельный сторож
    (``test_refetch_is_on_the_tape``): тут меряется расписание попыток, а не рассказ о них.
    """
    screen = _Screen(patience=30.0, retries=2)
    screen.at(300.0)
    screen.watch.read(front=400.0)
    screen.watch.read(front=400.0)  # картинка встала: отсюда и пошло терпение

    screen.clock.now += 10.0
    screen.watch.read(front=400.0)
    assert screen.reopened == [300.0], "первый перезабор - на первой трети терпения"

    screen.clock.now += 10.0
    screen.watch.read(front=400.0)
    assert screen.reopened == [300.0, 300.0]

    screen.clock.now += 5.0
    screen.watch.read(front=400.0)
    assert screen.reopened == [300.0, 300.0], "перезаборы кончились - дальше только терпеть"


def test_a_moving_picture_gives_the_patience_back() -> None:
    """Картинка пошла - счётчики стоящей обнуляются: терпение тратится не зря."""
    screen = _Screen()
    screen.at(300.0)
    screen.watch.read(front=400.0)
    screen.clock.now += 10.0
    screen.watch.read(front=400.0)

    screen.at(310.0)
    screen.watch.read(front=400.0)

    assert (screen.watch.still, screen.watch.loads) == (0.0, 0)


def test_a_pause_from_the_remote_spends_no_patience_at_all() -> None:
    """Пауза - не пропавший источник: показ жив, место прежнее, терпение целое."""
    screen = _Screen(patience=1.0)
    screen.at(600.0)
    screen.watch.paused = True

    screen.clock.now += 600.0
    seen = screen.watch.read()

    assert (seen.state, seen.pos, seen.playing) == ("PAUSED", 600.0, True)
    assert not screen.watch.dead


def test_the_credits_are_told_from_a_source_that_died_under_the_show() -> None:
    """Ноль декодера за порогом досмотра - титры; тот же ноль на пятой минуте - авария."""
    ended = _Screen()
    ended.exited(WHOLE * ENDING_RATIO)

    assert ended.watch.over() and ended.watch.read().state == ""

    died = _Screen()
    died.exited(282.0)

    assert not died.watch.over()
    assert died.watch.read().state == "BUFFERING", "смерть источника уходит в терпение"


def test_a_new_show_starts_with_a_clean_screen() -> None:
    """Новый показ забывает всё: и кадр, и паузу, и брошенную сессию."""
    screen = _Screen()
    screen.watch.dead, screen.watch.paused, screen.watch.shown = True, True, True
    screen.watch.loads, screen.watch.still, screen.watch.seen = 2, 5.0, 300.0

    screen.watch.reset()

    assert not (screen.watch.dead or screen.watch.paused or screen.watch.shown)
    assert (screen.watch.loads, screen.watch.still, screen.watch.seen) == (0, 0.0, -1.0)
