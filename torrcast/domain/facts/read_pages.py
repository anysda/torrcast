"""Кандидат в статью, статья в описание; зовёт добор справки к меню."""

from __future__ import annotations

from collections.abc import Mapping, Set

from torrcast.domain.facts.article_gate import _declares_work, _fits_type
from torrcast.domain.facts.confirms import confirms
from torrcast.domain.facts.linked_title import linked_title
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.facts.wiki_reply import _article
from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue


def _read_pages(
    payload: JsonValue,
    candidates: dict[tuple[str, int | None], list[str]],
    confirmed: Set[tuple[str, int | None]] = frozenset(),
    kinds: Mapping[tuple[str, int | None], str] | None = None,
) -> tuple[
    dict[tuple[str, int | None], str],
    dict[tuple[str, int | None], str],
    dict[tuple[str, int | None], str],
]:
    """Разобрать ответ Википедии: кандидат → статья, её описание, Q-код и чужой заголовок.

    Запрошенное имя и заголовок статьи — не одно и то же: API нормализует регистр и ведёт
    по перенаправлениям, и «Моана (мультфильм)» вполне может ответить статьёй с другим
    заголовком. Обратный путь API отдаёт сам, списками ``normalized`` и ``redirects``.

    🔴 Статья обязана быть ТОГО ЖЕ ТИПА, что спрошенная картина (:func:`_fits_type`), и
    одного года тут мало. Год сверяется по тексту (:func:`confirms`), а текст чужой
    статьи охотно называет чужой год своим: «Робокоп (телесериал)» открывается словами
    «канадский телесериал 1994 года» и тут же ссылается на «Робокопа» (1987) - и сверка
    года у фильма 1987-го проходила НА СЕРИАЛЕ. Хуже того, кандидат с уточнением
    «(телесериал)» стоит в очереди раньше «(фильм, {year})»
    (:func:`~torrcast.domain.facts.titles_for.titles_for`), поэтому до настоящей статьи
    очередь не доходила вовсе: зритель читал про сериал под именем фильма.

    Экранизация и её первоисточник - разные картины с общим именем и общими годами в
    тексте, и развести их может только объявленный тип. Тип у разбора имени есть, и
    подсказывается он сюда (``kinds``); года справке НЕ подсказывают - он подтвердит ровно
    ту подмену, которую должен ловить. Тип не назван или назван «other» - сверять нечем,
    и гейт молчит, как молчит он и на статье, не назвавшей своего типа.

    Третьим ответом едет межъязыковой заголовок принятой статьи
    (:func:`linked_title`) - адрес той же картины в чужой Википедии. Берётся он тут, а не
    вторым проходом по ответу, ровно по одной причине: принятая статья выбрана здешними
    гейтами, и второй проход обязан был бы повторить их все, чтобы не разойтись с первым.
    Ссылка едет тем же запросом и стоит ноль; кому она не нужна, тот её не читает.
    """
    hops, pages = wiki_pages(payload)
    about: dict[tuple[str, int | None], str] = {}
    entities: dict[tuple[str, int | None], str] = {}
    linked: dict[tuple[str, int | None], str] = {}
    for key, names in candidates.items():
        for name in names:
            page = _article(name, hops, pages)
            if page is None:
                continue
            extract = str(page.get("extract") or "")
            if not _fits_type(
                _asked_series((kinds or {}).get(key, "")), str(page.get("title") or ""), extract
            ):
                continue
            # Некоторые точные статьи не называют год в первых 500 символах. Тогда
            # пару имени, года и типа вправе подтвердить офлайн-карта IMDb. Послабление
            # действует только для полного имени: отрезанное до двоеточия имя легко
            # оказалось бы другой частью той же франшизы.
            #
            # 🔴 От сверки ГОДА карта освобождает, а от вопроса «произведение ли это» -
            # нет (:func:`_declares_work`). Карта доказывает, что картина с таким именем
            # и годом есть на свете, но про статью под этим именем не говорит ничего:
            # «Титаник» - пароход, «Дюна» - песчаный холм, и обе уходили зрителю как
            # справка о фильме (TC-957). Год у них не подтверждался - ровно ту защиту
            # послабление и снимало.
            exact = (
                key in confirmed
                and name.casefold() == key[0].strip().casefold()
                and _declares_work(str(page.get("title") or ""), extract)
            )
            if not confirms(extract, key[1]) and not exact:
                continue
            about[key] = extract
            if linked_here := linked_title(page):
                linked[key] = linked_here
            props = json_map(page.get("pageprops"))
            if props.get("wikibase_item"):
                entities[key] = str(props["wikibase_item"])
            break
    return about, entities, linked


def _asked_series(kind: str) -> bool | None:
    """Тип разобранной картины в вопрос гейта статьи: сериал, фильм или «не знаю».

    ``other`` - это не кино вовсе (концерт, книга, программа), и спрашивать про него
    «сериал или фильм» бессмысленно: гейту отвечается «не знаю», и он молчит. Так же
    отвечается и не названный тип - гейту нельзя подсовывать «фильм» там, где типа
    просто не спросили.
    """
    return {"tv": True, "movie": False}.get(kind)
