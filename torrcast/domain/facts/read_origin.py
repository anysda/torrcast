"""Статьи-кандидаты в паспорт картины; зовут все пути справки."""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.facts.akin import _crowded, akin
from torrcast.domain.facts.article_gate import _about_cinema, _fits_type
from torrcast.domain.facts.english_title import english_title
from torrcast.domain.facts.franchise_article import franchise_article
from torrcast.domain.facts.latin_title import latin_title
from torrcast.domain.facts.named_original import named_original
from torrcast.domain.facts.namesake import namesake
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.patterns import _CYRILLIC, _TAIL_RE
from torrcast.domain.facts.picture_year import picture_year
from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.transliterate import transliterate


def read_origin(
    pages: Sequence[JsonValue], title: str, trusted: bool = False, series: bool | None = None
) -> Origin:
    """Статьи-кандидаты → паспорт. Побеждает первая, которая про кино и про то самое.

    Статья должна быть про кино (:func:`_about_cinema`) — «Восхождение» это ещё и
    альпинизм, а «Матрица» — таблица, — и того же типа, что спросили
    (:func:`_fits_type`). А вот «про то самое» проверяется по-разному, и это ``trusted``.

    * **Поиск Википедии** (``trusted=False``) честно приносит однофамильцев, актёров и
      саундтреки — их отсеивает :func:`akin` по заголовку.
    * **Прямая выборка по имени** (``trusted=True``) — другое дело: имя мы назвали САМИ,
      и до статьи нас довела сама Википедия своим перенаправлением. Спорить с ней
      заголовком нельзя: она за тем и заведена, чтобы знать, что «Уэнсдей» пишется
      «Уэнздей», «ВандаВижн» — «Ванда/Вижн», а «Фруктовая корзинка» — «Корзинка
      фруктов». :func:`akin` все три заголовка отвергала, и справка молчала ровно там,
      где знала ответ: на этих именах поиск и оставался без оригинала.

    Название латиницей ищется по убыванию точности: скобка первой фразы («англ. …»),
    затем заголовок английской статьи, затем сам заголовок, если он и так на латинице
    (франшиза «Kingsman» подписана именно так — и именно так её ищут индексеры).

    ⚠️ Спросили ЛАТИНИЦЕЙ - :func:`akin` бессильна: заголовок русской статьи про «Тачки»
    с запросом ``cars`` не сверить ничем. Тождество тогда доказывает сам оригинал: статья
    «Тачки» открывается скобкой «англ. Cars», и это ровно то имя, которое спросили. Точное
    равенство обязательно - поиск Википедии по слову ``cars`` первой приносит «Тачки 4»
    («англ. Cars 4»), и на вхождении подстрокой человек получил бы не ту картину.

    ⚠️ Голое имя франшизы частью франшизы не отвечается (:func:`_crowded`): «гарри поттер»
    приносил паспорт ПЯТОГО фильма, добор уходил по его оригиналу и приводил 79 чужих
    раздач одной части. Либо статья самой франшизы, либо ничего.

    🔴 TC-480. Зеркальный случай - спросили ЧАСТЬ, а отвечает имя франшизы
    (:func:`_other_part`): такой паспорт отдаётся догадкой и без года. Часть, названную
    не номером, а подзаголовком, такая статья не отвечает вовсе
    (:func:`~torrcast.domain.facts.franchise_article.franchise_article`).
    """
    crowd = _crowded(title, pages)
    shortened = Origin()
    whole = Origin()
    for page in pages:
        if page is None:
            continue
        article = json_map(page)
        heading = str(article.get("title") or "")
        extract = str(article.get("extract") or "")
        if not _about_cinema(heading, extract) or not _fits_type(series, heading, extract):
            continue
        latin = (
            latin_title(extract)
            or english_title(page)
            or ("" if _CYRILLIC.search(heading) else heading)
        )
        if franchise_article(title, heading):
            # 🔴 TC-779. Статья про франшизу, а спрошена её картина с подзаголовком:
            # ни имя латиницей, ни год у неё не про то, что назвали.
            continue
        if _other_part(title, heading):
            # 🔴 TC-480. Спрошена часть N, а статья названа именем франшизы: её паспорт -
            # паспорт ПЕРВОЙ картины, и год у неё чужой. Имя латиницей годится (номер
            # части у него всё равно отрезан), год - нет, и догадкой это называется вслух.
            if not whole:
                whole = Origin(
                    title=latin,
                    name=_TAIL_RE.sub("", heading) if _CYRILLIC.search(heading) else "",
                    entity=str(json_map(article.get("pageprops")).get("wikibase_item") or ""),
                    guessed=True,
                )
            continue
        if (
            not trusted
            and not akin(title, heading, longer=not crowd)
            and not _same_latin(title, latin)
        ):
            if not shortened and _localized_short_name(title, heading, latin):
                shortened = Origin(
                    title=latin,
                    name=_TAIL_RE.sub("", heading),
                    entity=str(json_map(article.get("pageprops")).get("wikibase_item") or ""),
                    guessed=True,
                )
            continue
        found = Origin(
            title=latin,
            year=picture_year(extract),
            name=_TAIL_RE.sub("", heading) if _CYRILLIC.search(heading) else "",
            entity=str(json_map(article.get("pageprops")).get("wikibase_item") or ""),
            # 🔴 TC-567. Статья прочитана целиком, и чужого имени в ней не названо ни на
            # каком письме - вот это и есть отечественная картина. Пустой ``title`` сам по
            # себе того же не значит: иероглифы и кириллица другой страны дают ту же
            # пустоту (:func:`named_original`). Догадкам (``whole``, ``shortened``) признак
            # не достаётся вовсе: там и статья-то не про названную картину.
            native=not latin and not named_original(extract),
            namesake=namesake(pages, heading, picture_year(extract)),
        )
        if found:
            return found
    return shortened or whole


def _other_part(title: str, heading: str) -> bool:
    """Спрошена часть франшизы, а статья названа самой франшизой - то есть первой картиной.

    🔴 TC-480. Сверка заголовка (:func:`akin`) принимает запрос, который ПРОДОЛЖАЕТ имя
    статьи: «Властелин колец: Братство кольца» и статья «Властелин колец» - одна вещь,
    подзаголовок имени не меняет. Но ровно так же выглядит и номер части, а он меняет всё:
    на «трансформеры 3» отвечала статья «Трансформеры» и приносила паспорт первой картины
    2007 года вместо третьей 2011-го - причём паспорт ТВЁРДЫЙ, без всякой оговорки.

    Замер по корпусу (12 запросов с номером части): запасной путь справки отвечал не про
    ту часть в пяти, и во всех пяти это была первая картина франшизы с её годом -
    «История игрушек» 1995 вместо 2010, «Ледниковый период» 2002 вместо 2009,
    «Трансформеры» 2007 вместо 2011, «Стражи Галактики» 2014 вместо 2017, «Кунг-фу панда».

    Беззубым это выглядит только в номерном потоке: там год справки и так отбрасывается
    (:func:`~torrcast.usecases.discover._second_language._second_language`). А в потоке, где каталог
    объявил хвостовую цифру частью НАЗВАНИЯ, год справки - опора гейта, и опора эта чужая: ровно тот
    механизм подмены, который гейт обязан ловить.

    Отличается это от подзаголовка одним признаком, и он объявлен самим запросом: хвостовой номер
    части (:func:`~torrcast.domain.split_franchise_index.split_franchise_index`). Есть он, а
    заголовок - это голое имя франшизы без номера, значит спрошенной части статья не носит.
    """
    base, index = split_franchise_index(title)
    if index is None:
        return False
    name = slugify(heading.split(" (")[0])
    return bool(name) and name in {slugify(base), slugify(transliterate(base))}


def _localized_short_name(title: str, heading: str, latin: str) -> bool:
    """Прокатное имя длиннее заголовка на два коротких начальных слова.

    Так русская статья ``Незнакомцы`` находится по прокатному имени ``Все мы
    незнакомцы``: её оригинал ``All of Us Strangers`` подтверждает, что короткий
    заголовок не потерял слова картины. Одного совпавшего хвоста недостаточно - первый
    же кандидат поиска ``The Strangers`` был бы одноимённым фильмом 2008 года.

    Это по-прежнему догадка справки, поэтому найденный паспорт получает ``guessed`` и
    проходит обычный гейт второго захода, а не выдаётся за точное имя.
    """
    wanted = slugify(title).split("-")
    base = slugify(heading.split(" (")[0]).split("-")
    original = slugify(latin).split("-")
    return (
        len(wanted) == len(base) + 2
        and wanted[-len(base) :] == base
        and all(len(word) <= 3 for word in wanted[:2])
        and len(original) >= len(wanted)
    )


def _same_latin(title: str, latin: str) -> bool:
    """Спросили латиницей, и статья назвала ровно это же имя оригиналом - та самая картина."""
    wanted = slugify(title)
    return bool(wanted) and not _CYRILLIC.search(title) and slugify(latin) == wanted
