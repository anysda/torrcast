"""Справка к меню франшизы: о чём картина, рейтинг, длительность.

Меню печатает список картин, и по одному названию с годом человек часто не помнит,
что это было: «Тачки 2» — это про гонки или про шпионов? Модуль добирает то же, что
человек нашёл бы в поиске за десять секунд: две фразы по-русски, рейтинг и хронометраж.

**Источники без ключей и регистрации.** Это условие, а не пожелание: `install.sh`
разворачивает всё сам, и просить пользователя завести учётку на TMDB ради подписи в
меню — значит сломать «склонировал и поехал». Отсюда связка:

* **ru.wikipedia** ``action=query&prop=extracts`` — описание по-русски. Одним запросом
  на всю франшизу (``exlimit=20``), без ключа, ~0.4 с.
* **Wikidata** (SPARQL) — ``P345`` (идентификатор IMDb) и ``P2047`` (хронометраж).
  Тоже одним запросом на все картины сразу, ~0.6 с.
* **Офлайн-выгрузка IMDb** ``title.ratings.tsv`` — сам рейтинг. Её кладёт `install.sh`
  (:data:`RATINGS_PATH`), в рантайме это чтение файла, а не поход в сеть.

Что проверено и отвергнуто:

* REST-эндпоинт ``/api/rest_v1/page/summary/`` — самый быстрый (0.19 с) и самый
  соблазнительный, но он отдаёт **протухший кэш**: у «Моаны» и «Моаны 2» он возвращал
  ревизию сентября 2024 года и текст «будущий фильм» про кино, вышедшее в ноябре 2024.
  Двухлетней давности справка хуже, чем никакой.
* Рейтинг из Wikidata (``P444``) — дыряв и неверен: у «Тачек» лежит оценка Rotten
  Tomatoes без IMDb вовсе, у «Тачек 3» подписано «IMDb 7.4» при настоящих 6.7.
* Полные выгрузки IMDb ``title.basics`` (225 МБ) и ``title.akas`` (510 МБ) — ими можно
  сматчить картину и взять хронометраж совсем без сети, но 745 МБ на установку ради
  двух строк в меню несоразмерны. ``title.ratings`` — 8.6 МБ, и это уже терпимо.

**Второй потребитель — поиск.** :func:`origin` спрашивает у той же статьи паспорт
картины: оригинальное название латиницей и год выпуска. Это чинит сразу две беды добора
(:func:`~torrcast.parse.alt_query`): оригинал перестаёт зависеть от того, попал ли он в
первую выдачу («Кингсман: Секретная служба» → ``Kingsman: The Secret Service`` вместо
транслита в никуда), а год становится опорой гейта, который не даёт добору молча
подменить картину чужой одноимённой. Сеть молчит — паспорт пуст, и поиск идёт как шёл.

**Меню справку не ждёт.** Всё это тянется фоном (:meth:`Facts.start`), пока
прогреваются раздачи, а :meth:`Facts.get` отдаёт то, что успело приехать к
:data:`FACTS_BUDGET`. Не успело, сеть отрезана, Википедия легла — меню печатается ровно
так, как печаталось до этого модуля, без задержки и без жалоб. Найденное ложится в
кэш (:data:`CACHE_PATH`), поэтому второй показ той же франшизы уже мгновенный.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import urlencode

from torrcast.parse import slugify, transliterate

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["CACHE_PATH", "RATINGS_PATH", "Fact", "Facts", "Origin", "origin", "titles_for"]

#: Выгрузка IMDb ``title.ratings.tsv``: ``tconst<TAB>рейтинг<TAB>голоса``. Кладёт и
#: обновляет `install.sh`; нет файла - просто не будет рейтинга.
RATINGS_PATH: Final = Path("/var/lib/torrcast/imdb-ratings.tsv")
#: Найденная справка ложится сюда, чтобы второй показ той же франшизы не ходил в сеть.
CACHE_PATH: Final = Path("/var/lib/torrcast/facts.json")
#: Сколько меню согласно ждать справку, секунды. Потолок, а не ожидание: в норме оба
#: запроса укладываются в секунду, и ждать нечего - они идут, пока греются раздачи.
FACTS_BUDGET: Final = 1.5
#: Потолок одного сетевого запроса. Меньше общего бюджета: их два, и второй зависит от
#: первого; залипший запрос обязан отпустить меню, а не съесть весь бюджет.
HTTP_TIMEOUT: Final = 1.2
#: Сколько добор живёт ВСЕГО, секунды, считая от :meth:`Facts.start`. Меню отпускается
#: через :data:`FACTS_BUDGET`, а поток дописывает кэш ещё столько - уже никого не держа.
TOPUP_LIMIT: Final = 3.0
#: Сколько помним, что справки нет, секунды. Пустой ответ - тоже ответ: без него каждое
#: меню снова шло в сеть за той же самой пустотой, снова не успевало к дедлайну и снова
#: печаталось голым. Срок конечный - статью могли и написать.
EMPTY_TTL: Final = 7 * 24 * 3600
#: Кем представляемся Wikimedia: у них это требование к автоматике, а не вежливость.
USER_AGENT: Final = "torrcast/1.0 (https://github.com/anysda/torrcast)"
_WIKI_HOST: Final = "ru.wikipedia.org"
_WIKI_PATH: Final = "/w/api.php"
_WIKIDATA_HOST: Final = "query.wikidata.org"
_WIKIDATA_PATH: Final = "/sparql"
#: Сколько статей влезает в один запрос ``prop=extracts`` (лимит самого API).
_EXLIMIT: Final = 20
#: Уточнения в скобках, которыми русская Википедия разводит одноимённые статьи.
#: «Моана» - это страница значений, а мультфильм лежит под «Моана (мультфильм)».
_QUALIFIERS: Final = (
    "",
    " (мультфильм)",
    " (фильм)",
    " (телесериал)",
    " (мультфильм, {year})",
    " (фильм, {year})",
)
#: Как русская Википедия подписывает оригинальное название: «(англ. Kingsman: The Secret
#: Service)». Язык любой - важно, что перед названием стоит его сокращение с точкой.
_ORIGINAL_RE: Final = re.compile(r"\(\s*(?:[а-яё]{2,12}\.\s*)+([^)]+)\)")
#: Год выпуска из паспортной фразы статьи: «...комедийный боевик 2014 года». Именно «года»,
#: а не первое попавшееся число: у фильма «1917» первым в тексте стоит его название.
_YEAR_RE: Final = re.compile(r"\b(1[89]\d{2}|20\d{2})\s+года")
#: Про кино ли статья вообще. «Восхождение» - это ещё и альпинизм, а «Матрица» - таблица.
#: Франшиза сюда входит намеренно: у «Кингсмана» отдельной статьи о первой части нет,
#: а имя франшизы - ровно то, которым её подписывают индексеры.
_CINEMA_RE: Final = re.compile(r"фильм|сериал|кинокартин|аниме|франшиз", re.IGNORECASE)
#: Кириллица в заголовке: по ней видно, годится ли он сам как оригинальное название.
_CYRILLIC: Final = re.compile(r"[а-яё]", re.IGNORECASE)
#: Уточнение в конце заголовка статьи: «Wednesday (TV series)», «Восхождение (фильм, 1976)».
#: Им Википедия разводит одноимённое, а индексерам оно ни к чему - раздачу подписывают
#: именем без скобки, и именно имя мы у справки и берём.
_TAIL_RE: Final = re.compile(r"\s*\([^)]*\)\s*$")
#: Сколько символов статьи просим у Википедии. Раньше просили две фразы (``exsentences``),
#: но фразы там режет тот же наивный счёт точек, от которого мы уходим: у «Дюны» ответ
#: приезжал обрубком ««Дюна» (англ. Dune), в титрах «Дюна: Часть первая» (англ.» - и
#: дочитать его было негде. Символы такого не умеют, а границу фразы мы ставим сами
#: (:func:`sentence`). 500 символов на статью - это ~20 КБ на всю франшизу и те же 0.5 с.
_EXCHARS: Final = 500
#: Потолок описания в меню, символы. Первая фраза статьи почти всегда короче (у «Тачек»
#: 158, у «Моаны» 216); длиннее бывают биографические - у «Оппенгеймера» она идёт на 360
#: символов вместе с полным названием книги-первоисточника. Такую дочитывать в меню незачем,
#: и только её мы обрываем многоточием.
BLURB_CAP: Final = 240
#: Последнее слово перед точкой - по нему видно, конец это фразы или сокращение.
_LAST_WORD_RE: Final = re.compile(r"([A-Za-zА-Яа-яЁё]+)[^A-Za-zА-Яа-яЁё]*$")
#: С чего начинается новая фраза: заглавная буква или открывающая кавычка названия.
_SENTENCE_START_RE: Final = re.compile(r"[«\"“A-ZА-ЯЁ]")
#: Сокращения, после которых точка ничего не кончает. Языки оригинала («англ.», «бел.»,
#: «фр.») в русской статье о кино стоят в каждой первой фразе, остальное - то, чем она
#: обрастает: «реж.», «т. е.», «им.», «др.». Однобуквенные сюда не нужны: инициал
#: («Г. А. Потёмкина») и «т. е.» ловятся правилом «одна буква - не слово».
_ABBREV: Final = frozenset(
    (
        # языки оригинала
        "англ", "фр", "нем", "итал", "исп", "яп", "кит", "кор", "бел", "укр", "рус",
        "лат", "греч", "польск", "чеш", "швед", "норв", "фин", "дат", "нидерл", "порт",
        "тур", "перс", "араб", "иврит", "серб", "хорв", "рум", "венг", "эст", "лит",
        # прочее, чем обрастает первая фраза
        "букв", "дословно", "транслит", "сокр", "совр", "устар", "прим", "ср", "см",
        "напр", "др", "пр", "тыс", "млн", "млрд", "руб", "коп", "гг", "вв", "нэ", "ок",
        "реж", "сцен", "опер", "комп", "худ", "прод", "им", "ул", "пл", "св", "стр", "гл",
    )
)  # fmt: skip
#: Сколько статей смотрим в выдаче поиска Википедии. Нужная лежит в первых строках;
#: глубже идут актёры и саундтреки, и они только тянут ответ.
_SEARCH_HITS: Final = 6


class _IPv4Connection(http.client.HTTPSConnection):
    """HTTPS строго по IPv4.

    Не придирка: на хосте с прописанным, но нерабочим IPv6-выходом (типовая история за
    NAT и на VPS без v6-маршрута) обычный клиент сначала честно висит в SYN-SENT по
    AAAA-адресу и только потом падает на IPv4. Замер на таком хосте: 5.4 с против 0.33 с
    на тот же запрос. Бюджет справки — полторы секунды, то есть при v6 её не бывает
    никогда. Показу это не мешает (пусто — норма), но и терять её на ровном месте незачем.
    """

    #: Контекст TLS: проверка серта и имени - обычная, ничего тут не ослаблено.
    context: ssl.SSLContext = ssl.create_default_context()

    def connect(self) -> None:
        where = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)
        address = where[0][4]
        raw = socket.create_connection((str(address[0]), int(address[1])), self.timeout)
        self.sock = self.context.wrap_socket(raw, server_hostname=self.host)


def get_json(host: str, path: str, params: dict[str, str], headers: dict[str, str],
             timeout: float) -> Any:  # fmt: skip
    """GET с разбором JSON. Любая неудача — исключение: ловит его :meth:`Facts._work`."""
    conn = _IPv4Connection(host, timeout=timeout)
    try:
        conn.request(
            "GET", f"{path}?{urlencode(params)}", headers={"User-Agent": USER_AGENT, **headers}
        )
        response = conn.getresponse()
        if response.status != 200:
            raise OSError(f"{host} ответил {response.status}")
        return json.loads(response.read())
    finally:
        conn.close()


@dataclass(frozen=True, slots=True)
class Fact:
    """Справка по одной картине. Пустые поля — норма: нет данных, значит нет строки."""

    about: str = ""
    #: Уже с источником: «IMDb 7.6». Голая цифра в меню не значила бы ничего.
    rating: str = ""
    #: Готовая строка «1 ч 47 мин» - не минуты: считать их в уме человек не обязан.
    runtime: str = ""

    def __bool__(self) -> bool:
        return bool(self.about or self.rating or self.runtime)


def hms(minutes: int) -> str:
    """Минуты → «1 ч 47 мин»; ровный час — «1 ч»; меньше часа — «47 мин»; ноль — пусто."""
    if minutes <= 0:
        return ""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} мин"
    return f"{hours} ч {rest} мин" if rest else f"{hours} ч"


def titles_for(title: str, year: int | None) -> list[str]:
    """Под какими именами статья может лежать в русской Википедии, в порядке доверия.

    Первым — само название: «Тачки 2» так и называется. Дальше уточнения в скобках,
    которыми Википедия разводит одноимённое: «Моана» голым именем — это страница
    значений про полинезийское слово, а мультфильм 2016 года лежит под «Моана
    (мультфильм)», ремейк 2026-го — под «Моана (фильм, 2026)».

    Подзаголовок после двоеточия отрезается отдельным кандидатом: раздачи подписывают
    старое кино развёрнуто («Моана: романтика золотого века»), а статья называется
    короче. Чужую статью это не притащит — год всё равно проверяется по тексту.
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
    return out


def confirms(extract: str, year: int | None) -> bool:
    """Про тот ли это фильм: в первых фразах статьи должен стоять нужный год.

    Проверка дешёвая и на удивление надёжная — русская Википедия открывает статью о кино
    ровно этой формулой: «американский компьютерно-анимационный фильм 2006 года».
    Без неё «Моана» тянула бы описание ремейка 2026 года на мультфильм 2016-го, а «Тачки»
    — статью про франшизу целиком.

    Год неизвестен (раздача его не назвала) — сверять нечем, и справки не будет: пустая
    строка честнее чужого фильма.
    """
    return year is not None and bool(re.search(rf"\b{year}\b", extract))


@dataclass(frozen=True, slots=True)
class Origin:
    """Паспорт картины по справке: как она называется в оригинале и какого она года.

    Оба поля необязательны и означают ровно то, что сказано. Пустой ``title`` — у картины
    нет названия латиницей (советское и российское кино), а не «мы не нашли»: добирать
    латиницей такую картину нечем и не нужно. Пустой ``year`` — статью опознать не
    удалось; тогда гейт добора сверяет годы по самой выдаче, как умеет.

    ``name`` - как ту же картину зовут по-русски (заголовок русской статьи). Нужен
    зеркальному случаю: спросили латиницей, а половина каталога подписана по-русски
    («Cars» - одна мёртвая раздача при живых «Тачках»), и добирать надо русским именем.
    """

    title: str = ""
    year: int | None = None
    name: str = ""

    def __bool__(self) -> bool:
        return bool(self.title or self.year or self.name)


def origin(title: str, series: bool = False, budget: float = FACTS_BUDGET) -> Origin:
    """Паспорт картины из Википедии. Жёсткий потолок по времени и кэш на диске.

    Зовётся только на тощей выдаче, то есть там, где поиск и так собирается идти на
    второй круг по индексерам (1-3 с). Полторы секунды потолка на его фоне не видны, а
    счастливый путь сюда не заходит вовсе.

    ⚠️ Год выдачи сюда НЕ передаётся, и это принципиально: паспорт нужен гейту как
    независимое мнение. Подсказали бы год - справка послушно нашла бы статью под него, и
    сверять после этого было бы нечего: на «Восхождении» с подсказкой ``2019`` она
    уверенно приносила «Hannibal Rising», а без подсказки честно отвечает «1976».

    Молчание сети стоит ровно :attr:`budget`: запрос живёт в отдельном потоке, и залипший
    сокет держит не поиск, а демона, который умрёт вместе с процессом. Любая ошибка -
    пустой паспорт: справка не вправе ни ронять поиск, ни задерживать его сверх обещанного.
    """
    stored = _cached_origin(title, series)
    if stored is not None:
        return stored
    box: list[Origin] = []

    def work() -> None:
        with contextlib.suppress(Exception):
            box.append(origin_now(title, series, min(HTTP_TIMEOUT, budget)))

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(budget)
    found = box[0] if box else Origin()
    if found:
        _remember_origin(title, series, found)
    return found


def origin_now(title: str, series: bool = False, timeout: float = HTTP_TIMEOUT) -> Origin:
    """Синхронный поход за паспортом. Неудача — исключение, его ловит :func:`origin`.

    Два шага, и второй — только если первый промахнулся. Прямая выборка по именам
    (:func:`titles_for`) дешевле и точнее, ею и закрывается большинство: «Психо», «Печать
    зла», «Дедвуд (телесериал)» лежат ровно там, где их и ждёшь. Но не все: «Восхождение»
    голым именем — страница значений, а «Кингсман: Секретная служба» на ru.wikipedia
    подписана латиницей («Kingsman: Секретная служба»), и никаким перебором уточнений в
    неё не попасть. Тогда спрашиваем поиском самой Википедии — он эти случаи и разводит.
    """
    kind = "сериал" if series else "фильм"
    names = titles_for(title, None)
    if series:  # у сериала своя статья, и лежит она под своим уточнением
        names.sort(key=lambda name: "сериал" not in name)
    hops, pages = _pages(get_json(_WIKI_HOST, _WIKI_PATH, _extract_params(names), {}, timeout))
    direct = [_article(name, hops, pages) for name in names]
    found = read_origin(direct, title, trusted=True)
    if found:
        return found
    payload = get_json(_WIKI_HOST, _WIKI_PATH, _search_params(f"{title} {kind}"), {}, timeout)
    return read_origin(_ranked(payload), title)


def read_origin(pages: list[Any], title: str, trusted: bool = False) -> Origin:
    """Статьи-кандидаты → паспорт. Побеждает первая, которая про кино и про то самое.

    Статья должна быть про кино — «Восхождение» это ещё и альпинизм, а «Матрица» —
    таблица. А вот «про то самое» проверяется по-разному, и это ``trusted``.

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
    """
    for page in pages:
        if page is None:
            continue
        heading = str(page.get("title") or "")
        extract = str(page.get("extract") or "")
        if not _CINEMA_RE.search(f"{heading} {extract}"):
            continue
        seen = _YEAR_RE.search(extract)
        latin = (
            latin_title(extract)
            or english_title(page)
            or ("" if _CYRILLIC.search(heading) else heading)
        )
        if not trusted and not akin(title, heading) and not _same_latin(title, latin):
            continue
        found = Origin(
            title=latin,
            year=int(seen.group(1)) if seen else None,
            name=_TAIL_RE.sub("", heading) if _CYRILLIC.search(heading) else "",
        )
        if found:
            return found
    return Origin()


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


def akin(title: str, heading: str) -> bool:
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
    """
    base = slugify(heading.split(" (")[0])
    solid = base.replace("-", "")
    return bool(base) and any(
        want
        and (
            want == base
            or want.startswith(f"{base}-")
            or base.startswith(f"{want}-")
            or want.replace("-", "") == solid
        )
        for want in (slugify(title), slugify(transliterate(title)))
    )


def latin_title(extract: str) -> str:
    """Оригинальное название из первой фразы статьи; нет латиницы — пустая строка.

    Русская Википедия открывает статью о зарубежном кино скобкой с языком оригинала:
    «Кингсман: Секретная служба» (англ. Kingsman: The Secret Service). Скобок в фразе
    бывает несколько, и не все они про название — «(род. 1950)» у режиссёра тоже скобка
    с сокращением, поэтому годится лишь та, внутри которой латиница и нет кириллицы.
    Хвост после запятой отрезается: там лежит дословный перевод, а не имя раздачи.
    """
    for match in _ORIGINAL_RE.finditer(extract):
        name = re.split(r"[,;]", match.group(1))[0].strip(" «»\"'")
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
    """
    flat = re.sub(r"\s+", " ", text).strip()
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
            fresh = fetch(self.wanted)
            # Дописываем к тому, что уже лежало в кэше, а не заменяем: сеть отвечает только
            # про ненайденное, и присваиванием мы выбрасывали справку, которая у нас была.
            self.found = {**self.found, **fresh}
            # Пустой ответ тоже запоминаем - иначе поход за ним повторяется каждое меню.
            _remember(fresh, [key for key in self.wanted if key not in self.found])
        except Exception:
            pass
        finally:
            self._done.set()


def fetch(
    wanted: list[tuple[str, int | None]], timeout: float = HTTP_TIMEOUT
) -> dict[tuple[str, int | None], Fact]:
    """Собрать справку по картинам: Википедия → Wikidata → выгрузка рейтингов.

    Цепочка тут не вся: Wikidata спрашивают по идентификаторам из Википедии, и эти два
    запроса иначе как друг за другом не идут. А вот выгрузка рейтингов - файл на диске, с
    сетью не связанный ничем; читалась она третьим шагом, и её сотня тысяч строк ложилась
    на те же полторы секунды дедлайна, что и оба запроса. Теперь она читается ПОКА идёт
    первый запрос и к моменту нужды уже готова.
    """
    scores: dict[str, str] = {}

    def load() -> None:
        nonlocal scores
        scores = ratings()

    reader = threading.Thread(target=load, daemon=True)
    reader.start()
    about, entities = wiki_extracts(wanted, timeout)
    ids = wikidata_ids(sorted(set(entities.values())), timeout) if entities else {}
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

    Кандидатов на статью у картины несколько (:func:`titles_for`), и все они уезжают в
    один и тот же запрос — API берёт до :data:`_EXLIMIT` статей за раз. Побеждает первый
    кандидат, который оказался статьёй (не страницей значений, не пустышкой) и подтвердил
    год (:func:`confirms`).
    """
    candidates = {key: titles_for(*key) for key in wanted}
    names: list[str] = []
    for depth in range(max((len(c) for c in candidates.values()), default=0)):
        for key in wanted:
            if depth < len(candidates[key]) and len(names) < _EXLIMIT:
                names.append(candidates[key][depth])
    return _read_pages(
        get_json(_WIKI_HOST, _WIKI_PATH, _extract_params(names), {}, timeout), candidates
    )


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


def _origin_key(title: str, series: bool) -> str:
    """Паспорта лежат в том же файле, что и справка, но в своём ряду ключей."""
    return f"origin|{'tv' if series else 'movie'}|{title}"


def _read_cache() -> dict[str, Any]:
    """Кэш с диска. Битый или отсутствующий — пустой: перечитаем из сети."""
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_cache(raw: dict[str, Any]) -> None:
    """Дописать кэш. Не вышло записать — молчим: это не путь показа."""
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except OSError:
        pass


def _cached_origin(title: str, series: bool) -> Origin | None:
    """Что лежит в кэше. ``None`` — не спрашивали; пустой паспорт — спрашивали, нет его."""
    row = _read_cache().get(_origin_key(title, series))
    if not isinstance(row, dict):
        return None
    shown = row.get("year")
    return Origin(
        title=str(row.get("title", "")),
        year=shown if isinstance(shown, int) else None,
        name=str(row.get("name", "")),
    )


def _remember_origin(title: str, series: bool, found: Origin) -> None:
    raw = _read_cache()
    raw[_origin_key(title, series)] = {
        "title": found.title,
        "year": found.year,
        "name": found.name,
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
        out[key] = Fact(
            about=str(row.get("about", "")),
            rating=str(row.get("rating", "")),
            runtime=str(row.get("runtime", "")),
        )
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
