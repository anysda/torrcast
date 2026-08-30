"""Зеркало конца показа: причина перекода вслух, гашение хозяйства и поиск виноватого."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.journal import Tape
from tests.usecases.revive_playback.world import (
    FakeSupply,
    RemoteClosedReceiver,
    feed_with_segments,
)
from torrcast.adapters.recode.whole_encode import whole_encode
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.receiver import Receiver
from torrcast.ports.state_store.slot import store
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.playback._show_end import _blame_the_end, _close_show, _handover, _say_whole
from torrcast.usecases.playback.stream_server import StreamServer
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.watch import Watch


class _Quiet:
    """Приёмник и раздача, которые только записывают, что их погасили."""

    def __init__(self) -> None:
        self.stopped: list[bool] = []

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        self.stopped.append(quit_app)

    def position(self, front: float = 0.0) -> object:
        raise AssertionError("конец показа приёмник о месте не спрашивает")

    def start(self) -> None:
        return None


def test_the_reason_of_the_whole_recode_is_said_out_loud(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Зритель читает, ПОЧЕМУ фильм перекодируется, а не догадывается по чёткости."""
    whole = whole_encode(9.0, video_mbit=20.0, frame=2160, ceiling=1080)

    _say_whole(whole, "hevc", 10, 20.0, 2160, CAUTIOUS)

    printed = capsys.readouterr().out
    assert "перекодирую на ходу целиком" in printed
    assert "1080p" in printed, "ужатый кадр называется, а не подразумевается"


def test_everything_of_the_show_is_put_out_even_on_a_broken_receiver(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Приёмник роняет что угодно, а ffmpeg и раздача обязаны погаснуть в любом случае."""

    class _Falling(_Quiet):
        def stop(self, quit_app: bool = False) -> None:
            raise RuntimeError("сендер развалился")

    class _Server:
        def __init__(self) -> None:
            self.stops = 0

        def start(self) -> None:
            return None

        def stop(self) -> None:
            self.stops += 1

    feed = feed_with_segments(tmp_path)
    server: StreamServer = _Server()

    _close_show(None, None, _Falling(), feed, server)  # type: ignore[arg-type]

    assert isinstance(server, _Server) and server.stops == 1, "раздача обязана погаснуть"


def test_a_show_that_is_handed_over_keeps_the_app_open(tmp_path: Path) -> None:
    """Стык серий - приложение приёмника остаётся открытым: моргать экраном незачем."""
    entry = Entry(title="Кино", magnet="magnet:?xt=1")
    watch = Watch(key="кино", entry=entry)

    assert _handover(None) is False
    assert _handover(watch) is False, "показ не досмотрен - передавать нечего"


def _remember(key: str) -> None:
    """Сериал на предпоследней серии: следующая в раздаче есть, и стыку было бы куда идти."""
    state = store().load()
    state.put(
        key,
        Entry(
            title="Домохозяйки",
            magnet="magnet:?xt=1",
            kind="tv",
            dur=2600.0,
            season=1,
            episode=7,
            episodes=[[1, 7, 0], [1, 8, 1]],
        ),
    )
    store().save(state)


def _watched_to_the_end(key: str, out: Path, closed: bool) -> RemoteClosedReceiver:
    """Досмотреть серию настоящим кругом опроса; ``closed`` - убрал ли показ зритель.

    Признак приходит от приёмника и едет в сторож :func:`_closed`-ом, как в бою: рука
    теста, кладущая его прямо в :class:`Watch`, доказала бы только последнее звено.
    """
    entry = store().load().get(key)
    assert entry is not None
    watch = Watch(key=key, entry=entry)
    receiver = RemoteClosedReceiver(
        [(2569.0, "PLAYING", False), (0.0, "UNKNOWN", closed)], dur=2600.0
    )
    _hold(cast(Receiver, receiver), feed_with_segments(out), watch, clock=FakeClock(now=1000.0))
    _close_show(watch, None, cast(Receiver, receiver), feed_with_segments(out / "конец"), _Server())
    return receiver


class _Server:
    """Раздача показа, которой от конца нужно только погаснуть."""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


def test_a_show_closed_by_the_viewer_quits_the_app_though_the_next_episode_waits(
    tmp_path: Path, tape: Tape
) -> None:
    """Показ убрали пультом - приложение приёмника гаснет, хоть закладка и сдвинута.

    🔴 Стыка серий тут не будет: следующую серию цикл юнита в этот же процесс не грузит
    (TC-880), а оставленное открытым приложение держит на экране иконку Default Media
    Receiver до её собственного таймаута простоя и оттягивает автовыключение телевизора.

    Мерится разница, а не флаг: обе половины проходят один и тот же круг опроса и один и
    тот же конец показа, и различает их ровно пустой экран приёмника.
    """
    _remember("tv:домохозяйки-пультом:2020")
    _remember("tv:домохозяйки-сама:2020")

    by_remote = _watched_to_the_end("tv:домохозяйки-пультом:2020", tmp_path / "пульт", closed=True)
    by_itself = _watched_to_the_end("tv:домохозяйки-сама:2020", tmp_path / "сама", closed=False)

    assert by_remote.stopped == [True], "воля зрителя - приложение приёмника закрываем"
    assert by_itself.stopped == [False], "тот же конец без пульта - это стык серий"


def test_a_dead_source_takes_the_blame_of_the_broken_show() -> None:
    """Показ оборвался при мёртвом источнике - виноват он, и это сказано человеку."""
    with pytest.raises(InfraError, match="источник не читается"):
        _blame_the_end(cast_supply(FakeSupply(silence="TorrServer не отвечает")), clock=_NoWait())


def test_a_live_source_leaves_the_receiver_to_blame() -> None:
    """Источник здоров - остаётся приёмник, и обвинение достаётся ему."""
    with pytest.raises(InfraError, match="приёмник не досмотрел поток"):
        _blame_the_end(cast_supply(FakeSupply()), clock=_NoWait())


def test_a_show_without_a_single_frame_names_itself_apart() -> None:
    """«Не увидел ни кадра» и «не досмотрел» - две разные аварии для того, кто у экрана."""
    with pytest.raises(InfraError, match="картинки не было ни разу"):
        _blame_the_end(cast_supply(FakeSupply()), shown=False, clock=_NoWait())


class _NoWait:
    """Часы, которые не ждут: расспрос источника меряется решением, а не секундами."""

    def monotonic(self) -> float:
        return 0.0

    def wall(self) -> float:
        return 0.0

    def sleep(self, seconds: float) -> None:
        return None


def cast_supply(supply: FakeSupply) -> StreamSource:
    """Подделка источника честно занимает место настоящего договора."""
    return cast(StreamSource, supply)
