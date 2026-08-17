"""Имена, под которыми статья может лежать в Википедии; зовёт добор справки."""

from __future__ import annotations

from torrcast.domain.facts.patterns import _QUALIFIERS


def titles_for(title: str, year: int | None) -> list[str]:
    """Под какими именами статья может лежать в русской Википедии, в порядке доверия.

    Первым — само название: «Тачки 2» так и называется. Дальше уточнения в скобках,
    которыми Википедия разводит одноимённое: «Моана» голым именем — это страница
    значений про полинезийское слово, а мультфильм 2016 года лежит под «Моана
    (мультфильм)», ремейк 2026-го — под «Моана (фильм, 2026)».

    Подзаголовок после двоеточия отрезается отдельным кандидатом: раздачи подписывают
    старое кино развёрнуто («Моана: романтика золотого века»), а статья называется
    короче. Чужую статью это не притащит — год всё равно проверяется по тексту.

    Регистр внутри слова Википедия сама не чинит: ``redirects=1`` нормализует лишь ПЕРВУЮ
    букву. «breaking bad» уходит в «Breaking bad» и мимо статьи, тогда как редирект есть с
    «Breaking Bad»; так же теряются «fruits basket», «twin peaks», «true detective». Поэтому
    к именам добавляются регистровые варианты голого имени - заглавные слова и нижний
    регистр. Лишний кандидат чужого не тащит (год и заголовок всё равно сверяются), а
    редирект по нужному написанию находится в той же прямой выборке, без похода в поиск.
    """
    bases = [title.strip()]
    head = title.split(":", 1)[0].strip()
    if head and head != bases[0]:
        bases.append(head)
    out: list[str] = []
    for base in bases:
        for qualifier in _QUALIFIERS:
            if "{year}" in qualifier and year is None:
                continue
            name = base + qualifier.format(year=year)
            if name not in out:
                out.append(name)
    for base in bases:
        for variant in (base.title(), base.lower()):
            if variant != base and variant not in out:
                out.append(variant)
    return out
