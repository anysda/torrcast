"""Имя картины из английской статьи; зовёт разбор паспорта."""

from __future__ import annotations

from torrcast.domain.facts.linked_title import linked_title
from torrcast.domain.facts.patterns import _TAIL_RE
from torrcast.domain.json_value import JsonValue


def english_title(page: JsonValue) -> str:
    """Как та же картина называется в английской Википедии; уточнение в скобке отрезано.

    Русская статья пишет оригинал в первой фразе не всегда: у аниме в скобке стоят
    иероглифы («Юная революционерка Утэна» — 少女革命ウテナ), и латиницы там нет вовсе.
    Межъязыковая ссылка отвечает на тот же вопрос и едет тем же запросом
    (:func:`extract_params`), а «(TV series)» и «(film)» на конце — это разметка
    Википедии, а не часть имени: индексеру с ней делать нечего.
    """
    return _TAIL_RE.sub("", linked_title(page)).strip()
