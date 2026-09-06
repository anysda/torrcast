"""Проверяет адрес ленты последних раздач: без query, узкой категорией."""

from __future__ import annotations

from torrcast.adapters.prowlarr.feed_url import FEED_CATEGORIES, feed_url


def test_the_feed_url_has_no_query_string() -> None:
    """Лента спрашивает БЕЗ запроса: агрегат сам отдаёт последние раздачи."""
    url = feed_url("http://127.0.0.1:9696", "KEY", 200)

    assert "query=" not in url
    assert url.startswith("http://127.0.0.1:9696/api/v1/search?apikey=KEY")


def test_the_feed_url_carries_movie_tv_and_other_categories() -> None:
    """Софт и музыку лента не спрашивает, а «Other» спрашивает: там лежит целый индексер."""
    url = feed_url("http://p", "k", 200)

    assert "&categories=2000&categories=5000&categories=100003" in url
    assert len(FEED_CATEGORIES) == 3
    assert "categories=6000" not in url


def test_the_limit_travels_on_the_wire_as_asked() -> None:
    assert "&limit=300" in feed_url("http://p", "k", 300)
