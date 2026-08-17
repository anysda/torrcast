"""Зеркало :mod:`torrcast.adapters.chromecast.mock.mock_receiver`."""

from __future__ import annotations

from typing import Any

from tests.conftest import FakeProc
from tests.fakes.clock import FakeClock
from torrcast.adapters.chromecast.mock.hls_fetch import CORS_HEADER
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.domain.not_raised import NOT_RAISED
from torrcast.domain.position import Position
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.ports.receiver import Receiver

URL = "http://127.0.0.1:9/hls/index.m3u8"


class _Paper:
    """Раздача на бумаге: отдаёт пустой манифест и помнит, о чём её спросили."""

    status_code = 200
    text = ""

    def __init__(self) -> None:
        self.headers = {CORS_HEADER: "*"}
        self.asked: list[str] = []

    def get(self, url: str, timeout: float = 0.0) -> _Paper:
        self.asked.append(url)
        return self

    def raise_for_status(self) -> None:
        return None


class _Silent:
    """Поток, которого нет: фоновых читателей тут не заводится."""

    def start(self) -> None:
        pass

    def join(self, timeout: float | None = None) -> None:
        pass


def _receiver(clock: FakeClock | None = None, **kwargs: Any) -> tuple[MockReceiver, _Paper]:
    mock = MockReceiver(
        clock=clock or FakeClock(1000.0),
        spawn=lambda *args, **rest: FakeProc(),
        thread=lambda **rest: _Silent(),
        **kwargs,
    )
    paper = _Paper()
    mock.fetch.session = lambda ca: paper
    return mock, paper


def test_the_mock_is_a_receiver_the_show_can_drive() -> None:
    """Договор приёмника выполняется целиком - иначе показу его не отдать."""
    mock, _ = _receiver()

    assert isinstance(mock, Receiver)


def test_the_show_starts_where_it_was_sent_and_not_at_the_head_of_the_film() -> None:
    """До первого слова декодера приёмник стоит ТАМ, куда его послали.

    С нулём продолжение с 0:20:00 читалось бы как 0:00:00, и закладку сухим прогоном
    проверить было бы нельзя вовсе.
    """
    mock, paper = _receiver()

    mock.play(URL, at=1200.0)
    mock.report.duration = 7200.0

    assert paper.asked == [URL], "манифест приёмник спрашивает сам: TLS, доступность, CORS"
    assert mock.position(front=1260.0).pos == 1200.0
    assert mock.position(front=1260.0).pos == 1200.0, "и на следующем опросе тоже"


def test_the_patience_and_the_sulk_come_from_the_profile() -> None:
    """Повадки приёмника - числа его профиля, а не константы в коде."""
    stick, _ = _receiver(profile=ANDROID_TV)
    cautious, _ = _receiver()

    assert stick.patience == ANDROID_TV.patience
    assert stick.fetch.sulk == ANDROID_TV.sulk
    assert cautious.patience == CAUTIOUS.patience == MockReceiver.PATIENCE
    assert CAUTIOUS.segment_retries == MockReceiver.SEGMENT_RETRIES


def test_a_patience_named_by_the_caller_beats_the_profile() -> None:
    """Терпение задаётся и в конструкторе: тест не обязан выжидать замеренные секунды."""
    mock, _ = _receiver(patience=6.0)

    assert mock.patience == 6.0


def test_the_pause_stops_the_decoder_and_the_resume_reopens_where_it_stood() -> None:
    """Пауза снимает декодер, снятая пауза продолжает показ ровно с того места."""
    mock, paper = _receiver()
    mock.play(URL, at=600.0)
    mock.decoder.pos = Position(600.0, 7200.0, True)

    mock.pause()

    assert mock.position().state == "PAUSED", "показ жив и стоит на месте, а не погас"

    mock.resume()

    assert mock.position().state != "PAUSED"
    assert paper.asked == [URL, URL], "снятая пауза - это новый заход к тому же источнику"
    assert mock.decoder.start == 600.0


def test_the_seek_takes_the_decoder_to_the_named_second() -> None:
    """Перемотка доезжает до приёмника тем же местом, что и на ТВ."""
    mock, _ = _receiver()
    mock.play(URL, at=600.0)

    mock.seek(1200.5)

    assert mock.decoder.start == 1200.5
    assert mock.screen.seen == 1200.5, "терпение считается от нового места, а не от старого"


def test_a_replay_is_refused_while_the_404_is_still_remembered() -> None:
    """Приёмник, поймавший 404, ближайшее время не берёт LOAD вовсе."""
    clock = FakeClock(1000.0)
    mock, paper = _receiver(clock, profile=ANDROID_TV)
    mock.play(URL, at=600.0)
    mock.fetch.sulk_until = clock.monotonic() + 150.0

    assert mock.replay(600.0) == NOT_RAISED
    assert paper.asked == [URL], "второго захода не было - наказание держит"


class _Moving(FakeClock):
    """Часы, за которыми едет декодер: каждая секунда ожидания двигает картинку."""

    decoder: Any = None

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        if self.decoder is not None:
            self.decoder.pos = Position(self.decoder.pos.pos + seconds, 7200.0, True)


def test_a_replay_names_only_a_picture_that_really_came_back() -> None:
    """Место подъёма называется про вернувшуюся картинку, а не про отправленный LOAD."""
    clock = _Moving(1000.0)
    mock, _ = _receiver(clock)
    mock.play(URL, at=600.0)
    mock.screen.dead = True
    clock.decoder = mock.decoder  # декодер поехал - вот теперь на экране картинка

    assert mock.replay(600.0) == 600.0
    assert not mock.screen.dead, "показ поднят - сессия снова живая"
    assert clock.sleeps == [1.0], "картинка нашлась с первого опроса - дальше не ждём"


def test_a_decoder_that_never_started_is_not_called_a_show() -> None:
    """Декодер лёг, не начав: показа нет, и врать о нём нельзя."""
    clock = FakeClock(1000.0)
    mock, _ = _receiver(clock)
    mock.play(URL, at=600.0)
    mock.decoder.pos = Position(600.0, 7200.0, False)

    assert mock.replay(600.0) == NOT_RAISED
