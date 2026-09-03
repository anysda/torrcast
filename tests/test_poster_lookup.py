"""Зеркало :mod:`hass.poster_lookup`: просьбы о постере и манифест кадра."""

from hass.poster_lookup import _manifest, _poster_asks
from torrcast.domain.facts.ask import Ask
from torrcast.domain.playback_snapshot import PlaybackSnapshot


def test_the_recorded_names_reach_the_poster_without_duplicates() -> None:
    """Ошибка каталога не выбрасывает исходный запрос, а оригинал едет полем просьбы."""
    shown = PlaybackSnapshot(
        key="movie:еше-по-одной:2020",
        title="Еше по одной",
        year=2020,
        original="Druk",
        query="еще-по-одной",
    )

    assert _poster_asks(shown) == [
        Ask("Еше по одной", 2020, "movie", "Druk"),
        Ask("еще по одной", 2020, "movie", ""),
    ]


def test_the_series_asks_for_a_series() -> None:
    """Подпись серии есть - род просьбы «tv»: у «Сталкера» это разные статьи."""
    shown = PlaybackSnapshot(
        key="tv:сталкер:2018", title="Сталкер", year=2018, label="S01E01", query="сталкер"
    )

    assert _poster_asks(shown)[0] == Ask("Сталкер", 2018, "tv", "")


def test_the_hls_base_names_its_master_manifest() -> None:
    """Сеанс отдаёт базу, а ffmpeg открывает существующий мастер-манифест под ней."""
    assert _manifest("http://10.0.1.5:8080") == "http://10.0.1.5:8080/index.m3u8"
    assert _manifest("http://10.0.1.5:8080/index.m3u8") == ("http://10.0.1.5:8080/index.m3u8")
