"""Зеркало :mod:`hass.poster_lookup`: имена постера и манифест кадра."""

from hass.poster_lookup import _manifest, _poster_names
from torrcast.domain.playback_snapshot import PlaybackSnapshot


def test_all_recorded_names_reach_the_poster_without_duplicates() -> None:
    """Ошибка каталога не выбрасывает исходный запрос и оригинальное имя картины."""
    shown = PlaybackSnapshot(
        key="movie:еше-по-одной:2020",
        title="Еше по одной",
        year=2020,
        original="Druk",
        query="еще-по-одной",
    )

    assert _poster_names(shown) == ["Еше по одной", "Druk", "еще по одной"]


def test_the_hls_base_names_its_master_manifest() -> None:
    """Сеанс отдаёт базу, а ffmpeg открывает существующий мастер-манифест под ней."""
    assert _manifest("http://10.0.1.5:8080") == "http://10.0.1.5:8080/index.m3u8"
    assert _manifest("http://10.0.1.5:8080/index.m3u8") == ("http://10.0.1.5:8080/index.m3u8")
