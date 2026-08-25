"""Зеркально проверяет цикл серий внутри юнита показа."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes.journal import Tape
from tests.fakes.stream_source import FakeStreamSource
from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.worker_settings import WORKER_META
from torrcast.ports.journal import slot as journal_slot
from torrcast.ports.state_store import slot as state_slot
from torrcast.ports.state_store.ephemeral import Ephemeral
from torrcast.usecases import worker_loop
from torrcast.usecases.following import _following
from torrcast.usecases.worker_loop import _worker_loop


def test_metadata_budget_of_the_unit_stays_where_it_was() -> None:
    assert WORKER_META == 60.0


def test_the_loop_and_its_next_episode_lookup_are_callable() -> None:
    assert callable(_worker_loop) and callable(_following)


class _EmitTape(Tape):
    """Лента, помнящая и свободные события: снимок порогов уезжает именно ими."""

    def emit(self, phase: str, event: str, **fields: object) -> None:
        self.calls.append((f"{phase}/{event}", dict(fields)))


def test_the_loop_pins_the_thresholds_snapshot_to_the_session_start_record(
    monkeypatch: pytest.MonkeyPatch, _ports_restored: None
) -> None:
    """Снимок порогов уезжает в ленту полями записи о начале сеанса, а не «где-то
    рядом»: иначе недельный разбор читал бы начало показа без чисел, которыми играли."""
    key = "movie:dune:2021"
    state = Ephemeral()
    fresh = state.load()
    fresh.put(
        key,
        Entry(title="Дюна", magnet="magnet:?xt=urn:btih:x", dur=3600.0, depth=8, frame=1080),
    )
    state.save(fresh)
    state_slot.install(state)
    tape = _EmitTape()
    journal_slot.install(tape)
    asked: list[tuple[Config, Profile]] = []

    def snapshot(config: Config, profile: Profile) -> dict[str, object]:
        asked.append((config, profile))
        return {
            "profile_source": "паспорт приёмника",
            "thresholds": {"burst": 60.0},
            "threshold_sources": {"burst": "профиль q70d"},
        }

    monkeypatch.setattr(worker_loop, "_worker_thresholds", snapshot)
    config = Config()

    code = worker_loop._worker_loop(
        config,
        key,
        FakeTorrentEngine(),
        None,  # type: ignore[arg-type]  # приёмник зовёт только показ, а он здесь подделка
        FakeStreamSource(),
        [],
        CAUTIOUS,
        play=lambda *args, **kwargs: 0,
    )

    assert code == 0
    assert asked == [(config, CAUTIOUS)], "снимок снят с настроек и профиля серии"
    start: list[dict[str, Any]] = tape.named("session/session_start")
    assert len(start) == 1, "запись о начале сеанса одна на серию"
    assert start[0]["profile"] == "q70d"
    assert start[0]["profile_source"] == "паспорт приёмника"
    assert start[0]["thresholds"] == {"burst": 60.0}
    assert start[0]["threshold_sources"] == {"burst": "профиль q70d"}


def _shown_title(entry: Entry, _ports: None = None) -> str:
    """Подпись, с которой цикл зовёт показ: ровно она уезжает на экран."""
    key = "tv:harley-quinn:2019"
    state = Ephemeral()
    fresh = state.load()
    fresh.put(key, entry)
    state.save(fresh)
    state_slot.install(state)
    journal_slot.install(_EmitTape())
    seen: list[str] = []

    def play(config: Config, source: str, audio: int, about: str, *args: Any, **kw: Any) -> int:
        seen.append(about)
        return 0

    worker_loop._worker_loop(
        Config(),
        key,
        FakeTorrentEngine(),
        None,  # type: ignore[arg-type]  # приёмник зовёт только показ, а он здесь подделка
        FakeStreamSource(),
        [],
        CAUTIOUS,
        play=play,
    )
    return seen[0]


def _harley(**fields: Any) -> Entry:
    return Entry(
        title="Харли Квинн",
        magnet="magnet:?xt=urn:btih:x",
        kind="tv",
        dur=1500.0,
        depth=8,
        frame=1080,
        season=5,
        episode=1,
        episodes=[[5, 1, 0], [5, 2, 1]],
        **fields,
    )


def test_a_forced_voice_swap_reaches_the_screen_and_not_the_terminal(
    _ports_restored: None,
) -> None:
    """Зритель смотрит в телевизор: подпись показа - единственное, что туда уезжает."""
    shown = _shown_title(_harley(studio="The Kitchen Russia", heard="TVShows"))

    assert shown == "Харли Квинн s5e1 · озвучка TVShows вместо The Kitchen Russia"


def test_a_show_without_a_swap_carries_no_extra_word(_ports_restored: None) -> None:
    """Подмены нет - и приписывать подписи нечего: молчаливых подмен не бывает, лишних тоже."""
    assert _shown_title(_harley(studio="The Kitchen Russia")) == "Харли Квинн s5e1"
