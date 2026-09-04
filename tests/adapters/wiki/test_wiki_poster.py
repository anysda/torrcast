"""Проверяет цепочку за постером: статья со сверенным годом, инфобокс, файл, байты."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.endpoints import EN_WIKI_HOST, WIKI_HOST
from torrcast.adapters.wiki.poster_files import POSTER_WIDTH
from torrcast.adapters.wiki.wiki_poster import WikiPoster
from torrcast.domain.facts.ask import Ask

#: Первая секция английской статьи в том виде, в каком её отдаёт ``revisions``.
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


def _page(title: str, english: str, year: int | None, kind: str = "Фильмы") -> dict[str, Any]:
    """Статья русского раздела: ссылка на английскую и год в категориях."""
    page: dict[str, Any] = {"title": title, "langlinks": [{"lang": "en", "title": english}]}
    if year is not None:
        page["categories"] = [{"title": f"Категория:{kind} {year} года"}]
    return page


def _stored(name: str, kept: Any) -> dict[str, Any]:
    """Один файл в ответе ``imageinfo``: адрес, а с ним стороны, если проба их назвала.

    Стороны названы не всеми пробами намеренно: живой ответ их везёт всегда, а вот
    ПРОВЕРЯЮТ их только те пробы, которые про вордмарк. Остальным они лишний шум.
    """
    if isinstance(kept, str):
        return {"title": f"File:{name}", "imageinfo": [{"thumburl": kept}]}
    address, wide, high = kept
    return {
        "title": f"File:{name}",
        "imageinfo": [{"thumburl": address, "thumbwidth": wide, "thumbheight": high}],
    }


def _wiki(
    pages: list[dict[str, Any]], text: dict[str, str], files: dict[str, Any]
) -> FakeJsonClient:
    """Википедия, отвечающая тремя разными ответами на три шага цепочки."""

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if params.get("prop") == "imageinfo":
            named = [name.partition(":")[2] for name in params["titles"].split("|")]
            return {
                "query": {"pages": [_stored(name, files[name]) for name in named if name in files]}
            }
        if params.get("prop") == "revisions":
            return {
                "query": {
                    "pages": [
                        {
                            "title": name,
                            "revisions": [{"slots": {"main": {"content": text[name]}}}],
                        }
                        for name in params["titles"].split("|")
                        if name in text
                    ]
                }
            }
        return {"query": {"pages": pages}}

    return FakeJsonClient(answer)


def test_the_chain_walks_from_the_russian_name_to_the_picture_bytes() -> None:
    """Три шага, три ответа - и на выходе байты, а не адрес чужого хоста."""
    client = _wiki(
        [_page("Тачки", "Cars", 2006)],
        {"Cars": INFOBOX},
        {"Cars 2006.jpg": "https://upload.wikimedia.org/c.jpg"},
    )
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster(Ask("Тачки", 2006, "movie"), 1.0) == PICTURE
    assert files.asked == ["https://upload.wikimedia.org/c.jpg"]


def test_the_english_name_rides_along_with_the_article_and_costs_no_extra_trip() -> None:
    """🔴 Ссылка приезжает тем же запросом: лишнего похода по сети быть не должно.

    Спрошено у русского раздела ровно один раз, и спрошено с ``lllang=en``.
    """
    client = _wiki(
        [_page("Тачки", "Cars", 2006)],
        {"Cars": INFOBOX},
        {"Cars 2006.jpg": "https://upload.wikimedia.org/c.jpg"},
    )
    WikiPoster(client, FakeBytesClient()).poster(Ask("Тачки", 2006, "movie"), 1.0)

    linked = [call for call in client.calls if "lllang" in call[2]]
    assert len(linked) == 1, f"за ссылкой ходили {len(linked)} раз"
    assert linked[0][0] == WIKI_HOST and linked[0][2]["lllang"] == "en"
    assert client.calls[0] == linked[0], "ссылка спрошена не первым же запросом"
    assert any(call[0] == EN_WIKI_HOST for call in client.calls[1:])


def test_the_next_article_is_read_when_the_first_one_has_no_infobox_picture() -> None:
    """🔴 Живой «Брат»: голое имя ведёт в статью про родство, фильм стоит вторым.

    Останься чтение на первом ответе - постера у картины не было бы никогда, и разошлось
    бы это молча: карточка показывала бы кадр и выглядела бы исправной.
    """
    client = _wiki(
        [_page("Брат", "Brother", 1997), _page("Брат (фильм, 1997)", "Brother (1997 film)", 1997)],
        {"Brother": KINSHIP, "Brother (1997 film)": "| image = Brat poster.jpg\n"},
        {"Brat poster.jpg": "https://upload.wikimedia.org/b.jpg"},
    )
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster(Ask("Брат", 1997, "movie"), 1.0) == PICTURE
    assert files.asked == ["https://upload.wikimedia.org/b.jpg"]


def test_the_file_is_asked_for_a_shrunk_copy() -> None:
    """Без ширины ответ приезжает вектором, а карточка плеера вектор не рисует."""
    client = _wiki(
        [_page("Уэнздей", "W", 2022, kind="Телесериалы")],
        {"W": "| image = W logo.svg\n"},
        {"W logo.svg": "https://upload.wikimedia.org/500px-W.png"},
    )
    WikiPoster(client, FakeBytesClient()).poster(Ask("Уэнздей", 2022, "tv"), 1.0)

    asked = [call[2] for call in client.calls if call[2].get("prop") == "imageinfo"]
    assert asked and asked[0]["iiurlwidth"] == str(POSTER_WIDTH)


def test_a_wordmark_in_the_infobox_gives_way_to_the_cover_of_the_other_section() -> None:
    """🔴 Живая «Аниматрица»: в английском инфобоксе логотип 512x147, а не обложка.

    Карточка плеера рисовала таким «постером» широкую тёмную полосу с надписью, по
    которой картину не узнать, - а обложка той же картины всё это время лежала в русской
    статье и стояла в очереди ВТОРОЙ, за вордмарком. Отказ выносится по сторонам
    картинки, и очередь идёт дальше сама.
    """
    client = _wiki(
        [_page("Аниматрица", "The Animatrix", 2003)],
        {
            "The Animatrix": "| image = Theanimatrix-logo.svg\n",
            "Аниматрица": "| изображение = The Animatrix poster.jpg\n",
        },
        {
            "Theanimatrix-logo.svg": ("https://upload.wikimedia.org/500px-logo.png", 500, 144),
            "The Animatrix poster.jpg": ("https://thumb.wikimedia.org/500px-p.jpg", 500, 638),
        },
    )
    files = FakeBytesClient()
    ask = Ask("Аниматрица", 2003, "movie")

    assert WikiPoster(client, files).poster(ask, 1.0) == PICTURE
    assert files.asked == ["https://thumb.wikimedia.org/500px-p.jpg"], "за логотипом не ходили"


def test_a_wordmark_alone_leaves_the_picture_without_an_address() -> None:
    """Лежачая картинка - не постер, и обещать под неё имя нельзя.

    Пустота тут честна: у зовущего на неё свой ответ - кадр показа у карточки, голая
    строка у списка обзора, - а рамка вокруг тёмной полосы не ответ никому.
    """
    client = _wiki(
        [_page("Уэнздей", "W", 2022, kind="Телесериалы")],
        {"W": "| image = W logo.svg\n"},
        {"W logo.svg": ("https://upload.wikimedia.org/500px-W.png", 500, 130)},
    )
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster(Ask("Уэнздей", 2022, "tv"), 1.0) is None
    assert files.asked == [], "за байтами вордмарка никто не ходил"


def test_an_upright_cover_is_not_touched_by_the_wordmark_rule() -> None:
    """Живой «Интерстеллар»: 220x326, и правило про лежачие его не касается."""
    client = _wiki(
        [_page("Интерстеллар", "Interstellar", 2014)],
        {"Interstellar": "| image = Interstellar film poster.jpg\n"},
        {"Interstellar film poster.jpg": ("https://upload.wikimedia.org/i.jpg", 220, 326)},
    )
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster(Ask("Интерстеллар", 2014, "movie"), 1.0) == PICTURE
    assert files.asked == ["https://upload.wikimedia.org/i.jpg"]


def test_the_sides_of_the_file_are_asked_for_along_with_its_address() -> None:
    """🔴 Без ``size`` в ``iiprop`` мерить вордмарк нечем, и правило станет слепым.

    У неуменьшенного файла сторон в ответе нет вовсе, и молчание про них значит
    «пропустить»: слепое правило зеленело бы на подделке и пускало бы логотипы живьём.
    """
    client = _wiki(
        [_page("Тачки", "Cars", 2006)],
        {"Cars": INFOBOX},
        {"Cars 2006.jpg": "https://upload.wikimedia.org/c.jpg"},
    )
    WikiPoster(client, FakeBytesClient()).poster(Ask("Тачки", 2006, "movie"), 1.0)

    asked = [call[2] for call in client.calls if call[2].get("prop") == "imageinfo"]
    assert asked, "запрос про файл вообще был"
    assert "size" in asked[0]["iiprop"].split("|"), f"спрошено {asked[0]['iiprop']}"


def test_a_picture_without_an_english_article_answers_with_nothing() -> None:
    """Ответа нет - и врать нечем: запасной путь заведён у того, кто зовёт."""
    client = _wiki([{"title": "Внутри Лапенко", "missing": True}], {}, {})
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster(Ask("Внутри Лапенко", 2019, "tv"), 1.0) is None
    assert files.asked == [], "за файлом никто не ходил"


def test_a_file_missing_from_the_store_is_not_asked_for_bytes() -> None:
    """Имя в инфобоксе есть, файла на складе нет - адреса не будет, и похода тоже."""
    client = _wiki([_page("Тачки", "Cars", 2006)], {"Cars": INFOBOX}, {})
    files = FakeBytesClient()

    assert WikiPoster(client, files).poster(Ask("Тачки", 2006, "movie"), 1.0) is None
    assert files.asked == []


def test_a_silent_wikipedia_is_told_apart_from_a_picture_without_a_poster() -> None:
    """🔴 429 и обрыв - не «постера нет»: спрашивать после них можно снова.

    Проглоти этот заход исключение - и картина, попавшая на 429, осталась бы без постера
    до конца жизни склада, а выглядело бы это как честное «не нашлось».
    """
    client = FakeJsonClient(lambda host, path, params: (_ for _ in ()).throw(OSError("HTTP 429")))

    with pytest.raises(OSError, match="429"):
        WikiPoster(client, FakeBytesClient()).poster(Ask("Тачки", 2006, "movie"), 1.0)
