"""Снимок показа формирует зрительское имя и признак продолжения."""

from torrcast.domain.playback_snapshot import PlaybackSnapshot


def test_snapshot_describes_episode() -> None:
    snapshot = PlaybackSnapshot("key", "Луна", position=10, label="s1e2")

    assert snapshot.shown_as == "«Луна» s1e2"
    assert snapshot.resumable
