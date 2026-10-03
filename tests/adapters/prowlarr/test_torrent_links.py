"""Ссылки на .torrent запоминаются из выдачи Prowlarr по infohash, магнет не меняется."""

from torrcast.adapters.prowlarr.from_feed_json import from_feed_json
from torrcast.adapters.prowlarr.from_json import from_json
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.adapters.prowlarr.torrent_links import LINKS

KEY = "AB" * 20
LINK = "http://prowlarr.invalid/12/download?apikey=k&link=x&file=Cars"


def _row(**extra: object) -> dict[str, object]:
    row = {"title": "Cars 2006 1080p", "infoHash": KEY, "size": 7_000_000_000, "seeders": 40}
    row["indexer"] = "RuTor"
    row.update(extra)
    return row


def test_the_search_answer_feeds_the_link_by_infohash() -> None:
    rows = from_json([_row(downloadUrl=LINK)])

    assert LINKS.link_for(KEY.lower()) == LINK
    assert "download" not in to_releases(rows)[0].magnet  # магнет прежний, без ключа


def test_the_feed_answer_feeds_the_link_too() -> None:
    from_feed_json([_row(downloadUrl=LINK, publishDate="2026-10-01T10:00:00Z")])

    assert LINKS.link_for(KEY) == LINK


def test_rows_without_a_hash_or_an_http_link_leave_nothing() -> None:
    from_json(
        [
            _row(downloadUrl="magnet:?xt=urn:btih:" + KEY),
            _row(infoHash=None, downloadUrl=LINK),
            _row(infoHash="short", downloadUrl=LINK),
            _row(),
        ]
    )

    assert LINKS.link_for(KEY) is None


def test_the_registry_keeps_the_5000_latest_links() -> None:
    LINKS.remember(
        [{"infoHash": f"{i:040x}", "downloadUrl": f"http://p.invalid/{i}"} for i in range(5001)]
    )

    assert LINKS.link_for(f"{0:040x}") is None
    assert LINKS.link_for(f"{1:040x}") == "http://p.invalid/1"
    assert LINKS.link_for(f"{5000:040x}") == "http://p.invalid/5000"
