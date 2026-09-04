"""Зеркало :mod:`hass.poster_lookup`: просьбы о постере, манифест кадра и места картинок."""

from hass.poster_lookup import (
    _frame_key,
    _manifest,
    _playing_key,
    _poster_asks,
    _poster_identity,
)
from hass.poster_name import poster_name
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


def test_the_frame_of_a_show_lies_beside_its_poster_and_not_in_its_place() -> None:
    """🔴 Разные места - это то, что даёт постеру сменить кадр, не стерев его байты.

    Отпечаток кадра уже уехал наружу предыдущим снимком, и Home Assistant спрашивает
    картинку следующим запросом. Ляг постер в то же место - на этот запрос ответили бы
    «нет такой картинки», и карточка мигнула бы пустотой посреди замены.
    """
    shown = PlaybackSnapshot(key="tv:уэнздей:2022", title="Уэнздей", year=2022, label="s1e1")
    key = _playing_key(shown)

    assert _frame_key(key) != key
    assert _frame_key(key).startswith(key), "кадр опознаётся тем же показом"


def test_a_series_keeps_one_shelf_name_and_a_key_of_its_own_for_every_episode() -> None:
    """Постер у сериала один на все серии, а кадр - свой у каждой.

    Поэтому подпись серии входит в место картинки, но не входит в имя на полке: приди
    она и туда - Википедию спрашивали бы заново на каждой серии.
    """
    first = PlaybackSnapshot(key="k", title="Уэнздей", year=2022, label="s1e1")
    second = PlaybackSnapshot(key="k", title="Уэнздей", year=2022, label="s1e2")

    assert _playing_key(first) != _playing_key(second)
    assert _poster_identity(first) == _poster_identity(second)
    assert _poster_identity(first) == poster_name("Уэнздей", 2022, "tv"), "имя общее со списком"
