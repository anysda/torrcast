"""Снимок показа формирует зрительское имя и признак продолжения."""

from torrcast.domain.playback_snapshot import PlaybackSnapshot


def test_snapshot_describes_episode() -> None:
    snapshot = PlaybackSnapshot("key", "Луна", position=10, label="s1e2")

    assert snapshot.shown_as == "«Луна» s1e2"
    assert snapshot.resumable


def test_the_snapshot_speaks_the_original_name_under_english(_english: None) -> None:
    """Под EN снимок зовёт картину тем же именем, что строка запуска."""
    snapshot = PlaybackSnapshot("key", "Луна", label="s1e2", original="Moon")

    assert snapshot.spoken == "Moon"
    assert snapshot.shown_as == "«Moon» s1e2"


def test_the_snapshot_speaks_the_recorded_name_under_russian(_russian_product: None) -> None:
    snapshot = PlaybackSnapshot("key", "Луна", original="Moon")

    assert snapshot.spoken == "Луна"
