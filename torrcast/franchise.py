"""Часть разбора имён; публичный фасад — :mod:`torrcast.parse`."""

from __future__ import annotations

__all__ = [
    "TYPE_CHECKING",
    "Callable",
    "Counter",
    "_alias_slugs",
    "_aliases",
    "_by_words",
    "_chapter_of",
    "_compose",
    "_continued",
    "_franchise_item_key",
    "_free_first",
    "_glued_year",
    "_group_weight",
    "_link",
    "_numbered_line",
    "_picture_season_span",
    "_run_span",
    "_sorted",
    "_unchaptered",
    "_word_list",
    "_words",
    "by_majority",
    "cluster",
    "franchises",
    "glue",
    "menu_order",
    "other_words",
    "outside_numbering",
    "re",
    "seasons_named",
]

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.parse_name import (
        _ALTERNATIVE_PICTURE_RE,
        _ALTERNATIVE_TITLE_RE,
        _CHAPTER_RE,
        _CYRILLIC,
        _PART_NUMBER_RE,
        _ROMAN,
        Kind,
        Picture,
        Release,
        _paired,
        franchise_key,
        in_digits,
        part_number,
        slugify,
    )


import re
from collections import Counter
from collections.abc import Callable


def cluster(releases: list[Release]) -> list[Picture]:
    """Сгруппировать релизы в картины; порядок = хронология франшизы.
    Кросс-язычность: если хоть где-то встретилось ``Тачки 3 / Cars 3``, то чисто
    латинский релиз ``Cars 3`` попадёт в тот же кластер, что и русский.

    🔴 Разбор идёт в порядке, который НЕ зависит от того, чей индексер ответил первым.
    Развязки ничьих в самих сортировках (TC-227) для этого мало: словарь синонимов и
    канон оригинала берут первую попавшуюся строку (``setdefault``), а каноническое имя
    картины считается большинством (:func:`_compose`) - и при равном счёте побеждает
    опять же тот, кто пришёл раньше. Замерено на сырых пулах (99 запросов, по 10
    перетасовок каждый): без этой строки перетасовка меняла картину у 59 запросов из 99,
    а верхний релиз картины С ТЕМ ЖЕ именем и годом - у 25. Живой случай - «Дюна» 2000:
    картина приезжала то на 5 раздач с верхом на 7 сидах, то на 2 раздачи с верхом на 39,
    и узнать об этом человеку было неоткуда.
    """
    releases = sorted(releases, key=lambda r: (r.magnet, r.raw_name))
    aliases: dict[str, str] = {}
    paired: dict[tuple[Kind, str, int | None], set[str]] = {}
    original_kinds: dict[tuple[str, int | None], set[Kind]] = {}
    for release in releases:
        if release.original and _CYRILLIC.search(release.title):
            original = slugify(release.original)
            title = slugify(release.title)
            aliases.setdefault(original, title)
            paired.setdefault((release.kind, title, release.year), set()).add(original)
            original_kinds.setdefault((original, release.year), set()).add(release.kind)
    series_originals = {
        release.slug for release in releases if not release.original and release.kind == "tv"
    }

    # Обычно ключ кластера - русский slug: так варианты перевода одного оригинала
    # сходятся через ``canon``. Исключение - каталог явно назвал под одним переводом и
    # годом несколько оригиналов: «Девять / Nine» и «Девять / 9» - разные картины.
    disputed = {
        key
        for key, originals in paired.items()
        if len(originals) > 1 and any(len(x) == 1 for x in originals)
    }
    canon: dict[tuple[Kind, str, int | None], tuple[Kind, str, int | None]] = {}
    buckets: dict[tuple[Kind, str, int | None], list[Release]] = {}
    for release in releases:
        kind = release.kind
        slug = release.slug if release.original else aliases.get(release.slug, release.slug)
        if (
            not release.original
            and release.slug in series_originals
            and len(kinds := original_kinds.get((release.slug, release.year), set())) == 1
        ):
            # Непомеченный латинский релиз наследует тип у парной строки каталога.
            kind = next(iter(kinds))
        key = (kind, slug, release.year)
        if release.original:
            original = slugify(release.original)
            if (release.kind, slugify(release.title), release.year) in disputed:
                key = (kind, original, release.year)
            else:
                key = canon.setdefault((kind, original, release.year), key)
        buckets.setdefault(key, []).append(release)

    pictures = [_compose(kind, year, group) for (kind, _, year), group in buckets.items()]
    return _sorted(_unchaptered(glue(pictures)))


def _chapter_of(title: str) -> tuple[str, int] | None:
    """Глава в имени: «Дары Смерти: Часть II» → ``("дары смерти", 2)``; не глава - None."""
    match = _PART_NUMBER_RE.match(title.strip())
    if not match:
        return None
    head = title[: match.start(1)].rstrip(" ,-")
    if not _CHAPTER_RE.search(head):
        return None
    base = slugify(_CHAPTER_RE.sub("", head).rstrip(" ,-:."))
    token = match.group(1).lower()
    number = int(token) if token.isdigit() else _ROMAN.get(token)
    return (base, number) if base and number is not None else None


def _unchaptered(pictures: list[Picture]) -> list[Picture]:
    """Снять номер части франшизы с ГЛАВ одной картины; сами картины не трогаются.

    🔴 TC-406. «Гарри Поттер и Дары Смерти: Часть I» и «Часть II» - половины одной
    работы, но их номера 1 и 2 в широком меню «гарри поттер» читались номерами частей
    ВСЕЙ франшизы: линейкой становились две главы, а восемь настоящих фильмов уезжали
    в хвост с подписью «без номера части» - франшиза без номеров выглядела
    нумерованной.

    Глава доказывается сиблингом: каталог назвал «Часть 1» того же имени - значит,
    работа делилась на главы, и номера в ней - номера глав. Без сиблинга номер
    остаётся номером части: «Стражи Галактики. Часть 2» - вторая часть франшизы
    (первый фильм каталог подписал просто «Стражи Галактики», делить её не на что), и
    запрос «стражи галактики 2» отвечает ею, как прежде. Тем же правилом живы «Оно:
    Глава 2» и «Дюна: Часть вторая» - слово тут не решает ничего, решает подпись
    каталога. Меряется по сохранённым выдачам: снятие номера с глав не стоит ни одного
    настоящего номерного ответа.

    Запрос к самой главенной работе это не ломает: «дары смерти 2» отвечает второй
    главой по хронологии - как всякая франшиза, которую каталог номерами не подписал.
    """
    chaptered = {
        chapter[0]
        for picture in pictures
        for release in picture.releases
        if (chapter := _chapter_of(release.title)) is not None and chapter[1] == 1
    }
    if not chaptered:
        return pictures
    for picture in pictures:
        if picture.part is None:
            continue
        for release in picture.releases:
            chapter = _chapter_of(release.title)
            if chapter is not None and chapter[0] in chaptered and chapter[1] == picture.part:
                picture.part = None
                break
    return pictures


def by_majority(counted: Counter[str]) -> str:
    """Самое частое имя кучки; при РАВНОМ счёте - самое короткое, потом по алфавиту.

    Развязка тут не косметика. ``most_common`` при равенстве отдаёт то имя, что легло в
    счётчик первым, то есть то, чей индексер ответил быстрее: «Армитаж: Двойная матрица»
    приезжает с оригиналом ``Armitage III: Dual Matrix`` и ``Armitage: Dual-Matrix``
    поровну, и картина меняла паспорт от запуска к запуску.

    Короткое имя при равенстве - не произвол: длиннее его делают ровно довески каталога,
    номер части в переводе названия («Матрица 2: Перезагрузка» против «Матрица:
    Перезагрузка») или лишняя нумерация оригинала. Номер части при этом не теряется -
    его забирает :attr:`Picture.part` отдельным счётом.
    """
    return min(counted, key=lambda name: (-counted[name], len(name), name))


def _compose(kind: Kind, year: int | None, group: list[Release], also: str = "") -> Picture:
    """Кучка релизов → картина: каноническое имя, оригинал и номер части по большинству."""
    titles = Counter(r.title for r in group if _CYRILLIC.search(r.title))
    title = by_majority(titles or Counter(r.title for r in group))
    originals = Counter(r.original for r in group if r.original)
    # Номер части часто есть лишь в части переводов («Матрица 2: Перезагрузка»)
    # - забираем его на всю картину, он точнее года при двух фильмах за год.
    parts = Counter(n for r in group if (n := part_number(r.title)) is not None)
    original = by_majority(originals) if originals else None
    return Picture(
        title=title,
        year=year,
        kind=kind,
        original=original,
        part=min(parts, key=lambda n: (-parts[n], n)) if parts else None,
        also=also,
        aliases=_alias_slugs(group, title, original),
        releases=group,
    )


def _alias_slugs(group: list[Release], title: str, original: str | None) -> tuple[str, ...]:
    """Псевдонимы кучки слагами: имена из заголовков минус те, что уже стали паспортом.

    Порядок отсортирован нарочно: разбор не вправе зависеть от того, чей индексер ответил
    первым (:func:`cluster`), а псевдонимы приезжают из разных строк выдачи.
    """
    known = {slugify(title), slugify(original or "")}
    found = {slug for r in group for name in r.aliases if (slug := slugify(name))}
    return tuple(sorted(found - known))


def _sorted(pictures: list[Picture]) -> list[Picture]:
    return sorted(pictures, key=lambda p: (p.year is None, p.year or 0, p.title, p.original or ""))


def glue(pictures: list[Picture]) -> list[Picture]:
    """Склеить картины, тождество которых ДОКАЗАНО именем и годом.

    Кластер разводит релизы по ключу «имя + год», и одна картина рассыпается на кучки
    ровно там, где каталог подписывает её по-разному. Живые примеры с домашних индексеров:

    * «Врата Штейна» (2011, русская озвучка, 86 сидов) и ``Steins;Gate`` (36 раздач, года
      в именах нет вовсе) - две картины, и запрос латиницей русской озвучки не видел В
      ПРИНЦИПЕ: пул латиницей богатый, второго захода не будет, а склеивать было нечем;
    * «Кавказская пленница, или Новые приключения Шурика» приезжает с годами 1966, 1967
      и 1969 - каталог путает год производства с годом проката, и 22 раздачи классики
      выглядят как три хилые картины.

    Доказательство тождества - только имя, названное самим каталогом: полное название
    картины или её оригинал (``Врата Штейна / Steins;Gate`` несёт оба). Франшиза здесь не
    годится: «Тачки 2» и «Тачки 3» - одна франшиза и разные картины, поэтому номер части
    из имени не режется. Одинаковых имён при разных типах не бывает: у аниме сериал и
    полнометражка подписаны одинаково, а картины это разные, - ``kind`` разделяет.

    🔴 TC-308. **Третье имя в заголовке - такое же имя каталога.** У картины бывает ДВА
    оригинала: международное название и родное. «Унесённые призраками» приезжают строками
    «Унесённые призраками / Sen to Chihiro no Kamikakushi / Spirited Away (2001)» - в
    паспорт попадает второе, а по третьему картину зовёт полмира, и именно им подписаны
    46 латинских раздач. Имена как строки не сходились, склеивать было нечем, и в меню
    стояли ДВЕ картины 2001 года: у одной японский оригинал и русский звук, у другой
    ``Spirited Away`` и звук английский. Спросишь по-русски - одна, спросишь латиницей -
    другая, и человек об этом ниоткуда не узнает. Признак дешёвый и офлайновый: оба имени
    стоят в именах самих раздач, разбор их уже читает (:func:`_alias_slugs`).

    ⚠️ **Третья подпись сводит только с ОДИНОКИМ именем** - тем, которое каталог не спарил
    ни с чем (``original`` пуст). Пара имён в заголовке - это уже сказанное каталогом «эта
    картина зовётся так и так», и третья подпись чужого заголовка её не отменяет: третьим
    там стоит что угодно вплоть до имени студии. Без этого условия замер по сотне
    сохранённых выдач давал ложные склейки ровно того сорта, ради которого заведён гейт
    года: «Стальной алхимик» 2003-го впитывал «Братство» 2009-го, а «Наруто: Ураганные
    хроники» - «Путь ниндзя». С условием на тех же выдачах меняются 6 запросов из 104, и
    все шесть - сведение одной картины: ``Spirited Away`` с «Унесёнными призраками»,
    ``Chainsaw Man The Movie Reze Arc`` с «Историей Резе» (плюс полсотни раздач, включая
    2160p), «Рэмбо» с «Первой кровью».

    Гейт года при этом прежний: «Унесённые призраками: движущиеся картинки» 2011 года
    несут оригиналом ровно ``Spirited Away`` и остаются отдельной картиной.

    🔴 **Год - гейт, а не украшение.** Ремейк носит имя оригинала («Психо» 1960 и 1998),
    и склеить их значило бы молча подсунуть человеку чужой фильм. Поэтому:

    * годы расходятся больше чем на 1 - НЕ склеиваем (±1 - это разница между годом
      производства и годом проката, её раздачи путают постоянно);
    * год не назван вовсе - склеиваем с единственным известным годом под этим именем, но
      если под ним лежат ДВЕ картины разных лет, безымянная не достаётся никому: выбирать
      наугад между оригиналом и ремейком нельзя.
    """
    parent = list(range(len(pictures)))

    def identity(name: str) -> str:
        """Имя картины без подписи формата показа в его хвосте."""
        plain = re.sub(r"(?:-)?(?:в-)?3[дd]$", "", slugify(name)).rstrip("-")
        return re.sub(
            r"(?<=-)(?:часть|part)-([ivx]{1,4})$",
            lambda match: (
                match.group(0)[: match.group(0).rfind("-") + 1]
                + str(_ROMAN.get(match.group(1), match.group(1)))
            ),
            plain,
        )

    def alternative_release(release: Release) -> bool:
        title = release.raw_name.split(" / ", 1)[0]
        return bool(
            _ALTERNATIVE_PICTURE_RE.search(release.raw_name) or _ALTERNATIVE_TITLE_RE.search(title)
        )

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    alternative = [
        bool(p.releases) and all(alternative_release(r) for r in p.releases) for p in pictures
    ]
    disputed = {
        (picture.kind, slugify(picture.title), picture.year)
        for picture in pictures
        if picture.original
        and len(
            {
                slugify(other.original)
                for other in pictures
                if other.original
                and other.kind == picture.kind
                and other.year == picture.year
                and slugify(other.title) == slugify(picture.title)
            }
        )
        > 1
        and any(
            len(slugify(other.original)) == 1
            for other in pictures
            if other.original
            and other.kind == picture.kind
            and other.year == picture.year
            and slugify(other.title) == slugify(picture.title)
        )
    }
    named: dict[tuple[Kind, str, bool], list[int]] = {}
    for i, picture in enumerate(pictures):
        title = identity(picture.title)
        contested = (picture.kind, title, picture.year) in disputed
        names = set() if contested else {title}
        if picture.original:
            names.add(identity(picture.original))
        # Число словом и число цифрой - одно имя (:func:`in_digits`). Гейт года при этом
        # остаётся прежним, так что «12 обезьян» 1995-го с сериалом 2015-го не сшить.
        if not contested:
            names |= {in_digits(name) for name in names if name}
        for name in names:
            if name:
                named.setdefault((picture.kind, name, alternative[i]), []).append(i)
    for same in named.values():
        _link(pictures, same, union)
    # Третье имя из заголовка (:attr:`Picture.aliases`) сводит картину только с ОДИНОКИМ
    # именем - тем, которое каталог не спарил ни с чем (``original`` пуст).
    lone: dict[tuple[Kind, str, bool], list[int]] = {}
    for i, picture in enumerate(pictures):
        if picture.original:
            continue
        for name in {(slug := identity(picture.title)), in_digits(slug)}:
            if name:
                lone.setdefault((picture.kind, name, alternative[i]), []).append(i)
    for i, picture in enumerate(pictures):
        for alias in picture.aliases:
            for name in (alias, in_digits(alias)):
                if (
                    bucket := lone.get((picture.kind, name, alternative[i]))
                ) is not None and i not in bucket:
                    bucket.append(i)
    for same in lone.values():
        _link(pictures, same, union)

    groups: dict[int, list[int]] = {}
    for i in range(len(pictures)):
        groups.setdefault(root(i), []).append(i)
    out: list[Picture] = []
    for members in groups.values():
        if len(members) == 1:
            out.append(pictures[members[0]])
            continue
        merged = sorted(
            (pictures[i] for i in members),
            key=lambda p: (-len(p.releases), p.title, p.original or ""),
        )
        releases = [r for p in merged for r in p.releases]
        year = _glued_year(merged[0].kind, merged, releases)
        fresh = _compose(merged[0].kind, year, releases)
        # Второе имя - самое многолюдное из тех, что не стали каноническим: именно его
        # человек и набрал, если спрашивал латиницей, а в меню теперь русское название.
        fresh.also = next((p.title for p in merged if slugify(p.title) != slugify(fresh.title)), "")
        out.append(fresh)
    return out


def _glued_year(kind: Kind, merged: list[Picture], releases: list[Release]) -> int | None:
    """Год склеенной картины: у кино - по большинству раздач, у сериала - самый ранний.

    🔴 TC-201. **У сериала год - самый РАННИЙ из известных**, а не год самой толстой кучки.
    Со сшивкой сезонов кучки разъезжаются на десятилетия, и сериал подписывался годом
    самого обсиженного сезона: «Доктор Кто (2017)» при 12 раздачах 2005-го против 90
    раздач 2017-го, «Игра престолов (2019)», «Чёрное зеркало (2019)». Это не только кривая
    строка в меню: справку ищут по паре «имя + год» и сверяют год по первым фразам статьи
    (:func:`torrcast.facts.confirms`), а статья открывается годом НАЧАЛА сериала. С чужим
    годом справки нет вовсе - ни рейтинга, ни описания, ни хронометража, на котором
    считается битрейт (TC-185).

    🔴 TC-328. **У кино ранний год - не начало, а описка каталога**, и правило сериала на
    него не переносится. Гейт года (:func:`_link`) сводит в одну картину только соседние
    годы, так что спорят тут не оригинал с ремейком, а год производства с годом проката:
    «Титаник» стоял в меню как «Титаник (1996)» из-за трёх раздач из 68, подписанных
    1996-м. Год человек читает глазами, чтобы отличить оригинал от ремейка, - это наш же
    приём против подмены картины, и врущий год подрывает ровно тот признак, на который мы
    его учим смотреть. Слово за большинством раздач; при равном счёте - за ранним годом,
    то есть за прежним ответом.

    Считается по РАЗДАЧАМ, а не по кучкам: кучка тут - не голос, а лишь то, как каталог
    разложил одинаковые имена, и одна раздача с опиской весит там столько же, сколько
    шесть десятков без неё.
    """
    dated = [r.year for r in releases if r.year is not None]
    if kind != "tv" and dated:
        counted = Counter(dated)
        return min(counted, key=lambda year: (-counted[year], year))
    return min((p.year for p in merged if p.year is not None), default=None)


def _run_span(picture: Picture) -> tuple[int, int] | None:
    """Сквозной отрезок серий картины: ``[01-201]`` → (1, 201). Нет такого имени - None.

    Считаются только раздачи со СКВОЗНОЙ нумерацией - те, что перечислили серии, но не
    назвали сезона. Раздача, назвавшая сезон, нумерует серии внутри него и к общей линейке
    сериала отношения не имеет.
    """
    numbers = [
        n
        for r in picture.releases
        if r.episodes and not r.seasons and r.season is None
        for n in (r.episodes[0], r.episodes[-1])
    ]
    return (min(numbers), max(numbers)) if numbers else None


def _picture_season_span(picture: Picture) -> tuple[int, int] | None:
    """Сквозной отрезок сезонов картины. Нет таких имён - None."""
    numbers = [
        s
        for r in picture.releases
        for s in (r.seasons or ([r.season] if r.season is not None else []))
    ]
    return (min(numbers), max(numbers)) if numbers else None


def _continued(
    pictures: list[Picture], chains: list[list[int]], union: Callable[[int, int], None]
) -> list[list[int]]:
    """Сшить цепочки лет, которые ПРОДОЛЖАЮТ нумерацию серий, а не начинают её заново.

    🔴 TC-169, точечное послабление гейта года - и только для сериалов со сквозной
    нумерацией (:func:`_run_span`). Длинное аниме идёт по каталогу кусками, у каждого
    свой год, а серии считаются насквозь через весь сериал: «Гинтама / Gintama TV-1
    [01-201] (2006)», «TV-2 [202-252] (2011)», ... «TV-8 [354-367] (2018)». Между
    крайними кусками 12 лет, гейт года читал это как ремейк - и сериал рассыпался на
    шесть картин, из которых у той, где лежит ПЕРВАЯ серия, оставалось две раздачи.

    Гейт при этом не ослаблен: ремейк тем и ремейк, что начинает счёт заново, и его
    диапазон стартует с первой серии. Сшиваем, только когда поздний кусок:

    * начинается НЕ с первой серии/сезона - счёт не начат заново;
    * начинается там, где кончился ранний (с зазором не больше одной серии/сезона, а
      пересечение допустимо: сборник «TV [01-252]» перекрывает куски внутри себя).

    Обе стороны обязаны назвать свои серии/сезоны сами. Молчит хоть одна - сшивать
    нечем, и работает прежний гейт года.
    """
    if len(chains) < 2 or any(pictures[i].kind != "tv" for chain in chains for i in chain):
        return chains
    out: list[list[int]] = [chains[0]]
    for chain in chains[1:]:
        before_ep = [span for i in out[-1] if (span := _run_span(pictures[i]))]
        after_ep = [span for i in chain if (span := _run_span(pictures[i]))]
        start_ep = min((s for s, _ in after_ep), default=0)

        before_s = [span for i in out[-1] if (span := _picture_season_span(pictures[i]))]
        after_s = [span for i in chain if (span := _picture_season_span(pictures[i]))]
        start_s = min((s for s, _ in after_s), default=0)

        # Сшивает ЛЮБАЯ из двух линеек: сквозная нумерация серий (аниме) или нумерация
        # сезонов (длинный сериал, у которого каждый сезон датирован своим годом).
        if (before_ep and start_ep > 1 and start_ep <= max(e for _, e in before_ep) + 1) or (
            before_s and start_s > 1 and start_s <= max(e for _, e in before_s) + 1
        ):
            union(out[-1][0], chain[0])
            out[-1] = out[-1] + chain
            continue
        out.append(chain)
    return out


def _link(pictures: list[Picture], same: list[int], union: Callable[[int, int], None]) -> None:
    """Связать картины, приехавшие под одним именем: сначала по годам, потом безымянные.

    Годы выстраиваются в цепочки шагом не больше единицы: 1966 и 1967 - одна картина,
    1967 и 1969 - уже нет. Картина без года достаётся цепочке, только если она под этим
    именем одна: две цепочки - это оригинал и ремейк, и молча выбрать между ними нельзя.
    """
    dated = sorted(
        (i for i in same if pictures[i].year is not None),
        key=lambda i: (pictures[i].year or 0, pictures[i].title, pictures[i].original or ""),
    )
    chains: list[list[int]] = []
    for i in dated:
        current = pictures[i]
        year = current.year or 0
        previous = pictures[chains[-1][-1]] if chains else None
        close_outlier = False
        if previous is not None and previous.original and current.original:
            close_outlier = (
                year - (previous.year or 0) == 2
                and len(previous.releases) == 1
                and len(current.releases) >= 10
                and slugify(previous.original) == slugify(current.original)
            )
        if previous is not None and (year - (previous.year or 0) <= 1 or close_outlier):
            chains[-1].append(i)
        else:
            chains.append([i])
    for chain in chains:
        for i in chain[1:]:
            union(chain[0], i)
    chains = _continued(pictures, chains, union)
    blank = [i for i in same if pictures[i].year is None]
    if len(chains) > 1:  # оригинал и ремейк под одним именем: безымянной картине веры нет
        return
    for i in blank[1:]:
        union(blank[0], i)
    if chains and blank:
        union(chains[0][0], blank[0])


def seasons_named(picture: Picture) -> tuple[int, ...]:
    """Сезоны, которые раздачи картины назвали САМИ, по возрастанию; пусто - все молчат.

    Нужна одной честной строке. Сериал попадает в меню целой картиной, а план строится
    только по тем раздачам, чьё имя накрывает спрошенный сезон (:meth:`Release.covers`).
    Не накрыл никто - картина исчезала из меню молча, и человек читал дефолт, вставший
    на соседа. Живой промах: «Гинтама» (2018) переживает привязку с 41 раздачей и 33
    живыми, но все они подписаны сезонами 5-10, первого нет ни в одной, - и на `s1e1`
    дефолтом вставал спин-офф «Gintama: 3-nen Z-gumi Ginpachi-sensei», ни словом не
    объяснив, куда делся основной сериал.

    ⚠️ Это то, что сказало ИМЯ, а не то, что лежит в раздаче. Молчащие о сезоне раздачи
    сюда не попадают вовсе: они накрывают любой сезон (окончательный ответ дают файлы), и
    называть их сезон было бы выдумкой. Поэтому пустой ответ значит «имена молчат», а не
    «сезонов нет», и строка на нём не строится.
    """
    named = {s for r in picture.releases for s in (r.seasons or ((r.season,) if r.season else ()))}
    return tuple(sorted(named))


def franchises(pictures: list[Picture]) -> dict[str, list[Picture]]:
    """Картины → франшизы: общий канонический ключ, значение отсортировано по году.
    Два фильма за один год («Перезагрузка» и «Революция», обе 2003) разводит явный
    номер части; без него вперёд идёт картина с бо́льшим числом раздач — основной
    фильм, а не спин-офф или «киноляпы».
    """
    grouped: dict[str, list[Picture]] = {}
    for picture in pictures:
        grouped.setdefault(picture.franchise, []).append(picture)
    for items in grouped.values():
        items.sort(key=_franchise_item_key)
    return grouped


def _franchise_item_key(picture: Picture) -> tuple[bool, int, int, int, str]:
    """Порядок частей франшизы: год, названный номер, вес и имя."""
    return (
        picture.year is None,
        picture.year or 0,
        picture.part or 99,
        -len(picture.releases),
        picture.title,
    )


def _numbered_line(pictures: list[Picture]) -> tuple[list[Picture], list[Picture]]:
    """Франшиза → (основная линейка по номерам частей, всё остальное после неё).

    Каталог нумерует не всё: у «Тачек» номер стоит на второй и третьей части, а первая
    подписана просто «Тачки» - как и спин-офф «Тачки: Мультачки. Байки Мэтра» двумя
    годами позже. По хронологии спин-офф оказывался между первой и второй частью, и в
    меню выходило «2. Мультачки, 3. Тачки 2»: номер пункта не совпадал с номером части,
    хотя человек читает его именно так и именно им отвечает.

    Правило простое и держится на том, что каталог сказал вслух:

    * у кого номер части есть - те и есть линейка, по возрастанию номера;
    * первое место линейки свободно (номера ``1`` никто не назвал) - его занимает первая
      часть, которую каталог просто не с чем было нумеровать (:func:`_free_first`), и
      только если её с франшизой связала сама подпись каталога;
    * остальные безномерные идут ПОСЛЕ линейки, в хронологии.

    🔴 Не-видео (``kind == "other"``) места в линейке не занимает, даже когда в его имени
    есть номер: том аудиокниги «Homo Ludens 1. Класс: Сталкер» вставал ПЕРВЫМ пунктом
    меню кинофраншизы «Сталкер» - единственным носителем номера во всей выдаче - и мог
    быть принят за первую часть фильма. Здесь это ограждение обязано стоять само, а не
    полагаться на фильтр в :func:`_numbered`: сюда линейку приносят и
    :func:`menu_order`, и :func:`outside_numbering`, а они зовут её на всём меню целиком.
    Из хвоста не-видео при этом не исчезает: показать его - честно, давать ему номер
    части - нет.

    ⚠️ Нумерованных частей нет вовсе («Матрица», «Гарри Поттер») - картины остаются
    в хронологии, а не-видео уходит после них.
    """
    numbered = sorted(
        (p for p in pictures if p.part is not None and p.kind != "other"),
        key=lambda p: (p.part or 0, p.year is None, p.year or 0, p.title),
    )
    if not numbered:
        return sorted(pictures, key=lambda p: p.kind == "other"), []
    rest = [p for p in pictures if p.part is None or p.kind == "other"]
    free = _free_first(rest, numbered) if rest and all(p.part != 1 for p in numbered) else None
    first = [free] if free is not None else []
    tail = [p for p in rest if p is not free]
    return first + numbered, tail


def _free_first(rest: list[Picture], numbered: list[Picture]) -> Picture | None:
    """Кто из безномерных занимает свободное первое место линейки; ``None`` - некому.

    🔴 TC-373. Претендент обязан быть связан с франшизой ПОДПИСЬЮ КАТАЛОГА, а не одним
    «раньше всех вышел»: либо он назван ровно именем франшизы («Форсаж» 2001, «Оно»,
    «Ледниковый период»), либо его оригинал делит корень с оригиналом нумерованной части
    («Властелин колец: Братство кольца» делит ``The Lord of the Rings`` с «Битвой за
    Средиземье 2»). Прежде место доставалось любой ранней безномерной, и на запрос
    «тачки 1» при пропавшей из выдачи первой части отвечал спин-офф «Тачки: Мультачки.
    Байки Мэтра» - другая картина той же франшизы (корень её оригинала ``Cars Toon``
    свой, а не ``Cars``), молча вставшая на место просимой.

    🔴 TC-361. Прежде место отдавалось самой ранней безномерной по хронологии, и на
    «форсаж 1» отвечал «Форсаж» 1992 года - однофамилец с оригиналом ``Afterburn``, одной
    раздачей и четырьмя сидами, - тогда как «Форсаж» 2001 года (``The Fast and the
    Furious``, 13 раздач, 56 сидов) стоял в стороне с подписью «без номера части». Имя
    франшизы плюс номер первой части - самый простой запрос из возможных, и отвечать на
    него однофамильцем нельзя. Тот же класс в сохранённых выдачах: «Ледниковый период:
    выжившие» (1 раздача) вместо «Ледникового периода» (7), «Оно» с оригиналом ``It
    Follows`` вместо «Оно» с оригиналом ``It``, «Человек Паук» 1967 года (1 раздача)
    вместо «Человека-паука» 2002-го (7).

    Правило сужено, а не выключено - место занимает картина, которая:

    * вышла РАНЬШЕ первой части, подписанной номером и годом. Первой частью может быть
      только то, что стоит перед нумерацией: иначе место забрал бы поздний спин-офф с
      богатой кучкой («Дэдпул и Росомаха», 59 раздач, против «Дэдпула», 15);
    * полнее прочих таких же КУЧКОЙ - тем же весом, каким франшиза разводит две картины
      одного года (:func:`franchises`) и каким живая часть перевешивает безгодового
      носителя номера (:func:`_living_part`). Число раздач - мера каталога, а не роя:
      сиды у одной и той же картины гуляют от прогона к прогону, и порог по ним отдал бы
      первое место «Тачек» спин-оффу «Мультачки» - на сохранённой выдаче у первой части
      4 сида, у спин-оффа 5.

    Кучки равны - остаётся ранняя, как и было. Сборник претендентом не бывает
    (:attr:`Picture.collection`): за ним пачка картин, а не картина.

    ⚠️ Раньше нумерации не вышло НИЧЕГО (или номера каталог назвал без года) - мерить не
    от чего, и место занимает самая ранняя безномерная, как прежде. Честный ответ тут
    только такой: линейка без первой части - это то, что сказал каталог.
    """
    roots = {franchise_key(p.original) for p in numbered if p.original}
    titled = [
        p
        for p in rest
        if p.kind != "other"  # первое место - картине, а не тому книги или репаку игры
        and (
            slugify(p.title) == p.franchise
            or (p.original is not None and franchise_key(p.original) in roots)
        )
    ]
    if not titled:
        return None
    anchor = min((p.year for p in numbered if p.year is not None), default=None)
    if anchor is None:
        return titled[0]
    early = [p for p in titled if p.year is not None and p.year < anchor and not p.collection]
    if not early:
        return titled[0]
    return max(early, key=lambda p: (len(p.releases), -(p.year or 0)))


def menu_order(pictures: list[Picture]) -> list[Picture]:
    """Меню франшизы: что в нём стоит и в каком порядке (номер пункта = номер части).

    🔴 TC-327. Сборник в меню не пункт. Раздача «Хоббит: Трилогия», «Гарри Поттер:
    Коллекция», «Хоббит / Властелин колец: Коллекция ... (2001-2014)» обрезается по слову
    про сборник до имени франшизы и заводит в каталоге картину, которой нет: в меню по
    «хоббит» стояло «Хоббит (2001)» одной раздачей на 165 ГБ - две трилогии сразу. Диапазон
    лет схлопывается в первый год, так что гейт года такое не разводит, а человек читает
    строку меню как картину и выбирает её.

    Убирается ПУНКТ МЕНЮ, а не раздача: сборник остаётся в каталоге, и там, где он и есть
    картина (сезон-пак сериала лежит в одной кучке с остальными раздачами сезона), его
    ничто не трогает - словом про сборник подписывают пачку ФИЛЬМОВ, а не сезоны
    (:attr:`Picture.collection`).

    ⚠️ Кроме сборников в меню не нашлось ничего - показываем их: выбирать всё равно не из
    чего, а пустое меню значит «ничего не нашлось» при живой выдаче в руках.
    """
    picked = [p for p in pictures if not p.collection]
    source = picked or list(pictures)
    keys = {p.franchise for p in source}
    if any(sum(other.startswith(f"{key}-и-") for other in keys) >= 2 for key in keys):
        return sorted(source, key=_franchise_item_key)
    line, tail = _numbered_line(source)
    return line + tail


def outside_numbering(pictures: list[Picture]) -> set[str]:
    """Ключи картин, стоящих ПОСЛЕ нумерованной линейки, - им и подписи в меню.

    Подпись честная - «без номера части», а не «спин-офф»: номер части каталог для них
    действительно не назвал, а вот спин-офф ли это, мы не знаем. У «Форсажа» безномерными
    подписаны «Двойной форсаж» и «Тройной форсаж» - это ровно основная линейка, и назвать
    их спин-оффами значило бы соврать в строке, которую человек не может проверить.
    """
    return {p.key for p in _numbered_line(pictures)[1]}


def _group_weight(groups: dict[str, list[Picture]], key: str) -> int:
    """Число раздач за ключом франшизы - вес не зависит от порядка выдачи."""
    return sum(len(p.releases) for p in groups[key])


def _by_words(wanted: str, groups: dict[str, list[Picture]]) -> str | None:
    """Ключ франшизы, в словах которого есть ВСЕ слова запроса - в любом порядке.

    Человек называет картину своими словами, а не так, как её подписал каталог:
    «бульвар сансет» вместо «Сансет бульвар», «гарри поттер дары смерти» вместо «Гарри
    Поттер И Дары Смерти». Подстрокой такое не ловится ни в одну сторону, и запрос
    падает в пустоту при живых раздачах прямо в той же выдаче.

    Сверяются слова, а не буквы, и целиком: «дети мужчин» не станет «Мужчины, женщины и
    дети» - слова «мужчин» там нет, есть «мужчины». Именно это и держит проверку узкой.

    Однобуквенные слова из запроса выбрасываются: союзы («и», «в») ставят и не ставят как
    попало, а решают совпадение всё равно не они. Слов должно остаться хотя бы два -
    одно слово, если оно в каталоге есть, находится обычной подстрокой.

    Из подошедших берётся самый тесный ключ: у «гарри поттер дары смерти» это
    ``гарри-поттер-и-дары-смерти``, а не ``гарри-поттер-и-дары-смерти-в-3д``.

    🔴 Вторым заходом слова сверяются ПО ФОРМЕ (:func:`same_words`): «Робот мечты» - это
    «Мечты робота», а буква в букву эти имена не сходятся ни одним из способов выше, и
    запрос падал в пустоту при восьми строках выдачи. Заход именно второй, а не общее
    послабление: пока слова совпадают целиком, всё решает первый, и ключ, найденный им,
    сильнее любой догадки об окончании.

    Дороги подмене это не открывает, и держат её два условия сразу (:func:`_paired`):
    слов должно быть ПОРОВНУ, и окончание прощается только слову, которое ПЕРЕЕХАЛО.
    «Дети мужчин» так и не станут «Мужчинами, женщинами и детьми» - слов там больше, - а
    «кольца власти» не станут «Кольцом власти»: там разница в окончании стоит на месте.
    """
    asked = _words(wanted)
    if len(asked) < 2:
        return None
    hits = [key for key in groups if asked <= _words(key)]
    if not hits:
        # Порядок слов тут значит всё (:func:`_paired`), поэтому сверяются списки в том
        # виде, как имя написано, а не множества.
        mine = _word_list(wanted)
        hits = [key for key in groups if _paired(mine, _word_list(key))]
    return (
        min(
            hits,
            key=lambda key: (len(_words(key)), len(key), -_group_weight(groups, key), key),
        )
        if hits
        else None
    )


def _words(slug: str) -> set[str]:
    return set(_word_list(slug))


def _word_list(slug: str) -> list[str]:
    """Слова имени по порядку, без односложных союзов («и», «в»): их ставят как попало."""
    return [word for word in slug.split("-") if len(word) > 1]


def other_words(query: str, picture: Picture | None) -> str:
    """Название картины, в которое запрос попал ТОЛЬКО другими словами - иначе пусто.

    Нужна одной честной строке: человек набрал «бульвар сансет», а играет «Сансет
    бульвар» - об этом надо сказать. Совпадение подстрокой (в любую сторону) и попадание
    по оригинальному названию молчаливы: там человек назвал картину ровно так, как её
    зовут, и объяснять нечего.

    ⚠️ Называется КАРТИНА целиком, а не корень её франшизы. Корень режет подзаголовок
    (:func:`franchise_name`), и на запросе подзаголовком строка выходила прямой
    бессмыслицей: «космическая одиссея» - в каталоге это «2001».
    """
    if picture is None:
        return ""
    wanted = slugify(query)
    keys = [picture.franchise]
    if picture.original:
        keys.append(franchise_key(picture.original))
    if any(wanted in key or key in wanted for key in keys):
        return ""
    return picture.title


def _aliases(groups: dict[str, list[Picture]]) -> dict[str, str]:
    """Оригинальное имя франшизы → ключ русской франшизы, в которой её больше всего раздач.

    ⚠️ Имён-однофамильцев в выдаче полно, и раньше побеждало последнее попавшееся: ``Steins;Gate``
    вело не на «Врата Штейна» (41 раздача), а на «Врата Штейна ONA» - одну раздачу-огрызок,
    случайно оказавшуюся в перечислении последней. Запрос латиницей после этого показывал
    именно огрызок, а русская озвучка так и оставалась за бортом.

    🔴 **Имя картины кладётся ЦЕЛИКОМ, а не только корнем франшизы.** Корень режет
    подзаголовок и номер части (:func:`franchise_key`), и латинское имя, которым каталог
    подписал саму картину, в указателе не появлялось вовсе. Живой промах: «Убить Билла»
    (2003, 58 раздач) приезжает строками ``Убить Билла / Kill Bill: Vol. 1``, то есть
    каталог сам ручается за пару, но в указатель попадал огрызок ``kill-bill`` - а точное
    ``kill-bill-vol-1`` доставалось сборнику саундтреков «VA - Убить Билла - 1» (одна
    раздача, ноль живых), у которого номер части в имени стоит без двоеточия и потому не
    режется. Запрос ``Kill Bill: Vol. 1`` попадал точным совпадением в этот огрызок: 96
    раздач первого круга схлопывались до ОДНОЙ мёртвой, и картину спасал только второй
    круг по русскому имени - лишний поход по всем индексерам на каждом старте.

    Дороги однофамильцам это не открывает, и вот почему: добавленное имя ДЛИННЕЕ того,
    что уже лежало в указателе. Корень ``kill-bill`` на ту же франшизу указывал и раньше;
    более точное имя может лишь развести то, что корень сводил, но не свести то, что он
    разводил. За саму пару «латиница ↔ русское имя» ручается не догадка, а строка
    каталога: имя берётся из ``picture.original``, а туда оно попадает только из релиза,
    назвавшего оба имени разом. Спор двух картин за одно имя решает тот же вес, что и
    для корня, - число раздач.
    """
    weight = {key: sum(len(p.releases) for p in items) for key, items in groups.items()}
    aliases: dict[str, str] = {}
    for key, items in groups.items():
        for picture in items:
            if not picture.original:
                continue
            for name in (franchise_key(picture.original), slugify(picture.original)):
                if name and weight[key] > weight.get(aliases.get(name, ""), 0):
                    aliases[name] = key
    return aliases
