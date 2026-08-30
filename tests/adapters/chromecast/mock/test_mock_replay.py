"""Подъём погасшего показа: картинка называется только та, что действительно вернулась."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from tests.fakes.clock import FakeClock
from torrcast.adapters.chromecast.mock.hls_decoder import HlsDecoder
from torrcast.adapters.chromecast.mock.mock_replay import mock_replay
from torrcast.adapters.chromecast.mock.screen_watch import ScreenWatch
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_raised import NOT_RAISED
from torrcast.domain.position import Position
from torrcast.ports.clock import Clock


class _Screen:
    """Экран на бумаге: помнит прыжок и то, считается ли показ погасшим."""

    def __init__(self) -> None:
        self.dead = True
        self.jumps: list[float] = []

    def jumped(self, at: float) -> None:
        self.jumps.append(at)


class _Decoder:
    """Декодер на бумаге: место на экране задаётся снаружи, останов запоминается."""

    def __init__(self, pos: Position) -> None:
        self.pos = pos
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _Moving(FakeClock):
    """Часы, за которыми едет декодер: каждая секунда ожидания двигает картинку."""

    decoder: _Decoder | None = None

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        if self.decoder is not None:
            self.decoder.pos = Position(self.decoder.pos.pos + seconds, 7200.0, True)


def _replay(
    clock: FakeClock,
    decoder: _Decoder,
    screen: _Screen,
    at: float = 600.0,
    open_at: Callable[[float], None] = lambda pos: None,
) -> tuple[float, str]:
    """Место подъёма и причина, по которой его нет."""
    return mock_replay(
        open_at,
        cast(ScreenWatch, screen),
        cast(HlsDecoder, decoder),
        cast(Clock, clock),
        at,
        60.0,
    )


def test_a_replay_names_only_a_picture_that_really_came_back() -> None:
    """Место подъёма называется про вернувшуюся картинку, а не про отправленный LOAD."""
    clock = _Moving(1000.0)
    decoder = _Decoder(Position(600.0, 7200.0, True))
    clock.decoder = decoder  # декодер поехал - вот теперь на экране картинка
    screen = _Screen()

    assert _replay(clock, decoder, screen) == (600.0, "")
    assert not screen.dead, "показ поднят - сессия снова живая"
    assert screen.jumps == [600.0], "терпение считается от нового места"
    assert clock.sleeps == [1.0], "картинка нашлась с первого опроса - дальше не ждём"


def test_a_decoder_that_never_started_is_not_called_a_show() -> None:
    """Декодер лёг, не начав: показа нет, и врать о нём нельзя."""
    clock = FakeClock(1000.0)
    decoder = _Decoder(Position(600.0, 7200.0, False))

    place, refused = _replay(clock, decoder, _Screen())

    assert place == NOT_RAISED
    assert decoder.stopped, "мёртвый декодер за собой не оставляем"
    assert refused.startswith("не взял:"), "снаружи это отказ приёмника, а не наше падение"


def test_a_source_that_is_still_gone_is_not_a_replay_either() -> None:
    """Источника всё ещё нет - зовущий попробует ещё или погасит показ сам."""
    clock = FakeClock(1000.0)
    decoder = _Decoder(Position(600.0, 7200.0, True))
    screen = _Screen()

    place, refused = _replay(clock, decoder, screen, open_at=_gone)

    assert place == NOT_RAISED
    assert screen.jumps == [] and clock.sleeps == [], "ждать нечего: LOAD не взяли"
    assert refused == "упал: источника нет", "исключение проглочено, причина его - нет"


def test_the_ways_of_not_raising_the_show_are_named_apart_and_not_by_one_string() -> None:
    """🔴 Разные исходы обязаны дать РАЗНЫЕ записи, а не одну строку на всех.

    Ответ про место у всех неудач один - :data:`NOT_RAISED`, - поэтому различие живёт
    только в названной причине. Пока её не было, замер подъёмов по сухой ленте читался
    двусмысленно: ноль подъёмов значил и «продукт передумал поднимать», и «процесс упал
    раньше, чем успел» (TC-880).
    """
    said = [_named(True), _named(False), _named(True, _gone)]

    assert len(set(said)) == 3, f"три исхода обязаны называться по-разному: {said}"


def _named(playing: bool, open_at: Callable[[float], None] = lambda pos: None) -> str:
    """Как подъём назвал причину: декодер стоит, декодер лёг, источника нет."""
    place, refused = _replay(
        FakeClock(1000.0), _Decoder(Position(600.0, 7200.0, playing)), _Screen(), 600.0, open_at
    )
    assert place == NOT_RAISED
    return refused


def _gone(pos: float) -> None:
    """Источник, которого нет: заход к нему кончается аварией, а не картинкой."""
    raise InfraError("источника нет")
