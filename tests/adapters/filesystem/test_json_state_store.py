"""Проверяет атомарное хранение позиции без потери старых полей."""

from torrcast.adapters.filesystem.json_state_store import JsonStateStore
from torrcast.domain.playback_state import PlaybackState


def test_preserves_legacy_entry_fields(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    store = JsonStateStore({"TORRCAST_STATE": "/fake/state.json"})
    data = {"movie:x:2020": {"title": "X", "pos": 4}}
    monkeypatch.setattr(store, "_read", lambda: data)
    monkeypatch.setattr(store, "_write", lambda payload: data.update(payload))

    store.save(PlaybackState("movie:x:2020", 12.5))

    assert store.load("movie:x:2020") == PlaybackState("movie:x:2020", 12.5)
    assert data["movie:x:2020"]["title"] == "X"
