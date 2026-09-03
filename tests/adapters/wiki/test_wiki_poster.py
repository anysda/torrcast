"""Проверяет цепочку за постером: английская статья, инфобокс, файл, байты."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.endpoints import EN_WIKI_HOST, WIKI_HOST
from torrcast.adapters.wiki.wiki_poster import POSTER_WIDTH, WikiPoster

#: Первая секция английской статьи в том виде, в каком её отдаёт ``action=parse``.
INFOBOX = "{{Infobox film\n| name = Cars\n| image = Cars 2006.jpg\n| caption = Poster\n}}"
#: Английская статья БЕЗ картинки в инфобоксе - так выглядит статья про родство,
#: в которую ведёт голое имя «Брата».
KINSHIP = "{{Wiktionary}}\n'''Brother''' is a male sibling."
PICTURE = b"\xff\xd8\xff\xe0picture"


@dataclass
class FakeBytesClient:
    """Двойник загрузчика: помнит адреса и отдаёт байты или бросает, что велено."""

    body: bytes = PICTURE
    error: Exception | None = None
    asked: list[str] = field(default_factory=list)

    def fetch(self, address: str, timeout: float) -> bytes:
        self.asked.append(address)
        if self.error is not None:
            raise self.error
        return self.body


def _wiki(pages: dict[str, Any], text: dict[str, str], files: dict[str, Any]) -> FakeJsonClient:
    """Википедия, отвечающая тремя разными ответами на три шага цепочки."""

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if params["action"] == "query" and params.get("prop") == "imageinfo":
            return files.get(params["titles"], {"query": {"pages": [{"missing": True}]}})
        if params["action"] == "parse":
            return (
                {"parse": {"wikitext": text[params["page"]]}}
                if params["page"] in text
                else {"error": {"code": "missingtitle"}}
            )
        return pages

    return FakeJsonClient(answer)


def _file(name: str, address: str) -> dict[str, Any]:
    return {"query": {"pages": [{"title": name, "imageinfo": [{"thumburl": address}]}]}}


def test_the_chain_walks_from_the_russian_name_to_the_picture_bytes() -> None:
    """Три шага, три ответа - и на выходе байты, а не адрес чужого хоста."""
    client = _wiki(
        {"query": {"pages": [{"title": "Тачки", "langlinks": [{"lang": "en", "title": "Cars"}]}]}},
        {"Cars": INFOBOX},
        {"File:Cars 2006.jpg": _file("File:Cars 2006.jpg", "https://upload.wikimedia.org/c.jpg")},
    )
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster("Тачки", 2006, "movie", 1.0) == PICTURE
    assert files.asked == ["https://upload.wikimedia.org/c.jpg"]


def test_the_english_name_rides_along_with_the_article_and_costs_no_extra_trip() -> None:
    """🔴 Ссылка приезжает тем же запросом: лишнего похода по сети быть не должно.

    Спрошено у русского раздела ровно один раз, и спрошено с ``lllang=en``.
    """
    client = _wiki(
        {"query": {"pages": [{"title": "Тачки", "langlinks": [{"lang": "en", "title": "Cars"}]}]}},
        {"Cars": INFOBOX},
        {"File:Cars 2006.jpg": _file("File:Cars 2006.jpg", "https://upload.wikimedia.org/c.jpg")},
    )
    WikiPoster(client, FakeBytesClient()).poster("Тачки", 2006, "movie", 1.0)

    russian = [call for call in client.calls if call[0] == WIKI_HOST]
    assert len(russian) == 1, f"походов в русский раздел {len(russian)}"
    assert russian[0][2]["lllang"] == "en"
    assert all(call[0] == EN_WIKI_HOST for call in client.calls[1:])


def test_the_next_article_is_read_when_the_first_one_has_no_infobox_picture() -> None:
    """🔴 Живой «Брат»: голое имя ведёт в статью про родство, фильм стоит вторым.

    Останься чтение на первом ответе - постера у картины не было бы никогда, и разошлось
    бы это молча: карточка показывала бы кадр и выглядела бы исправной.
    """
    client = _wiki(
        {
            "query": {
                "pages": [
                    {"title": "Брат", "langlinks": [{"lang": "en", "title": "Brother"}]},
                    {
                        "title": "Брат (фильм, 1997)",
                        "langlinks": [{"lang": "en", "title": "Brother (1997 film)"}],
                    },
                ]
            }
        },
        {"Brother": KINSHIP, "Brother (1997 film)": "| image = Brat poster.jpg\n"},
        {
            "File:Brat poster.jpg": _file(
                "File:Brat poster.jpg", "https://upload.wikimedia.org/b.jpg"
            )
        },
    )
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster("Брат", 1997, "movie", 1.0) == PICTURE
    assert files.asked == ["https://upload.wikimedia.org/b.jpg"]


def test_the_file_is_asked_for_a_shrunk_copy() -> None:
    """Без ширины ответ приезжает вектором, а карточка плеера вектор не рисует."""
    client = _wiki(
        {"query": {"pages": [{"title": "Уэнздей", "langlinks": [{"lang": "en", "title": "W"}]}]}},
        {"W": "| image = W logo.svg\n"},
        {"File:W logo.svg": _file("File:W logo.svg", "https://upload.wikimedia.org/500px-W.png")},
    )
    WikiPoster(client, FakeBytesClient()).poster("Уэнздей", 2022, "tv", 1.0)

    asked = [call[2] for call in client.calls if call[2].get("prop") == "imageinfo"]
    assert asked and asked[0]["iiurlwidth"] == str(POSTER_WIDTH)


def test_a_picture_without_an_english_article_answers_with_nothing() -> None:
    """Ответа нет - и врать нечем: запасной путь заведён у того, кто зовёт."""
    client = _wiki({"query": {"pages": [{"title": "Внутри Лапенко", "missing": True}]}}, {}, {})
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster("Внутри Лапенко", 2019, "tv", 1.0) is None
    assert files.asked == [], "за файлом никто не ходил"


def test_a_file_missing_from_the_store_is_not_asked_for_bytes() -> None:
    """Имя в инфобоксе есть, файла на складе нет - адреса не будет, и похода тоже."""
    client = _wiki(
        {"query": {"pages": [{"title": "Тачки", "langlinks": [{"lang": "en", "title": "Cars"}]}]}},
        {"Cars": INFOBOX},
        {},
    )
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster("Тачки", 2006, "movie", 1.0) is None
    assert files.asked == []


def test_a_silent_wikipedia_is_told_apart_from_a_picture_without_a_poster() -> None:
    """🔴 429 и обрыв - не «постера нет»: спрашивать после них можно снова.

    Проглоти этот заход исключение - и картина, попавшая на 429, осталась бы без постера
    до конца жизни склада, а выглядело бы это как честное «не нашлось».
    """
    client = FakeJsonClient(lambda host, path, params: (_ for _ in ()).throw(OSError("HTTP 429")))

    with pytest.raises(OSError, match="429"):
        WikiPoster(client, FakeBytesClient()).poster("Тачки", 2006, "movie", 1.0)
