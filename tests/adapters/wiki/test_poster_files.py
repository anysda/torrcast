"""Проверяет, что постер берётся из ОБОИХ разделов и файл ищется на своём хосте."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.endpoints import EN_WIKI_HOST, WIKI_HOST
from torrcast.adapters.wiki.wiki_poster import WikiPoster
from torrcast.domain.facts.ask import Ask

#: Английская статья, у которой инфобокс есть, а строка постера ПУСТА. Так выглядит
#: «Chernobyl: Zone of Exclusion» вживую - и ровно на ней приговор расходился с байтами.
EN_EMPTY = "{{Infobox television\n| image        =\n| country      = Russia\n}}"
#: Русская статья той же картины: постер у неё свой, и лежит он локально.
RU_POSTER = (
    "{{Телесериал\n| название = Чернобыль. Зона отчуждения\n"
    "| изображение       = Сериал Зона.jpg\n| описание изображения = \n"
    "| формат изображения = FullHD\n}}"
)
#: Английская статья, которая свой постер называет.
EN_POSTER = "{{Infobox television\n| image = Chernobyl 2019 Miniseries.jpg\n}}"

RU_ADDRESS = "https://upload.wikimedia.org/wikipedia/ru/z.jpg"
EN_ADDRESS = "https://upload.wikimedia.org/wikipedia/en/m.jpg"
RU_PICTURE = b"\xff\xd8\xff\xe0russian"
EN_PICTURE = b"\xff\xd8\xff\xe0english"


@dataclass
class FakeBytesClient:
    """Двойник загрузчика: помнит адреса и отдаёт по адресу свои байты."""

    bodies: dict[str, bytes] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    def fetch(self, address: str, timeout: float) -> bytes:
        self.asked.append(address)
        return self.bodies[address]


def _page(title: str, english: str, year: int, kind: str = "Телесериалы") -> dict[str, Any]:
    page: dict[str, Any] = {
        "title": title,
        "categories": [{"title": f"Категория:{kind} {year} года"}],
    }
    if english:
        page["langlinks"] = [{"lang": "en", "title": english}]
    return page


def _wiki(
    pages: list[dict[str, Any]],
    text: dict[str, dict[str, str]],
    files: dict[str, dict[str, str]],
) -> FakeJsonClient:
    """Википедия, у которой у КАЖДОГО хоста свои статьи, свой вики-текст и свои файлы."""

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if params.get("prop") == "imageinfo":
            named = [name.partition(":")[2] for name in params["titles"].split("|")]
            here = files.get(host, {})
            return {
                "query": {
                    "pages": [
                        {"title": f"File:{name}", "imageinfo": [{"thumburl": here[name]}]}
                        for name in named
                        if name in here
                    ]
                }
            }
        if params.get("prop") == "revisions":
            here = text.get(host, {})
            return {
                "query": {
                    "pages": [
                        {"title": name, "revisions": [{"slots": {"main": {"content": here[name]}}}]}
                        for name in params["titles"].split("|")
                        if name in here
                    ]
                }
            }
        return {"query": {"pages": pages if host == WIKI_HOST else []}}

    return FakeJsonClient(answer)


def test_an_english_article_with_an_empty_image_line_falls_back_to_the_russian_poster() -> None:
    """🔴 Статья есть, год сходится, а ``| image =`` пуст - и байтов не было никогда.

    Раньше приговор говорил «да» по одному лишь наличию статьи, имя картинки уезжало
    в выдачу, и маршрут ``/api/poster/`` отвечал 404 навсегда. Постер этой картины
    лежит в русской статье, и брать его надо оттуда.
    """
    client = _wiki(
        [_page("Чернобыль. Зона отчуждения", "Chernobyl: Zone of Exclusion", 2014)],
        {
            EN_WIKI_HOST: {"Chernobyl: Zone of Exclusion": EN_EMPTY},
            WIKI_HOST: {"Чернобыль. Зона отчуждения": RU_POSTER},
        },
        {WIKI_HOST: {"Сериал Зона.jpg": RU_ADDRESS}},
    )
    files = FakeBytesClient({RU_ADDRESS: RU_PICTURE})
    ask = Ask("Чернобыль. Зона отчуждения", 2014, "tv", "")

    assert WikiPoster(client, files).poster(ask, 1.0) == RU_PICTURE
    assert files.asked == [RU_ADDRESS]


def test_the_russian_file_is_asked_of_the_russian_host_and_not_of_the_english_one() -> None:
    """🔴 Несвободная обложка лежит ЛОКАЛЬНО: на чужом хосте она ``missing``.

    Спроси мы русский файл у английского раздела - ответом была бы пустота, и находка
    осталась бы без картинки при живом и найденном файле.
    """
    client = _wiki(
        [_page("Чернобыль. Зона отчуждения", "Chernobyl: Zone of Exclusion", 2014)],
        {
            EN_WIKI_HOST: {"Chernobyl: Zone of Exclusion": EN_EMPTY},
            WIKI_HOST: {"Чернобыль. Зона отчуждения": RU_POSTER},
        },
        {WIKI_HOST: {"Сериал Зона.jpg": RU_ADDRESS}},
    )
    WikiPoster(client, FakeBytesClient({RU_ADDRESS: RU_PICTURE})).poster(
        Ask("Чернобыль. Зона отчуждения", 2014, "tv", ""), 1.0
    )

    asked = [
        (host, params["titles"]) for host, _, params in client.calls if "imageinfo" in str(params)
    ]
    assert (WIKI_HOST, "File:Сериал Зона.jpg") in asked, f"файл спрошен не там: {asked}"


def test_an_english_poster_of_a_later_candidate_beats_a_russian_one_of_an_earlier() -> None:
    """🔴 Русская обложка ДОБАВЛЯЕТ картинки, но ни одной не подменяет.

    У запроса «Чернобыль» 2019 года первым кандидатом идёт «Зона отчуждения»: её
    категории называют и 2014, и 2019. Своей русской картинкой она перебила бы постер
    мини-сериала HBO, который стоит кандидатом вторым и назван английской статьёй.
    """
    client = _wiki(
        [
            _page("Чернобыль", "Chernobyl: Zone of Exclusion", 2019),
            _page("Чернобыль (телесериал)", "Chernobyl (miniseries)", 2019),
        ],
        {
            EN_WIKI_HOST: {
                "Chernobyl: Zone of Exclusion": EN_EMPTY,
                "Chernobyl (miniseries)": EN_POSTER,
            },
            WIKI_HOST: {"Чернобыль": RU_POSTER},
        },
        {
            WIKI_HOST: {"Сериал Зона.jpg": RU_ADDRESS},
            EN_WIKI_HOST: {"Chernobyl 2019 Miniseries.jpg": EN_ADDRESS},
        },
    )
    files = FakeBytesClient({RU_ADDRESS: RU_PICTURE, EN_ADDRESS: EN_PICTURE})

    got = WikiPoster(client, files).poster(Ask("Чернобыль", 2019, "tv", ""), 1.0)
    assert got == EN_PICTURE, "русская обложка чужой статьи перебила английскую своей"


def test_a_picture_with_no_poster_anywhere_keeps_no_name_at_all() -> None:
    """Нет обложки ни в одном разделе - нет и картинки: строка остаётся строкой.

    Это вторая половина того же правила: приговор обязан молчать там, где байтов не
    будет, иначе на месте картинки снова появится рамка вокруг пустоты.
    """
    client = _wiki(
        [_page("Чернобыль. Зона отчуждения", "Chernobyl: Zone of Exclusion", 2014)],
        {
            EN_WIKI_HOST: {"Chernobyl: Zone of Exclusion": EN_EMPTY},
            WIKI_HOST: {"Чернобыль. Зона отчуждения": "{{Телесериал\n| изображение = \n}}"},
        },
        {},
    )
    ask = Ask("Чернобыль. Зона отчуждения", 2014, "tv", "")
    poster = WikiPoster(client, FakeBytesClient())

    assert poster.wanted([ask], 1.0)[ask] == [], "приговор пообещал байты, которых нет"
    assert poster.poster(ask, 1.0) is None
