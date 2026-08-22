"""Зеркально проверяет чтение паспорта следующей серии."""

import pytest

from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.domain.worker_settings import WORKER_DUR
from torrcast.usecases import episode_duration
from torrcast.usecases.episode_duration import _duration


def test_a_full_passport_is_not_asked_for_twice() -> None:
    entry = Entry(title="Кино", magnet="magnet:?x=1", dur=100.0, depth=8, frame=1080)

    assert _duration("ключ", entry, "http://127.0.0.1:1/x") is entry


def test_the_probe_budget_stays_where_it_was() -> None:
    assert WORKER_DUR == 90.0


def test_missing_weight_is_estimated_for_the_current_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Следующая серия тоже получает цели до первого куска."""
    monkeypatch.setattr(
        episode_duration,
        "_episode_prober",
        lambda source, timeout: Media(duration=4000.0, video="h264", height=1080, width=1920),
    )
    monkeypatch.setattr(episode_duration, "store", lambda: _MemoryStore())
    entry = Entry(
        title="Сериал",
        magnet="magnet:?x=1",
        kind="tv",
        file_idx=2,
        episodes=[[1, 1, 1, 10_000_000_000], [1, 2, 2, 20_000_000_000]],
    )

    _duration("ключ", entry, "http://127.0.0.1:1/x")

    assert entry.vbps == 40.0, "оценка берёт размер текущей, а не первой серии"
    assert entry.vbps_estimated


def test_a_measured_weight_and_an_old_three_column_row_keep_their_meaning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Замер помечен замером, а старой строке размер по-прежнему не приписывается."""
    monkeypatch.setattr(
        episode_duration,
        "_episode_prober",
        lambda source, timeout: Media(duration=4000.0, video_bps=12_000_000.0),
    )
    monkeypatch.setattr(episode_duration, "store", lambda: _MemoryStore())
    measured = Entry(title="Сериал", magnet="m", file_idx=2, episodes=[[1, 2, 2]])

    _duration("замер", measured, "http://127.0.0.1:1/x")
    monkeypatch.setattr(
        episode_duration,
        "_episode_prober",
        lambda source, timeout: Media(duration=4000.0),
    )
    old = Entry(title="Сериал", magnet="m", file_idx=2, episodes=[[1, 2, 2]])
    _duration("старая", old, "http://127.0.0.1:1/x")

    assert (measured.vbps, measured.vbps_estimated) == (12.0, False)
    assert (old.vbps, old.vbps_estimated) == (-1.0, False)


class _MemoryState:
    def put(self, key: str, entry: Entry) -> None:
        pass


class _MemoryStore:
    def load(self) -> _MemoryState:
        return _MemoryState()

    def save(self, state: _MemoryState) -> None:
        pass
