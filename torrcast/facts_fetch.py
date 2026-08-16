"""Чтение и кэш справки; публичный фасад — :mod:`torrcast.facts`."""

from __future__ import annotations

__all__ = [
    "BLURB_CAP",
    "FACTS_BUDGET",
    "HTTP_TIMEOUT",
    "TYPE_CHECKING",
    "Any",
    "Facts",
    "Path",
    "_about_cinema",
    "_article",
    "_cache_path",
    "_cached",
    "_cached_origin",
    "_crowded",
    "_ends_phrase",
    "_extract_params",
    "_fits_type",
    "_key",
    "_localized_short_name",
    "_origin_key",
    "_other_part",
    "_pages",
    "_ranked",
    "_read_cache",
    "_read_pages",
    "_remember",
    "_remember_origin",
    "_same_latin",
    "_search_params",
    "_write_cache",
    "akin",
    "english_title",
    "fetch",
    "json",
    "latin_title",
    "namesake",
    "picture_year",
    "ratings",
    "re",
    "read_origin",
    "read_sparql",
    "same_words",
    "sentence",
    "shorten",
    "slugify",
    "split_franchise_index",
    "state_path",
    "threading",
    "time",
    "transliterate",
    "wiki_extracts",
    "wikidata_ids",
]

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.facts_origin import (
        _ABBREV,
        _CINEMA_RE,
        _CJK,
        _CYRILLIC,
        _DEFAULT_CACHE_PATH,
        _EXBATCHES,
        _EXCHARS,
        _EXLIMIT,
        _FILM_WORD_RE,
        _GENRE_RE,
        _HATNOTE_RE,
        _LAST_WORD_RE,
        _MADE_RE,
        _ORIGINAL_RE,
        _SCREEN_RE,
        _SEARCH_HITS,
        _SENTENCE_START_RE,
        _SERIES_WORD_RE,
        _TAIL_RE,
        _TITLED_RE,
        _WIKI_HOST,
        _WIKI_PATH,
        _WIKIDATA_HOST,
        _WIKIDATA_PATH,
        _YEAR_RE,
        CACHE_PATH,
        EMPTY_TTL,
        RATINGS_PATH,
        TOPUP_LIMIT,
        Fact,
        Origin,
        confirms,
        get_json,
        hms,
        titles_for,
    )

import contextlib
import json
import re
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from torrcast.facts_origin import BLURB_CAP, FACTS_BUDGET, HTTP_TIMEOUT
from torrcast.parse import same_words, slugify, split_franchise_index, transliterate
from torrcast.state import state_path

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


def read_origin(
    pages: list[Any], title: str, trusted: bool = False, series: bool | None = None
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
    (:func:`_other_part`): такой паспорт отдаётся догадкой и без года.
    """
    crowd = _crowded(title, pages)
    shortened = Origin()
    whole = Origin()
    for page in pages:
        if page is None:
            continue
        heading = str(page.get("title") or "")
        extract = str(page.get("extract") or "")
        if not _about_cinema(heading, extract) or not _fits_type(series, heading, extract):
            continue
        latin = (
            latin_title(extract)
            or english_title(page)
            or ("" if _CYRILLIC.search(heading) else heading)
        )
        if _other_part(title, heading):
            # 🔴 TC-480. Спрошена часть N, а статья названа именем франшизы: её паспорт -
            # паспорт ПЕРВОЙ картины, и год у неё чужой. Имя латиницей годится (номер
            # части у него всё равно отрезан), год - нет, и догадкой это называется вслух.
            if not whole:
                whole = Origin(
                    title=latin,
                    name=_TAIL_RE.sub("", heading) if _CYRILLIC.search(heading) else "",
                    entity=str((page.get("pageprops") or {}).get("wikibase_item") or ""),
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
                    entity=str((page.get("pageprops") or {}).get("wikibase_item") or ""),
                    guessed=True,
                )
            continue
        found = Origin(
            title=latin,
            year=picture_year(extract),
            name=_TAIL_RE.sub("", heading) if _CYRILLIC.search(heading) else "",
            entity=str((page.get("pageprops") or {}).get("wikibase_item") or ""),
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
    (:func:`~torrcast.cli._second_language`). А в потоке, где каталог объявил хвостовую
    цифру частью НАЗВАНИЯ, год справки - опора гейта, и опора эта чужая: ровно тот
    механизм подмены, который гейт обязан ловить.

    Отличается это от подзаголовка одним признаком, и он объявлен самим запросом: хвостовой
    номер части (:func:`~torrcast.parse.split_franchise_index`). Есть он, а заголовок - это
    голое имя франшизы без номера, значит спрошенной части статья не носит.
    """
    base, index = split_franchise_index(title)
    if index is None:
        return False
    name = slugify(heading.split(" (")[0])
    return bool(name) and name in {slugify(base), slugify(transliterate(base))}


def namesake(pages: list[Any], heading: str, year: int | None) -> str:
    """Заголовок ДРУГОЙ картины того же года, которую справка знает под тем же именем.

    🔴 TC-371. Двусмысленность бывает не в отборе, а в самих источниках: именем «Девять» и
    годом 2009 в русском прокате подписаны две разные картины - мюзикл (``Nine``) и
    мультфильм (``9``). Каталог сводит их в одну кучку: имя и год - оба признака отбора - у
    них совпадают, а больше в раздачах не сказано ничего. Развести их разбором нечем, и
    молчать об этом нельзя: человек просит «девять», получает одну из двух, и объяснения
    нет ни строчки.

    Признак стоит ровно ноль: статьи уже приехали. Справка спрашивается сразу под всеми
    уточнениями (:data:`_QUALIFIERS`), «(мультфильм)» и «(фильм)» среди них, и обе картины
    лежат в одном ответе - остаётся их сосчитать.

    Ограждения два, и оба про то, чтобы строка не стала шумом:

    * год ОДИН И ТОТ ЖЕ. Одноимённых картин в справке полно («Дюна» 1984 и 2021, «Моана»
      2016 и 2026), но год их разводит, и разводит его же отбор - говорить не о чем;
    * статья ДРУГАЯ: тот же заголовок приезжает по нескольку раз, потому что под разными
      уточнениями лежит одно перенаправление.

    Про кино ли вторая статья, решает тот же гейт, что и для первой (:func:`_about_cinema`):
    у «Матрицы» под тем же именем лежит таблица, и картиной она не станет.
    """
    if year is None:
        return ""
    for page in pages:
        if page is None:
            continue
        other = str(page.get("title") or "")
        extract = str(page.get("extract") or "")
        if other == heading or not _about_cinema(other, extract):
            continue
        if picture_year(extract) == year:
            return other
    return ""


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


def _about_cinema(heading: str, extract: str) -> bool:
    """Про кино ли статья: либо назван киношный тип, либо экранный признак вместе с жанром.

    Гейт молчания: не пройдя его, статья не даст ни оригинала, ни года. Он же - главное
    ограждение справки, потому что оригинал вычитывается из первой скобки статьи
    (:func:`latin_title`), а такая скобка есть у кого угодно: у человека («англ. William
    Bradley Pitt»), у книги («англ. Dune» в статье о романе Герберта), у компании. Тихо
    подменить картину чужой строкой страшнее, чем промолчать, поэтому список типов -
    именно белый: чего в нём нет, того справка не знает.

    Второй путь нужен статьям, где тип записан описательно: «Во все тяжкие» открывается
    словами «американская телевизионная криминальная драма», и киношного слова там нет
    вовсе. Экранный признак и жанр требуются ОБА - поодиночке каждый врёт: «телевизионная
    сеть» это NBC, а «драма» бывает театральной.

    Третий путь - паспортная формула произведения, и заведён он ради неанглийской
    классики (TC-138). Статью о ней Википедия пишет без слова «фильм» в именительном:
    «Похитители велосипедов» (итал. Ladri di biciclette) - драма Витторио Де Сика 1948
    года»,  «Семь самураев» - «эпическая самурайская кинодрама ... в 1954 году». Первые
    два пути такую статью отвергали, справка молчала, и поиск уходил в индексер
    транслитом ``pokhititeli velosipedov`` - при живом ``Ladri di biciclette``.
    Требуются ВСЕ три приметы разом, и каждая отсекает свой класс чужих статей:

    * название в кавычках в начале фразы - так подписывают произведение, а не человека
      («Витторио Де Сика ... - итальянский кинорежиссёр» мимо, и это важно: у режиссёра
      в скобке своё имя латиницей, и справка выдала бы его за название картины);
    * жанр - роман, опера и пьеса своих жанров сюда не отдают («Дюна» - «роман»);
    * год выхода - у произведения он есть, у понятия и термина его нет.
    """
    text = f"{heading} {extract}"
    if _CINEMA_RE.search(text):
        return True
    if _SCREEN_RE.search(text) and _GENRE_RE.search(text):
        return True
    first = sentence(extract)
    return bool(_TITLED_RE.match(first) and _GENRE_RE.search(first) and _MADE_RE.search(first))


def picture_year(extract: str) -> int | None:
    """Год САМОЙ картины из статьи; не уверены - ``None``, и это честнее числа наугад.

    Год паспорта сильнее выдачи, поэтому ошибиться в нём - то же самое, что подменить
    картину. А брался он первым попавшимся «NNNN года» по всей первой врезке, и в статьях
    об экранизациях это через раз год СОСЕДА: у сериала «Фарго» 2014 года врезка второй
    фразой говорит «вдохновлён фильмом 1996 года», у «Дедвуд: Фильм» 2019 года - «по
    мотивам сериала 2006 года». Справка уверенно называла 1996 и 2006.

    Поэтому год ищется в два шага. Сначала - в первой фразе: там стоит паспортная формула
    («американский компьютерно-анимационный фильм 2006 года»), и она про эту картину, а не
    про соседа. Нет его там - годимся только на единогласие: когда во всей врезке год
    назван один-единственный, спутать его не с чем («Мастер и Маргарита (телесериал, 2005)»
    - только 2005). Названо несколько - выбирать между ними нечем, и мы молчим.
    """
    first = _YEAR_RE.search(sentence(extract))
    if first:
        return int(first.group(1))
    named = {match.group(1) for match in _YEAR_RE.finditer(extract)}
    return int(named.pop()) if len(named) == 1 else None


def _fits_type(series: bool | None, heading: str, extract: str) -> bool:
    """Того ли типа статья, что спросили: сериал против фильма.

    Гейт против худшего брака справки - молчаливой подмены картины её ЭКРАНИЗАЦИЕЙ.
    Тип картины у поиска есть, и он подсказывается (:func:`origin`), но одной подсказки
    мало: она только двигает кандидата с нужным уточнением в начало очереди
    (:func:`origin_now`), а не выкидывает чужие. Статьи «Атака титанов (телесериал)» в
    русской Википедии нет вовсе, и очередь спокойно доходила до «Атака титанов (фильм)» -
    японского игрового фильма 2015 года. Дальше не спасало ничто: статья про кино, гейт
    :func:`_about_cinema` её пропускал, заголовок под запрос подходил (:func:`akin` -
    «Атака титанов» слово в слово), а год ей никто не подсказывает. И поиск уходил
    добирать чужую картину с паспортом, который сильнее выдачи.

    Сверяется ОБЪЯВЛЕННЫЙ тип - тот, которым статья открывает первую фразу («японский
    художественный фильм», «американский телесериал-антология»), - и только по первой
    фразе с заголовком: дальше по тексту «фильм» и «сериал» стоят про соседей по
    франшизе, а не про саму картину.

    Отказ - только на ПРЯМОМ противоречии: статья назвала чужой тип и не назвала нужный.
    Молчание о типе отказом не считается, и это не поблажка, а необходимость: «Во все
    тяжкие» открывается словами «американская телевизионная криминальная драма» (ни
    «фильма», ни «сериала»), а «Блич» - «манга Тайто Кубо и её аниме-адаптации». Требуй
    мы явного слова, справка замолчала бы на картинах, которые сегодня знает.
    """
    if series is None:
        return True
    text = f"{heading} {sentence(extract)}"
    said_film = bool(_FILM_WORD_RE.search(text))
    said_series = bool(_SERIES_WORD_RE.search(text))
    asked, other = (said_series, said_film) if series else (said_film, said_series)
    return asked or not other


def _same_latin(title: str, latin: str) -> bool:
    """Спросили латиницей, и статья назвала ровно это же имя оригиналом - та самая картина."""
    wanted = slugify(title)
    return bool(wanted) and not _CYRILLIC.search(title) and slugify(latin) == wanted


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


def akin(title: str, heading: str, longer: bool = True) -> bool:
    """Про то же ли это, что спросили: заголовок статьи против запроса.

    Уточнение в скобках отбрасывается («Восхождение (фильм, 1976)» → «Восхождение»), а
    запрос сверяется и как есть, и латиницей: статья про «Кингсман» называется
    ``Kingsman``, и по-русски её заголовок не узнать.

    ⚠️ Сверяется НАЧАЛО имени, а не вхождение куда попало. «Ганнибал: Восхождение» тоже
    содержит слово «восхождение», и на вхождении справка уверенно выдавала его паспорт за
    паспорт фильма Шепитько - то есть ровно ту подмену, которую и должна ловить.

    Пробелы и знаки между словами картину не различают: статья про «ВандаВижн» называется
    «Ванда/Вижн», и одна косая черта делала имена чужими. Поэтому к трём сверкам добавлена
    четвёртая - точное равенство имён, у которых убраны все разделители. Именно точное:
    склей разделители у «начала имени», и «восхождение» совпало бы с «Ганнибалом».

    Пятая сверка - те же слова в другом порядке и другой форме (:func:`~torrcast.parse.same_words`):
    классику человек называет по памяти, и «Крики и шёпот» - это статья «Шёпоты и крики».

    ⚠️ ``longer`` запрещает шестую сверку - ту, где ДЛИННЕЕ заголовок статьи («Кингсман» →
    «Кингсман: Секретная служба»). Сверка нужная, но именно ею справка подменяла франшизу
    случайной частью: на голое «гарри поттер» ей подходили и «Орден Феникса», и
    «Принц-полукровка», и «узник Азкабана», а побеждал тот, кого выше поставил поиск.
    Выключает её :func:`_crowded` - там, где таких продолжений в выдаче несколько: одно
    продолжение это уточнение имени, а несколько - выбор части наугад.
    """
    base = slugify(heading.split(" (")[0])
    solid = base.replace("-", "")
    return bool(base) and any(
        want
        and (
            want == base
            or want.startswith(f"{base}-")
            or (longer and base.startswith(f"{want}-"))
            or want.replace("-", "") == solid
            or same_words(want, base)
        )
        for want in (slugify(title), slugify(transliterate(title)))
    )


def _crowded(title: str, pages: Iterable[Any]) -> bool:
    """Продолжают ли запрошенное имя сразу несколько статей выдачи.

    Так выглядит запрос голым именем франшизы: «гарри поттер» продолжают «Гарри Поттер и
    Орден Феникса», «...и Принц-полукровка», «...и узник Азкабана». Выбрать из них нечем -
    человек не называл части, - и любой выбор был бы молчаливой подменой картины. Значит
    годится только статья, названная РОВНО так же (сама франшиза), либо ничего.

    Одно продолжение - другое дело: «Кингсман» продолжает единственная статья «Кингсман:
    Секретная служба», и это не выбор, а уточнение имени.
    """
    wants = [want for want in (slugify(title), slugify(transliterate(title))) if want]
    seen = {
        base
        for page in pages
        if page is not None
        for base in (slugify(str(page.get("title") or "").split(" (")[0]),)
        if base and any(base.startswith(f"{want}-") for want in wants)
    }
    return len(seen) > 1


def latin_title(extract: str) -> str:
    """Оригинальное название из первой фразы статьи; нет латиницы — пустая строка.

    Русская Википедия открывает статью о зарубежном кино скобкой с языком оригинала:
    «Кингсман: Секретная служба» (англ. Kingsman: The Secret Service). Скобок в фразе
    бывает несколько, и не все они про название — «(род. 1950)» у режиссёра тоже скобка
    с сокращением, поэтому годится лишь та, внутри которой латиница и нет кириллицы.
    Хвост после запятой отрезается: там лежит дословный перевод, а не имя раздачи.

    ⚠️ Иероглифы отсекаются наравне с кириллицей. У японского кино скобка двуязычна -
    «(яп. 進撃の巨人 エンド オブ ザ ワールド Shingeki no Kyojin: Endo obu za Wārudo)», - и латиница
    в ней есть, так что прежняя проверка её принимала и отдавала поиску целиком, вместе с
    иероглифами. Искать по такой строке нечего. Пропустив скобку, имя берут из английской
    статьи (:func:`english_title`), где оно записано одним именем.
    """
    for match in _ORIGINAL_RE.finditer(extract):
        name = re.split(r"[,;]", match.group(1))[0].strip(" «»\"'")
        if _CJK.search(name):
            continue
        if re.search(r"[A-Za-z]", name) and not re.search(r"[А-Яа-яЁё]", name):
            return name
    return ""


def sentence(text: str) -> str:
    """Первая фраза статьи целиком — от начала до точки, которая её действительно кончает.

    Википедия открывает статью паспортом («американский компьютерно-анимационный
    спортивный комедийный фильм 2006 года, снятый студией Pixar для кинокомпании Walt
    Disney Pictures») — самодостаточным ответом на «про что кино». Ценность его именно
    в целости: обрубок «американский компьютерно-анимационный…» не говорит ни жанра,
    ни года, а дочитать его негде.

    Точка кончает фразу не всякая, и все три исключения взяты с живых статей:

    * **скобки и кавычки.** «(англ. Cars)» стоит в первой фразе почти каждой статьи о
      зарубежном кино, а у «Оппенгеймера» внутри «ёлочек» лежит название книги с точкой
      посередине («Оппенгеймер. Триумф и трагедия Американского Прометея»). Пока скобка
      или кавычка не закрыта, точка внутри — не граница;
    * **сокращения.** «реж.», «им.», «т. е.» — после них фраза продолжается;
    * **инициалы.** «Г. А. Потёмкина»: одна буква перед точкой словом не бывает.

    Плюс общее правило: за границей фразы идёт пробел и заглавная буква (или кавычка
    названия). «2001: A Space Odyssey» и «6.7» так не разрежешь.

    ⚠️ Перед первой фразой у статьи бывает строка-указатель («О сериале см. статью 7
    самураев.») - её отрезаем (:data:`_HATNOTE_RE`): это разводка одноимённого, а не
    паспорт картины, и читать её как первую фразу - значит приписать картине чужой тип.
    """
    flat = _HATNOTE_RE.sub("", re.sub(r"\s+", " ", text).strip())
    depth = 0
    for pos, char in enumerate(flat):
        if char in "([«“":
            depth += 1
        elif char in ")]»”":
            depth = max(depth - 1, 0)
        elif char in ".!?" and depth == 0 and _ends_phrase(flat, pos):
            return flat[: pos + 1]
    return flat


def _ends_phrase(flat: str, pos: int) -> bool:
    """Кончает ли точка (или «!», «?») на позиции ``pos`` первую фразу."""
    tail = flat[pos + 1 :]
    if tail and not tail.startswith(" "):
        return False  # «2001: A Space Odyssey», «6.7» - точка внутри слова
    word = _LAST_WORD_RE.search(flat[:pos])
    if word and (len(word.group(1)) == 1 or word.group(1).lower() in _ABBREV):
        return False  # «А. Тарковского», «англ.», «т. е.»
    return not tail.strip() or bool(_SENTENCE_START_RE.match(tail.strip()))


def shorten(extract: str, limit: int = BLURB_CAP) -> str:
    """Первая фраза статьи под потолок :data:`BLURB_CAP`; многоточие — только если не влезла.

    Ширина терминала тут ни при чём: фраза переносится по словам (:func:`~torrcast.cli.
    menu_lines`) и занимает столько строк, сколько ей нужно. Обрыв многоточием остаётся
    ровно для того случая, ради которого он и заводился — фраза длиннее всякого разумного.
    """
    first = sentence(extract)
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-—")
    return f"{cut}..." if cut else ""


def ratings(path: Path | None = None) -> dict[str, str]:
    """``tconst`` → рейтинг из выгрузки IMDb. Нет файла — пустой словарь, и это не сбой.

    Файл читается целиком один раз за запуск и только тогда, когда рейтинг кому-то
    понадобился: на пути показа его не трогают вовсе. С отсечкой по числу голосов,
    которую ставит `install.sh`, это ~2 МБ и сотня тысяч строк — чтение на глаз мгновенное.
    """
    out: dict[str, str] = {}
    try:
        with (path or RATINGS_PATH).open(encoding="utf-8") as handle:
            next(handle, None)  # шапка «tconst averageRating numVotes»
            for line in handle:
                parts = line.split("\t")
                if len(parts) >= 2:
                    out[parts[0]] = parts[1].strip()
    except OSError:
        return {}
    return out


class Facts:
    """Фоновый добор справки: :meth:`start` — и живи дальше, :meth:`get` — забери.

    Поток один на всю франшизу, а не по потоку на картину: оба источника отвечают
    пакетом, и четыре картины стоят ровно столько же, сколько одна.
    """

    def __init__(self, pictures: Iterable[tuple[str, int | None]], budget: float = FACTS_BUDGET):
        self.wanted = list(pictures)
        self.budget = budget
        self.found: dict[tuple[str, int | None], Fact] = {}
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._deadline = 0.0
        self._started = 0.0

    def start(self) -> None:
        """Пустить добор фоном. Ошибки внутри гасятся: справка не вправе ронять показ."""
        self._started = time.monotonic()
        self._deadline = time.monotonic() + self.budget
        if not self.wanted:
            self._done.set()
            return
        self.found = _cached(self.wanted)
        if len(self.found) == len(self.wanted):  # всё уже лежит в кэше - сети не надо
            self._done.set()
            return
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()

    def get(self, title: str, year: int | None) -> Fact:
        """Справка по картине; не приехала к :attr:`budget` — пустая, и меню печатается.

        Дедлайн один на всё меню, а не бюджет на строку: иначе франшиза из четырёх картин
        ждала бы молчащий источник вчетверо дольше обещанного.
        """
        self._done.wait(max(0.0, self._deadline - time.monotonic()))
        return self.found.get((title, year), Fact())

    def finish(self) -> None:
        """Дать добору дописать кэш - уже ПОСЛЕ меню, чтобы следующее было полным.

        Дедлайн отпускает МЕНЮ, а не поток: тот идёт дальше и кладёт найденное на диск.
        В живом показе это и так успевает - пока человек читает меню и отвечает, поток
        давно закончил, и здесь ждать нечего. А вот там, где ход обрывается сразу за меню
        (``--dry``, отказ «картин много, а терминала нет»), процесс уносил поток с собой:
        в кэш не попадало ничего, и следующий заход снова печатал голое меню.

        Ждём не с нуля, а остаток :data:`TOPUP_LIMIT` от старта: полторы секунды бюджета
        уже прошли, и на Ctrl-C это оставляет не задержку, а её хвостик.
        """
        thread = self._thread
        if thread is not None:
            thread.join(max(0.0, self._started + TOPUP_LIMIT - time.monotonic()))

    def _work(self) -> None:
        try:
            # Спрашиваем только ненайденное: лежащее в кэше уже полное, и переспрашивать
            # его - значит занимать его именами место в пакете (:func:`wiki_extracts`) и
            # рисковать записать поверх полной справки её обеднённый повтор.
            missing = [key for key in self.wanted if key not in self.found]
            fresh = fetch(missing, ready=self._ready)
            # Дописываем к тому, что уже лежало в кэше, а не заменяем: сеть отвечает только
            # про ненайденное, и присваиванием мы выбрасывали справку, которая у нас была.
            self.found = {**self.found, **fresh}
            # Пустой ответ тоже запоминаем - иначе поход за ним повторяется каждое меню.
            _remember(fresh, [key for key in missing if key not in fresh])
        except Exception:
            pass
        finally:
            self._done.set()

    def _ready(self, part: dict[tuple[str, int | None], Fact]) -> None:
        """Описания - в меню, не дожидаясь украшений (:func:`fetch`).

        🔴 TC-561. Меню и так ждёт свои полторы секунды - вопрос лишь в том, получает ли
        оно за них хоть что-нибудь. Описание приезжает первым шагом, рейтинг и хронометраж
        - вторым, вдвое более медленным; складывать их было незачем: пока ждали второй,
        пропадал и первый. Теперь дошедшее до дедлайна печатается, а опоздавшее дописывает
        кэш (:meth:`finish`) и достаётся следующему показу целиком.

        В кэш отсюда не пишем: на диск ложится итог, а не полуфабрикат - иначе описание
        без рейтинга закрыло бы дорогу полной справке на неделю вперёд. И уже добытое
        полуфабрикатом не накрываем: лежащее слева уступает тому, что уже есть.
        """
        self.found = {**part, **self.found}


def fetch(
    wanted: list[tuple[str, int | None]],
    timeout: float = HTTP_TIMEOUT,
    ready: Callable[[dict[tuple[str, int | None], Fact]], None] | None = None,
) -> dict[tuple[str, int | None], Fact]:
    """Собрать справку по картинам: Википедия → Wikidata → выгрузка рейтингов.

    Цепочка тут не вся: Wikidata спрашивают по идентификаторам из Википедии, и эти два
    запроса иначе как друг за другом не идут. А вот выгрузка рейтингов - файл на диске, с
    сетью не связанный ничем; читалась она третьим шагом, и её сотня тысяч строк ложилась
    на те же полторы секунды дедлайна, что и оба запроса. Теперь она читается ПОКА идёт
    первый запрос и к моменту нужды уже готова.

    🔴 TC-561. Два шага стоят разного и значат разное. Первый несёт то, ради чего справку
    и зовут, - о чём кино; второй лишь украшает его рейтингом и хронометражем. А платят
    они одинаково: замер по ста меню - Википедия 0.73 с, Wikidata 0.89 с в середине и
    1.5 с на девятом дециле, то есть в сумме мимо потолка в полторы секунды чаще, чем в
    него. Раньше опоздание или отказ ВТОРОГО шага отменяли ПЕРВЫЙ целиком: исключение
    улетало наверх, добытое описание пропадало вместе с ним, и в кэш не ложилось ничего -
    следующее меню шло за тем же самым заново и снова печаталось голым (38 прогонов из
    ста не сохранили ни строки).

    Теперь порядок соответствует цене: описания отдаются ``ready`` сразу, как приехали, -
    меню печатает их, не дожидаясь украшений. Отказ Wikidata гасится: справка выходит без
    рейтинга и хронометража, но с тем, что уже добыто, и ложится в кэш.
    """
    scores: dict[str, str] = {}

    def load() -> None:
        nonlocal scores
        scores = ratings()

    reader = threading.Thread(target=load, daemon=True)
    reader.start()
    about, entities = wiki_extracts(wanted, timeout)
    if ready is not None:
        ready({key: Fact(about=text) for key, text in about.items() if text})
    ids: dict[str, tuple[str, int]] = {}
    if entities:
        with contextlib.suppress(Exception):
            ids = wikidata_ids(sorted(set(entities.values())), timeout)
    reader.join(timeout)
    out: dict[tuple[str, int | None], Fact] = {}
    for key in wanted:
        imdb_id, minutes = ids.get(entities.get(key, ""), ("", 0))
        fact = Fact(
            about=about.get(key, ""),
            rating=f"IMDb {scores[imdb_id]}" if imdb_id in scores else "",
            runtime=hms(minutes),
        )
        if fact:
            out[key] = fact
    return out


def wiki_extracts(
    wanted: list[tuple[str, int | None]], timeout: float
) -> tuple[dict[tuple[str, int | None], str], dict[tuple[str, int | None], str]]:
    """Одним запросом: описания по-русски и Q-идентификаторы Wikidata для второго шага.

    Кандидатов на статью у картины около десятка (:func:`titles_for`), а в один запрос их
    влезает :data:`_EXLIMIT`. Побеждает первый кандидат, который оказался статьёй (не
    страницей значений, не пустышкой) и подтвердил год (:func:`confirms`).

    🔴 TC-561. Пока запрос был один, лишние кандидаты просто отбрасывались - и это стоило
    не времени, а самой справки: в меню из семи картин до Википедии доезжало по два-три
    имени из двенадцати, то есть без уточнения «(мультфильм)», под которым и лежит
    «Моана». Замер на корпусе из ста настоящих меню (503 картины): спрошенные по одной,
    статью имеют 49% картин, а пакетом из двадцати имён справку получали 14%.

    Поэтому имена режутся на пакеты по :data:`_EXLIMIT` и уезжают РАЗОМ (:data:`_EXBATCHES`
    штук): запросы ждут сеть, а не друг друга. Замер там же: один пакет 0.78 с, три
    очередью 2.14 с, три разом 0.83 с - втрое больше имён за семь сотых секунды.
    """
    candidates = {key: titles_for(*key) for key in wanted}
    names: list[str] = []
    room = _EXLIMIT * _EXBATCHES
    for depth in range(max((len(c) for c in candidates.values()), default=0)):
        for key in wanted:
            if depth < len(candidates[key]) and len(names) < room:
                names.append(candidates[key][depth])
    answers: list[Any] = []
    lock = threading.Lock()

    def ask(part: list[str]) -> None:
        with contextlib.suppress(Exception):
            payload = get_json(_WIKI_HOST, _WIKI_PATH, _extract_params(part), {}, timeout)
            with lock:
                answers.append(payload)

    parts = [names[at : at + _EXLIMIT] for at in range(0, len(names), _EXLIMIT)]
    deadline = time.monotonic() + timeout
    wave = [threading.Thread(target=ask, args=(part,), daemon=True) for part in parts]
    for thread in wave:
        thread.start()
    for thread in wave:
        thread.join(max(0.0, deadline - time.monotonic()))
    if not answers:
        # Ни один пакет не ответил - это отказ сети, а не «статьи нет». Разница дорогая:
        # пустой ответ лёг бы в кэш на неделю (:func:`_remember`) и накрыл бы картину,
        # про которую Википедия прекрасно знает.
        raise OSError("Википедия не ответила ни на один запрос")
    return _read_pages(_merged(answers), candidates)


def _merged(answers: list[Any]) -> dict[str, Any]:
    """Несколько ответов Википедии - в один: разбор кандидатов о пакетах знать не должен.

    Склеиваются ровно те три списка, которыми отвечает API: сами статьи и оба обратных
    пути имени - нормализация регистра и перенаправления (:func:`_pages`).
    """
    query: dict[str, list[Any]] = {"pages": [], "normalized": [], "redirects": []}
    for payload in answers:
        part = payload.get("query", {}) if isinstance(payload, dict) else {}
        for kind, rows in query.items():
            rows.extend(part.get(kind) or [])
    return {"query": query}


def _extract_params(names: list[str]) -> dict[str, str]:
    """Один запрос за первыми фразами сразу нескольких статей и их Q-идентификаторами."""
    return {
        "action": "query",
        "titles": "|".join(names[:_EXLIMIT]),
        "redirects": "1",
        # Ссылка на английскую статью едет тем же запросом и ничего не стоит, а имя за ней
        # - ровно то, которым картину подписывают индексеры. Русская статья про аниме
        # оригинал латиницей не пишет вовсе («Юная революционерка Утэна» - и японские
        # иероглифы в скобке), и без этой ссылки добирать было бы нечем.
        "prop": "extracts|pageprops|langlinks",
        "lllang": "en",
        # Потолок общий на все статьи запроса, а не на каждую: с ``1`` ссылка приезжала бы
        # только у первой из них, и повезло бы не тому кандидату.
        "lllimit": str(_EXLIMIT),
        "ppprop": "disambiguation|wikibase_item",
        "exintro": "1",
        "explaintext": "1",
        "exchars": str(_EXCHARS),
        "exlimit": str(_EXLIMIT),
        "format": "json",
        "formatversion": "2",
    }


def _read_pages(
    payload: Any, candidates: dict[tuple[str, int | None], list[str]]
) -> tuple[dict[tuple[str, int | None], str], dict[tuple[str, int | None], str]]:
    """Разобрать ответ Википедии: кандидат → статья → описание и Q-идентификатор.

    Запрошенное имя и заголовок статьи — не одно и то же: API нормализует регистр и ведёт
    по перенаправлениям, и «Моана (мультфильм)» вполне может ответить статьёй с другим
    заголовком. Обратный путь API отдаёт сам, списками ``normalized`` и ``redirects``.
    """
    hops, pages = _pages(payload)
    about: dict[tuple[str, int | None], str] = {}
    entities: dict[tuple[str, int | None], str] = {}
    for key, names in candidates.items():
        for name in names:
            page = _article(name, hops, pages)
            if page is None:
                continue
            extract = page.get("extract") or ""
            if not confirms(extract, key[1]):
                continue
            about[key] = extract
            props = page.get("pageprops") or {}
            if props.get("wikibase_item"):
                entities[key] = props["wikibase_item"]
            break
    return about, entities


def _search_params(query: str) -> dict[str, str]:
    """Тот же запрос, но статьи выбирает поиск Википедии, а не мы перебором имён."""
    return {
        **_extract_params([]),
        "titles": "",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": str(_SEARCH_HITS),
        "gsrnamespace": "0",
    }


def _ranked(payload: Any) -> list[Any]:
    """Найденные статьи в порядке выдачи поиска; страницы значений сюда не попадают."""
    _hops, pages = _pages(payload)
    out = [page for page in pages.values() if "disambiguation" not in (page.get("pageprops") or {})]
    return sorted(out, key=lambda page: int(page.get("index") or _SEARCH_HITS))


def _pages(payload: Any) -> tuple[dict[str, str], dict[str, Any]]:
    """Ответ Википедии → (обратный путь имён, статьи по заголовку)."""
    query = payload.get("query", {}) if isinstance(payload, dict) else {}
    hops: dict[str, str] = {}
    for kind in ("normalized", "redirects"):
        for hop in query.get(kind, []) or []:
            hops[hop.get("from", "")] = hop.get("to", "")
    return hops, {page.get("title", ""): page for page in query.get("pages", []) or []}


def _article(name: str, hops: dict[str, str], pages: dict[str, Any]) -> Any:
    """Статья по запрошенному имени; страница значений и пустышка статьёй не считаются."""
    seen = name
    for _ in range(3):  # нормализация, затем перенаправление; больше не бывает
        seen = hops.get(seen, seen)
    page = pages.get(seen)
    if not page or page.get("missing") or "disambiguation" in (page.get("pageprops") or {}):
        return None
    return page


def wikidata_ids(items: list[str], timeout: float) -> dict[str, tuple[str, int]]:
    """Q-идентификаторы → (идентификатор IMDb, минуты). Один запрос на все картины.

    Хронометраж берём здесь, а не из выгрузки IMDb, по цене вопроса: за ``title.basics``
    пришлось бы качать 225 МБ. Расхождение с IMDb бывает в пару минут — это разница в том,
    считать ли титры, а не выдумка.
    """
    values = " ".join(f"wd:{item}" for item in items)
    query = (
        f"SELECT ?item ?imdb ?dur WHERE {{ VALUES ?item {{ {values} }} "
        "OPTIONAL { ?item wdt:P345 ?imdb } OPTIONAL { ?item wdt:P2047 ?dur } }"
    )
    head = {"Accept": "application/sparql-results+json"}
    return read_sparql(get_json(_WIKIDATA_HOST, _WIKIDATA_PATH, {"query": query}, head, timeout))


def read_sparql(payload: Any) -> dict[str, tuple[str, int]]:
    """Ответ SPARQL → ``{Q-идентификатор: (tt…, минуты)}``; чего нет — того нет."""
    out: dict[str, tuple[str, int]] = {}
    if not isinstance(payload, dict):
        return {}
    rows = (payload.get("results", {}) or {}).get("bindings", [])
    for row in rows:
        item = row.get("item", {}).get("value", "").rsplit("/", 1)[-1]
        if not item.startswith("Q"):
            continue
        imdb = row.get("imdb", {}).get("value", "")
        raw = row.get("dur", {}).get("value", "")
        minutes = int(float(raw)) if re.fullmatch(r"\d+(\.\d+)?", raw) else 0
        out[item] = (imdb, minutes)
    return out


def _key(title: str, year: int | None) -> str:
    return f"{title}|{year if year is not None else ''}"


def _origin_key(title: str, series: bool | None) -> str:
    """Паспорта лежат в том же файле, что и справка, но в своём ряду ключей."""
    kind = "either" if series is None else "tv" if series else "movie"
    return f"origin|{kind}|{title}"


def _read_cache() -> dict[str, Any]:
    """Кэш с диска. Битый или отсутствующий — пустой: перечитаем из сети."""
    try:
        raw = json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_cache(raw: dict[str, Any]) -> None:
    """Дописать кэш. Не вышло записать — молчим: это не путь показа."""
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _cache_path() -> Path:
    """Кэш рядом с состоянием; явная подмена константы остаётся удобной для тестов."""
    if CACHE_PATH != _DEFAULT_CACHE_PATH:
        return CACHE_PATH
    return state_path().with_name("facts.json")


def _cached_origin(title: str, series: bool | None) -> Origin | None:
    """Что лежит в кэше. ``None`` — не спрашивали; пустой паспорт — спрашивали, нет его."""
    row = _read_cache().get(_origin_key(title, series))
    if not isinstance(row, dict):
        return None
    shown = row.get("year")
    return Origin(
        title=str(row.get("title", "")),
        year=shown if isinstance(shown, int) else None,
        name=str(row.get("name", "")),
        entity=str(row.get("entity", "")),
        guessed=bool(row.get("guessed")),
        namesake=str(row.get("namesake", "")),
        # Ряды, записанные до TC-450, отметки об источнике не носят: пустая строка честно
        # значит «неизвестно», и выдавать её за Википедию нельзя.
        source=str(row.get("source", "")),
    )


def _remember_origin(title: str, series: bool | None, found: Origin) -> None:
    raw = _read_cache()
    raw[_origin_key(title, series)] = {
        "title": found.title,
        "year": found.year,
        "name": found.name,
        # Q-идентификатор нужен на диске, иначе одинокий год (:func:`origin_either`) на
        # втором показе терял бы второй источник и ронял год, подтверждённый на первом.
        "entity": found.entity,
        # Отметка «имя лишь похоже» тоже нужна на диске: без неё гейт добора на втором
        # показе той же картины поверил бы догадке как доказанному имени.
        "guessed": found.guessed,
        # Тёзка того же года (TC-371) - тоже на диск: со второго показа справку не
        # спрашивают вовсе, и честная строка про двусмысленность иначе пропадала бы.
        "namesake": found.namesake,
        # 🔴 TC-450. ЧЕМ отвечено - на диск вместе с ответом, иначе сохранённый прогон
        # умеет сказать только «оригинал есть», а «его дала карта, а не Википедия» - уже
        # нет, и пользу карты нечем сосчитать. На показ поле не влияет.
        "source": found.source,
    }
    _write_cache(raw)


def _cached(wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
    """Что уже лежит на диске. Битый кэш — как пустой: перечитаем из сети.

    Ряд с отметкой ``empty`` — это записанное «справки нет»: картина отдаётся пустой, и в
    сеть за ней не идут. Отметка со сроком (:data:`EMPTY_TTL`): вышел — ряда как не было.
    """
    raw = _read_cache()
    out: dict[tuple[str, int | None], Fact] = {}
    for key in wanted:
        row = raw.get(_key(*key))
        if not isinstance(row, dict):
            continue
        blank = row.get("empty")
        if isinstance(blank, int | float) and time.time() - blank > EMPTY_TTL:
            continue
        fact = Fact(
            about=str(row.get("about", "")),
            rating=str(row.get("rating", "")),
            runtime=str(row.get("runtime", "")),
        )
        if not fact and not isinstance(blank, int | float):
            continue
        out[key] = fact
    return out


def _remember(
    found: dict[tuple[str, int | None], Fact],
    misses: Iterable[tuple[str, int | None]] = (),
) -> None:
    """Дописать итог в кэш. Не вышло записать — молчим: это не путь показа.

    ``misses`` — картины, про которые источник ответил, но сказать ему нечего. Раньше они
    в кэш не попадали вовсе, и каждое меню шло за ними в сеть заново: поход не успевал к
    дедлайну, меню печаталось голым, следующее — точно так же. Пустой ответ — тоже ответ,
    и он тоже помнится, только со сроком (:data:`EMPTY_TTL`).
    """
    blanks = list(misses)
    if not found and not blanks:
        return
    raw = _read_cache()
    for key, fact in found.items():
        raw[_key(*key)] = {"about": fact.about, "rating": fact.rating, "runtime": fact.runtime}
    now = int(time.time())
    for key in blanks:
        raw[_key(*key)] = {"about": "", "rating": "", "runtime": "", "empty": now}
    _write_cache(raw)
