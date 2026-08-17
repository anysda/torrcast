"""Русское имя, перенаправленное на латинский заголовок; зовёт выборка по имени."""

from __future__ import annotations

from typing import Any

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.patterns import _CYRILLIC, _TAIL_RE, _WORK_RE
from torrcast.domain.facts.wiki_reply import _article
from torrcast.domain.slugify import slugify


def redirected_name(
    names: list[str], hops: dict[str, str], pages: dict[str, Any], title: str
) -> Origin:
    """Русское имя, которое сама Википедия перенаправляет на латинский заголовок.

    Слепая зона справки на аниме, подписанном латиницей: «врата штейна» - живое
    перенаправление на статью ``Steins;Gate``, но статья эта о ВИЗУАЛЬНОЙ НОВЕЛЛЕ, с
    которой всё началось, и киношного гейта :func:`_about_cinema` она не проходит. Справка
    молчала, добор шёл транслитом ``vrata shteyna`` в никуда, а до-вожаком склейки
    оставался сиквел - и скачок года гейт добора честно читал как подмену.

    Отвечать тут есть чем, и ответ подтверждён источником: перенаправление русского имени
    на латинский заголовок - это и есть утверждение Википедии «то же самое зовут вот так».
    Ровно его мы и берём - ИМЕНЕМ, без года:

    * год такой статьи чужой картине не годится вовсе. У ``Steins;Gate`` первая врезка
      кончается словами «20 августа 2026 года выйдет ремейк новеллы», и :func:`picture_year`
      честно называет 2026 - год, которого у аниме 2011 года нет и близко. Год объявлен
      сильнее выдачи, поэтому чужого года не бывает: пусто;
    * заголовок обязан быть на латинице, а запрос - по-русски. Это граница, за которой
      начинаются статьи о людях: русская Википедия подписывает их по-русски («Питт,
      Брэд»), и киношный гейт им по-прежнему единственная преграда;
    * статья обязана назвать себя произведением (:data:`_WORK_RE`) - иначе перенаправление
      привело бы к компании или к городу.
    """
    if not _CYRILLIC.search(title):
        return Origin()
    for name in names:
        page = _article(name, hops, pages)
        if page is None:
            continue
        heading = str(page.get("title") or "")
        if not heading or _CYRILLIC.search(heading) or slugify(heading) == slugify(name):
            continue
        if not _WORK_RE.search(f"{heading} {page.get('extract') or ''}"):
            continue
        return Origin(title=_TAIL_RE.sub("", heading).strip() or heading)
    return Origin()
