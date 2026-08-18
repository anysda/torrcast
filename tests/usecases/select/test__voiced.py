"""Зеркало ``--voice``: у поднятой раздачи есть хозяин, и бесхозной она не остаётся."""

from __future__ import annotations

from tests.usecases.select.world import entry
from torrcast.cli.args import Args
from torrcast.domain.config import Config
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.select._voiced import _Voiced, _voiced


class _Dropped:
    """Кто и что снёс: подделке отбора хватает списка хэшей."""

    def __init__(self, fails: bool = False) -> None:
        self.calls: list[list[str]] = []
        self._fails = fails

    def __call__(self, config: Config, hashes: list[str]) -> None:
        self.calls.append(list(hashes))
        if self._fails:
            raise TorrcastError("служба раздач не отвечает")


def test_without_the_flag_nothing_is_read_at_all() -> None:
    """Флага нет - этот путь тем и хорош, что обходится состоянием без похода в рой."""
    saved = entry(voice="Дубляж")

    assert _voiced(Config(), saved, Args(query=["кино"])) is saved


def test_a_torrent_handed_to_the_show_is_not_taken_away() -> None:
    """Юнит играет тот же магнит - раздача его, и убирать её тут нельзя."""
    own = _Voiced(torrent_hash="a" * 40, handed=True)
    dropped = _Dropped()

    own.drop(Config(), dropped)

    assert dropped.calls == []


def test_a_torrent_nobody_took_is_removed_by_its_own_hash() -> None:
    """Сухой прогон, Ctrl-C, «серии тут нет» - во всех исходах раздача убирается."""
    own = _Voiced(torrent_hash="b" * 40)
    dropped = _Dropped()

    own.drop(Config(), dropped)

    assert dropped.calls == [["b" * 40]]


def test_dropping_twice_is_harmless() -> None:
    """Повторный вызов и пустой хэш безвредны: чужого он не касается."""
    own = _Voiced(torrent_hash="c" * 40)
    dropped = _Dropped()

    own.drop(Config(), dropped)
    own.drop(Config(), dropped)

    assert dropped.calls == [["c" * 40]]
    assert own.torrent_hash == ""


def test_a_service_that_refuses_does_not_break_the_way_out() -> None:
    """Служба не отвечает - это не повод уронить выход из команды."""
    own = _Voiced(torrent_hash="d" * 40)

    own.drop(Config(), _Dropped(fails=True))

    assert own.torrent_hash == ""
