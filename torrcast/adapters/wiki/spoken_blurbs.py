"""Справка на языке продукта или её отсутствие; зовёт добор справки к меню."""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.adapters.wiki.wiki_translated import Key, wiki_translated
from torrcast.domain.catalogs.tongue import RU, tongue
from torrcast.domain.facts.blurb_outcome import BLANK
from torrcast.ports.json_client import JsonClient


def spoken_blurbs(
    client: JsonClient,
    about: dict[Key, str],
    linked: Mapping[Key, str],
    answered: set[Key],
    timeout: float,
) -> tuple[dict[Key, str], set[Key]]:
    """Описания на языке продукта вместо русских; под русским языком - ровно то, что было.

    🔴 Русский язык не платит тут НИЧЕГО: ни запроса, ни ветки разбора - ответ отдаётся
    тем же объектом, каким пришёл. Это не бережливость, а граница правки: справка под
    ``--ru`` обязана остаться посимвольно прежней.

    Второй ответ - про какие картины источник ответил честно. Из него вычтены дефектные
    (:data:`~torrcast.domain.facts.blurb_outcome.BLANK`), и вот почему: «ответил, и
    справки нет» вызывающий вправе запомнить пустым на неделю
    (:data:`~torrcast.domain.facts.settings.EMPTY_TTL`), а сложить на полку СЛОМАННЫЙ
    разбор значит держать дефект неделю и после починки. Честное «статьи на этом языке
    нет» на полку ложится: оно от починки не изменится.
    """
    language = tongue()
    if language == RU:
        return about, answered
    spoken, outcome = wiki_translated(client, list(about), linked, language, timeout)
    return spoken, answered - {key for key, why in outcome.items() if why == BLANK}
