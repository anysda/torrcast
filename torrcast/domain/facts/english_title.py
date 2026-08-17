"""Имя картины из английской статьи; зовёт разбор паспорта."""

from __future__ import annotations

from typing import Any

from torrcast.domain.facts.patterns import _TAIL_RE


def english_title(page: Any) -> str:
    """Как та же картина называется в английской Википедии; уточнение в скобке отрезано.

    Русская статья пишет оригинал в первой фразе не всегда: у аниме в скобке стоят
    иероглифы («Юная революционерка Утэна» — 少女革命ウテナ), и латиницы там нет вовсе.
    Межъязыковая ссылка отвечает на тот же вопрос и едет тем же запросом
    (:func:`_extract_params`), а «(TV series)» и «(film)» на конце — это разметка
    Википедии, а не часть имени: индексеру с ней делать нечего.
    """
    links = page.get("langlinks") or [] if isinstance(page, dict) else []
    name = str(links[0].get("title") or "") if links else ""
    return _TAIL_RE.sub("", name).strip()
