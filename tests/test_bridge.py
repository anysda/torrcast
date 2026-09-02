"""Зеркало моста: три отказа договора и словесная причина несостоявшегося показа."""

from __future__ import annotations

import signal
from typing import TYPE_CHECKING, Any

import pytest

from hass.bridge import BUSY, NO_NEXT, NO_VOLUME, NOTHING_PLAYING, VOLUME, Bridge
from hass.refused_error import RefusedError
from hass.say import SEEKBY, TOGGLE
from hass.volume import Volume
from tests.fakes.playback_session import FakePlaybackSession
from tests.fakes.state_store import FakeStateStore
from torrcast.adapters.choice_environment import _SystemChoiceEnvironment
from torrcast.domain.config import Config
from torrcast.domain.debug_handles import CTL_ENV
from torrcast.domain.entry import Entry
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.ports.state_store import slot as state_slot

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path


class _Receiver:
    """Приёмник, отвечающий из памяти: настоящий тут звонил бы в сеть."""

    def __init__(self, level: float = 0.3, deaf: bool = False) -> None:
        self.status = type("_Status", (), {"volume_level": level})()
        self.deaf = deaf
        self.wanted: list[float] = []

    def set_volume(self, level: float) -> None:
        if self.deaf:
            raise OSError("приёмник молчит")
        self.wanted.append(level)

    def disconnect(self) -> None:
        return None


def _bridge(
    session: FakePlaybackSession,
    *,
    command: Callable[[Sequence[str] | None], int] = lambda _argv: 0,
    receiver: _Receiver | None = None,
) -> Bridge:
    """Мост на подделках: сеанс показа, приёмник и команда - все свои.

    Очередь команд не подделывается: тест сам зовёт :meth:`Bridge.run_one`, как её зовёт
    точка входа из главного потока. Пока не позвал - команда «поднимается».
    """
    device: Any = receiver or _Receiver()
    return Bridge(
        session=session,
        settings=lambda: Config(tv="10.0.1.7"),
        volume=Volume("10.0.1.7", connect=lambda _address: device),
        command=command,
    )


def test_the_remote_refuses_when_nothing_is_playing() -> None:
    bridge = _bridge(FakePlaybackSession(playing=False))

    with pytest.raises(RefusedError) as refusal:
        bridge.control(TOGGLE, 0.0)

    assert refusal.value.word == NOTHING_PLAYING


def test_a_second_show_while_the_first_is_still_starting_is_refused() -> None:
    bridge = _bridge(FakePlaybackSession())

    bridge.play("матрица")  # команда в очереди, но ещё не сделана: показ поднимается
    with pytest.raises(RefusedError) as refusal:
        bridge.play("муха")

    assert refusal.value.word == BUSY
    assert bridge.run_one()
    assert bridge.play("муха")  # кончился первый - второй берётся


def test_a_film_has_no_next_episode() -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["movie:муха"] = Entry(title="Муха", magnet="magnet:?xt=1", kind="movie")
    store.save(state)
    bridge = _bridge(FakePlaybackSession(playing=True, play_key="movie:муха"))

    with pytest.raises(RefusedError) as refusal:
        bridge.next()

    assert refusal.value.word == NO_NEXT


def test_the_last_episode_of_the_release_has_no_next_one_either() -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["tv:чернобыль"] = Entry(
        title="Чернобыль",
        magnet="magnet:?xt=1",
        kind="tv",
        season=1,
        episode=4,
        episodes=[[1, 3, 0, 0], [1, 4, 1, 0]],
        query="чернобыль",
    )
    store.save(state)
    bridge = _bridge(FakePlaybackSession(playing=True, play_key="tv:чернобыль"))

    with pytest.raises(RefusedError) as refusal:
        bridge.next()

    assert refusal.value.word == NO_NEXT


def test_the_next_episode_is_asked_for_by_the_query_a_human_would_type() -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["tv:чернобыль"] = Entry(
        title="Чернобыль",
        magnet="magnet:?xt=1",
        kind="tv",
        season=1,
        episode=3,
        episodes=[[1, 3, 0, 0], [1, 4, 1, 0]],
        query="чернобыль",
    )
    store.save(state)
    asked: list[list[str]] = []

    def command(argv: Sequence[str] | None) -> int:
        asked.append(list(argv or []))
        return 0

    bridge = _bridge(FakePlaybackSession(playing=True, play_key="tv:чернобыль"), command=command)

    bridge.next()
    bridge.run_one()

    assert asked == [["чернобыль s1e4"]]


def test_a_deaf_receiver_refuses_the_level_instead_of_pretending() -> None:
    session = FakePlaybackSession(
        playing=True,
        play_key="movie:муха",
        shown=PlaybackSnapshot(key="movie:муха", title="Муха", position=60.0),
    )
    bridge = _bridge(session, receiver=_Receiver(deaf=True))

    with pytest.raises(RefusedError) as refusal:
        bridge.control(VOLUME, 0.4)

    assert refusal.value.word == NO_VOLUME


def test_a_refused_show_leaves_a_spoken_reason_and_the_next_one_clears_it() -> None:
    spoken = ["ничего не нашлось по запросу «муха»"]

    def command(argv: Sequence[str] | None) -> int:
        del argv
        if spoken:
            print(spoken.pop())
            return 1
        return 0

    bridge = _bridge(FakePlaybackSession(), command=command)

    bridge.play("муха")
    bridge.run_one()
    assert bridge.state()["last_error"] == "ничего не нашлось по запросу «муха»"

    bridge.play("матрица")
    bridge.run_one()
    assert bridge.state()["last_error"] is None


def test_a_command_is_allowed_to_install_a_signal_handler_the_way_cast_does() -> None:
    # 🔴 Ровно та строка, на которой мост молча не играл: `cast` на время команды ставит
    # свой обработчик SIGTERM (:func:`torrcast.cli.answered.answered`), а из рабочего
    # потока это не делается вовсе. Отпусти команду в поток - и вместо показа тут ляжет
    # словами «signal only works in main thread».
    def command(argv: Sequence[str] | None) -> int:
        del argv
        previous = signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, previous)
        return 0

    bridge = _bridge(FakePlaybackSession(), command=command)

    bridge.play("матрица")
    bridge.run_one()

    assert bridge.state()["last_error"] is None


def test_the_command_loop_leaves_when_it_is_asked_to() -> None:
    # 🔴 Уход проверяется тем же вызовом, которым мост живёт: не «поток кончился», а
    # цикл сказал «больше не зовите». Иначе юнит не отпускал бы SIGTERM.
    bridge = _bridge(FakePlaybackSession())

    bridge.stop()

    assert bridge.run_one() is False


def test_the_remote_word_goes_into_the_file_the_show_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Читателя не подделываем: слово забирает та самая единица, которой его забирает
    # идущий показ.
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))
    session = FakePlaybackSession(
        playing=True,
        play_key="movie:муха",
        shown=PlaybackSnapshot(key="movie:муха", title="Муха", position=60.0),
    )
    bridge = _bridge(session)

    bridge.control(SEEKBY, 90.0)

    assert _SystemChoiceEnvironment().read_command() == "seekby 90"
