"""Поддельный мир оживления показа: приёмник по сценарию, живая упаковка, ручные часы.

Общий инвентарь зеркал пакета: сна тут нет вовсе, а решения показа видно списками.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from tests.conftest import fake_packer
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.domain.position import Position
from torrcast.usecases.feed_pack.feed import Feed


@dataclass
class FakeReceiver:
    """Приёмник по сценарию: очередь состояний, как их отдаёт живой телевизор."""

    script: list[tuple[float, str]] = field(default_factory=list)
    #: Места, с которых у приёмника просили поднять показ (:meth:`replay`).
    replayed: list[float] = field(default_factory=list)
    #: Чем приёмник отвечает на подъём: место или отказ отрицательным числом.
    answer: float = 0.0

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        return None

    def position(self, front: float = 0.0) -> Position:
        pos, state = self.script.pop(0) if self.script else (0.0, "IDLE")
        return Position(pos, 7200.0, state in {"PLAYING", "BUFFERING"}, state)

    def replay(self, pos: float, paused: bool = False) -> float:
        self.replayed.append(pos)
        return self.answer


class Beat(NamedTuple):
    """Один круг опроса живого приёмника: что он ответил и можно ли ответу верить.

    ``stale`` - ответ взят не свежим: сокет лёг, и приёмник отдал эхо прошлого опроса
    (:attr:`torrcast.domain.position.Position.stale`). Врёт такое эхо ровно об одном - о
    воле зрителя: ``closed`` в нём всегда ``False``, потому что на экране числится ещё наше
    приложение из прошлого статуса. Замер на приставке 30-08-2026 именно так и выглядит
    (TC-880), поэтому круг опроса и в подделке умеет быть невнятным.
    """

    pos: float
    state: str
    closed: bool = False
    stale: bool = False


@dataclass
class RemoteClosedReceiver:
    """Приёмник, показ у которого убирает с экрана сам зритель.

    Признак пустого экрана
    (:func:`torrcast.adapters.chromecast.cast.viewer_closed._viewer_closed`) живой приёмник
    отдаёт одним ответом с местом и словом о ходе показа, поэтому и в сценарии он стоит
    рядом с ними: своя авария снаружи выглядит так же, а решение по ней обратное.
    """

    #: Круги опроса (:class:`Beat`); тройка без ``stale`` - внятный ответ.
    script: list[tuple[float, str, bool] | Beat] = field(default_factory=list)
    #: Чем гасили приложение приёмника: ``quit_app`` каждого :meth:`stop`.
    stopped: list[bool] = field(default_factory=list)
    dur: float = 7200.0
    #: Сколько кругов опроса показ потратил. Им и меряется цена выдержки на стыке серий:
    #: лишний круг на КАЖДОМ конце серии откладывал бы переход, а он дороже хвоста.
    polls: int = 0
    #: Места, с которых у приёмника просили поднять показ (:meth:`replay`).
    replayed: list[float] = field(default_factory=list)

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        self.stopped.append(quit_app)

    def replay(self, pos: float, paused: bool = False) -> float:
        # 🔴 Подъём подделке нужен не ради подъёма, а чтобы она вообще считалась приёмником:
        # лестница воскрешения первым делом спрашивает, умеет ли он поднимать
        # (:class:`torrcast.usecases.choice._ctl._Revivable`), и подделка без этого метода
        # уходила из лестницы раньше, чем та успевала разобрать конец картины. Живой
        # приёмник поднимать умеет, и зеркало обязано быть похоже именно здесь.
        self.replayed.append(pos)
        return pos

    def position(self, front: float = 0.0) -> Position:
        self.polls += 1
        beat = Beat(*self.script.pop(0)) if self.script else Beat(0.0, "IDLE")
        playing = beat.state in {"PLAYING", "BUFFERING"}
        return Position(beat.pos, self.dur, playing, beat.state, beat.closed, beat.stale)


@dataclass
class PlainReceiver:
    """Приёмник, который поднимать показ не умеет: у него нет :meth:`replay`."""

    script: list[tuple[float, str]] = field(default_factory=list)

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        return None

    def position(self, front: float = 0.0) -> Position:
        pos, state = self.script.pop(0) if self.script else (0.0, "IDLE")
        return Position(pos, 7200.0, state in {"PLAYING", "BUFFERING"}, state)


@dataclass
class FakeSupply:
    """Источник показа: отвечает ли служба и вернулась ли раздача с трекерами."""

    silence: str = ""
    restored: bool = False
    torrent_hash: str = "hash"
    magnet: str = "magnet:?xt=hash"
    lost: str = ""
    kept_up: bool = False
    thin: bool = False
    #: Сколько раз источник спрашивали: вопрос стоит запроса и задаётся не в горячем пути.
    asked: int = 0

    def check(self) -> str:
        self.asked += 1
        return self.silence


def feed_with_segments(tmp_path: Path, slots: int = 60, whole: float = 7200.0) -> Feed:
    """Упаковка на готовые сегменты ровной сетки; ffmpeg за ней настоящий не стоит.

    ``whole`` - длительность картины: по ней показ и решает, титры перед ним или авария
    (:func:`torrcast.domain.ending_reached.ending_reached`), поэтому конец серии зеркалу
    приходится называть честной длиной, а не общей.
    """
    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(slots):
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed = Feed(source="", audio=0, out=out, grid=Grid.uniform(whole), keep=40.0, wait=0.0)
    feed.packer = fake_packer(out, first=0)
    return feed
