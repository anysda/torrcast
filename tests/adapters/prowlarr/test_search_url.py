"""Проверяет адрес поискового запроса: агрегат, персональный запрос и провод."""

from torrcast.adapters.prowlarr.search_url import CATEGORIES, search_url


def test_адрес_ведёт_в_агрегат_prowlarr_со_всеми_категориями() -> None:
    """Эндпоинт у Jackett и Prowlarr разный; наш клиент ходит в /api/v1/search."""
    url = search_url("http://127.0.0.1:9696", "KEY", "матрица", 100)
    assert url.startswith("http://127.0.0.1:9696/api/v1/search?apikey=KEY")
    assert "&type=search" in url
    assert "&categories=2000&categories=5000&categories=8000" in url
    assert len(CATEGORIES) == 3
    assert "&indexerIds=" not in url


def test_персональный_запрос_называет_индексер_номером() -> None:
    """Врозь - значит по запросу на индексер, и номер у него свой на каждой установке."""
    url = search_url("http://p", "k", "матрица", 100, 7)
    assert url.endswith("&indexerIds=7")


def test_поисковый_url_несёт_запрос_без_склейки() -> None:
    """На проводе - разведённая форма: иначе санитайзер Prowlarr склеит слова (TC-129)."""
    url = search_url("http://p", "k", "Steins;Gate", 100)
    assert "query=Steins%20Gate" in url
    assert "%3B" not in url


def test_лимит_едет_на_провод_как_просили() -> None:
    assert "&limit=200" in search_url("http://p", "k", "матрица", 200)
