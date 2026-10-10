"""Запись, чей рой отвечает и не отдаёт: показ уходит в отбор и говорит об этом строкой."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.world import entry
from tests.usecases.select.dead_swarm import Swarm
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.cast_command._cmd_play import _cmd_play
from torrcast.usecases.select._continue import _continue
from torrcast.usecases.start_progress import START


@pytest.fixture(autouse=True)
def _outside(monkeypatch: pytest.MonkeyPatch, _russian_product: None) -> None:
    """Профиль приёмника называется прямо, строки - русские."""
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))


class _Dropping(Swarm):
    """Рой одного вопроса, у которого раздачу можно и снять."""

    def __init__(self) -> None:
        super().__init__()
        self.dropped: list[str] = []

    def drop(self, torrent_hash: str) -> bool:
        self.dropped.append(torrent_hash)
        return True


def _mute(_url: str) -> Callable[[float], bool | None]:
    return lambda _timeout: False


def test_a_recording_whose_swarm_gives_no_byte_takes_the_trip_to_search(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 TC-1420. Вся цепочка двери ``cast``: настоящее продолжение и настоящий приговор.

    Рой отвечает контактом и файлами, а байта не отдаёт: раньше запись играла и шесть
    минут не давала кадра. Теперь продолжение не открывается вовсе, показ идёт штатным
    отбором, а человек получает одну строку - почему.
    """
    state = WatchState()
    state.put("кино", entry(query="кино"))
    watch_store().save(state)
    swarm = _Dropping()
    composition.use_engines(monkeypatch, swarm)
    composition.use_first_byte(monkeypatch, _mute)
    resumed: list[object] = []
    trips: list[object] = []

    def played(*args: object, **_rest: object) -> int:
        resumed.append(args)
        return EXIT_OK

    def resume(*args: object, **rest: object) -> int | None:
        return _continue(*args, resume=played, **rest)  # type: ignore[arg-type]

    def choose(*args: object, **_kw: object) -> int:
        trips.append(args)
        return EXIT_OK

    START.began()
    try:
        assert _cmd_play(Args(query=["кино"]), resume=resume, choose=choose) == EXIT_OK
        told = START.seen()
    finally:
        START.gone()

    assert resumed == [], "мёртвая запись не играет"
    assert len(trips) == 1, "показ ушёл в отбор ровно один раз"
    assert swarm.dropped == ["hash-кино"], "поднятая проверкой раздача снята из службы"
    lines = [line for line in capsys.readouterr().out.splitlines() if "не играется" in line]
    assert len(lines) == 1, lines
    assert "записанная раздача не играется: за " in lines[0]
    assert "не отдала ни байта; ищу другую" in lines[0]
    assert told is not None and told["buried"] == lines[0], "вкладка слышит ту же строку"
