"""Просьбы о постере и адрес запасного кадра; зовёт сборщик картинки карточки."""

from __future__ import annotations

from torrcast.domain.facts.ask import Ask
from torrcast.domain.playback_snapshot import PlaybackSnapshot


def _poster_asks(shown: PlaybackSnapshot) -> list[Ask]:
    """Просьбы о постере этой картины, в порядке доверия к именам.

    Оригинальное имя едет ПОЛЕМ просьбы, а не ещё одним именем в очереди: русской
    статьи у части картин нет вовсе, и английская лежит ровно под оригинальным именем -
    но искать её там имеет смысл только после того, как русский раздел промолчал
    (:meth:`~torrcast.adapters.wiki.poster_pages.PosterPages.wanted`).
    """
    kind = "tv" if shown.label else "movie"
    year = shown.year or None
    out = [Ask(shown.title.strip(), year, kind, shown.original.strip())]
    asked = shown.query.replace("-", " ").strip()
    if asked and asked.casefold() != out[0].title.casefold():
        out.append(Ask(asked, year, kind, ""))
    return [ask for ask in out if ask.title]


def _manifest(where: str) -> str:
    """Адрес HLS-базы превратить в адрес мастер-манифеста."""
    return where if where.rstrip("/").endswith(".m3u8") else where.rstrip("/") + "/index.m3u8"
