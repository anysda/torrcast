"""Какая Википедия отвечает на каком языке продукта; зовёт вторая волна справки."""

from __future__ import annotations

from typing import Final

from torrcast.adapters.wiki.endpoints import WIKI_HOST
from torrcast.domain.catalogs.tongue import EN, RU

_HOSTS: Final = {RU: WIKI_HOST, EN: "en.wikipedia.org"}


def wiki_host(language: str) -> str:
    """Википедия языка продукта; незнакомый язык отвечает русской, как и было.

    🔴 Меняется тут только источник СПРАВКИ. Паспорт картины
    (:class:`~torrcast.adapters.wiki.wiki_articles.WikiArticles`) как ходил в русскую
    Википедию, так и ходит: из него растёт имя, которым спрашивают трекер
    (:func:`~torrcast.domain.facts.english_title.english_title`), и сдвинь его язык -
    сдвинется поиск раздач, а его двигать не просили.

    Незнакомый язык отвечает русским хостом, а не пустотой: список тут вырастет раньше,
    чем перевод подписей, и промежуточный язык обязан терять справку не насовсем, а лишь
    оставаться на прежнем источнике.
    """
    return _HOSTS.get(language, WIKI_HOST)
