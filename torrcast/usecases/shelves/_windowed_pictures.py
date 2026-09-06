"""Картины из окна ленты: раздачи внутри срока, кластеризованные и отфильтрованные."""

from __future__ import annotations

from datetime import datetime

from torrcast.domain.cluster import cluster
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.picture import Picture
from torrcast.domain.recent_enough import recent_enough
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue


def _windowed_pictures(
    rows: list[FeedRow], catalogue: TorrentCatalogue, *, days: int, now: datetime
) -> tuple[list[Picture], dict[str, datetime]]:
    """Картины окна и время первой раздачи по хэшу; без года или рода - картина не в счёт.

    Год и род спрошены тут же, а не у зовущего: обе полки (ТЗ §9) хотят ровно тот же
    отсев, а не свой собственный на каждой. Он же - вторая линия обороны от мусора
    ленты сверх фильтра категорий на самом запросе (:mod:`torrcast.adapters.prowlarr.
    feed_url`): «other» не показывают вовсе.
    """
    windowed = [row for row in rows if recent_enough(row.published, now, days)]
    releases = catalogue.to_releases([row.raw for row in windowed])
    pictures = [p for p in cluster(releases) if p.kind in ("movie", "tv") and p.year]
    dates: dict[str, datetime] = {}
    for row in windowed:
        info_hash = row.raw.info_hash.lower()
        if info_hash not in dates or row.published < dates[info_hash]:
            dates[info_hash] = row.published
    return pictures, dates


def _dates_of(picture: Picture, dates: dict[str, datetime]) -> list[datetime]:
    """Времена первой раздачи всех релизов картины, какие нашлись в окне."""
    hashes = (magnet_hash(release.magnet) for release in picture.releases)
    return [dates[h] for h in hashes if h and h in dates]


__all__ = ["_dates_of", "_windowed_pictures"]
