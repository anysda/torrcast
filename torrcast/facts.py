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

**Меню справку не ждёт.** Всё это тянется фоном (:meth:`Facts.start`), пока
прогреваются раздачи, а :meth:`Facts.get` отдаёт то, что успело приехать к
:data:`FACTS_BUDGET`. Не успело, сеть отрезана, Википедия легла — меню печатается ровно
так, как печаталось до этого модуля, без задержки и без жалоб. Найденное ложится в
кэш (:data:`CACHE_PATH`), поэтому второй показ той же франшизы уже мгновенный.
"""

from __future__ import annotations

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

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["CACHE_PATH", "RATINGS_PATH", "Fact", "Facts", "titles_for"]

#: Выгрузка IMDb ``title.ratings.tsv``: ``tconst<TAB>рейтинг<TAB>голоса``. Кладёт и
#: обновляет `install.sh`; нет файла — просто не будет рейтинга.
RATINGS_PATH: Final = Path("/var/lib/torrcast/imdb-ratings.tsv")
#: Найденная справка ложится сюда, чтобы второй показ той же франшизы не ходил в сеть.
CACHE_PATH: Final = Path("/var/lib/torrcast/facts.json")
#: Сколько меню согласно ждать справку, секунды. Потолок, а не ожидание: в норме оба
#: запроса укладываются в секунду, и ждать нечего — они идут, пока греются раздачи.
FACTS_BUDGET: Final = 1.5
#: Потолок одного сетевого запроса. Меньше общего бюджета: их два, и второй зависит от
#: первого; залипший запрос обязан отпустить меню, а не съесть весь бюджет.
HTTP_TIMEOUT: Final = 1.2
#: Кем представляемся Wikimedia: у них это требование к автоматике, а не вежливость.
USER_AGENT: Final = "torrcast/1.0 (https://github.com/anysda/torrcast)"
_WIKI_HOST: Final = "ru.wikipedia.org"
_WIKI_PATH: Final = "/w/api.php"
_WIKIDATA_HOST: Final = "query.wikidata.org"
_WIKIDATA_PATH: Final = "/sparql"
#: Сколько статей влезает в один запрос ``prop=extracts`` (лимит самого API).
_EXLIMIT: Final = 20
#: Уточнения в скобках, которыми русская Википедия разводит одноимённые статьи.
#: «Моана» — это страница значений, а мультфильм лежит под «Моана (мультфильм)».
_QUALIFIERS: Final = ("", " (мультфильм)", " (фильм)", " (мультфильм, {year})", " (фильм, {year})")


class _IPv4Connection(http.client.HTTPSConnection):
    """HTTPS строго по IPv4.

    Не придирка: на хосте с прописанным, но нерабочим IPv6-выходом (типовая история за
    NAT и на VPS без v6-маршрута) обычный клиент сначала честно висит в SYN-SENT по
    AAAA-адресу и только потом падает на IPv4. Замер на таком хосте: 5.4 с против 0.33 с
    на тот же запрос. Бюджет справки — полторы секунды, то есть при v6 её не бывает
    никогда. Показу это не мешает (пусто — норма), но и терять её на ровном месте незачем.
    """

    #: Контекст TLS: проверка серта и имени — обычная, ничего тут не ослаблено.
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
    #: Готовая строка «1 ч 47 мин» — не минуты: считать их в уме человек не обязан.
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


def shorten(extract: str, limit: int) -> str:
    """Первая фраза статьи, укороченная до ширины терминала.

    Википедия открывает статью паспортом («американский компьютерно-анимационный
    спортивный комедийный фильм 2006 года, снятый студией Pixar…») — это и есть ответ
    на «про что кино», если обрезать его по границе предложения, а не по счёту букв.

    Точка внутри скобок границей не считается: русская статья о зарубежном кино почти
    всегда начинается с «(англ. Cars)», и наивный разрез по первой же точке оставлял от
    описания огрызок ««Тачки» (англ.».
    """
    text = re.sub(r"\s+", " ", extract).strip()
    first = text
    depth = 0
    for pos, char in enumerate(text):
        depth += (char == "(") - (char == ")")
        if char in ".!?" and depth == 0 and text[pos + 1 : pos + 2] == " ":
            first = text[: pos + 1]
            break
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(" ", 1)[0]
    return f"{cut}…" if cut else ""


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

    def start(self) -> None:
        """Пустить добор фоном. Ошибки внутри гасятся: справка не вправе ронять показ."""
        self._deadline = time.monotonic() + self.budget
        if not self.wanted:
            self._done.set()
            return
        self.found = _cached(self.wanted)
        if len(self.found) == len(self.wanted):  # всё уже лежит в кэше — сети не надо
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

    def _work(self) -> None:
        try:
            self.found = fetch(self.wanted)
            _remember(self.found)
        except Exception:
            pass
        finally:
            self._done.set()


def fetch(
    wanted: list[tuple[str, int | None]], timeout: float = HTTP_TIMEOUT
) -> dict[tuple[str, int | None], Fact]:
    """Собрать справку по картинам: Википедия → Wikidata → выгрузка рейтингов."""
    about, entities = wiki_extracts(wanted, timeout)
    ids = wikidata_ids(sorted(set(entities.values())), timeout) if entities else {}
    scores = ratings() if ids else {}
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
    params = {
        "action": "query",
        "titles": "|".join(names),
        "redirects": "1",
        "prop": "extracts|pageprops",
        "ppprop": "disambiguation|wikibase_item",
        "exintro": "1",
        "explaintext": "1",
        "exsentences": "2",
        "exlimit": str(_EXLIMIT),
        "format": "json",
        "formatversion": "2",
    }
    return _read_pages(get_json(_WIKI_HOST, _WIKI_PATH, params, {}, timeout), candidates)


def _read_pages(
    payload: Any, candidates: dict[tuple[str, int | None], list[str]]
) -> tuple[dict[tuple[str, int | None], str], dict[tuple[str, int | None], str]]:
    """Разобрать ответ Википедии: кандидат → статья → описание и Q-идентификатор.

    Запрошенное имя и заголовок статьи — не одно и то же: API нормализует регистр и ведёт
    по перенаправлениям, и «Моана (мультфильм)» вполне может ответить статьёй с другим
    заголовком. Обратный путь API отдаёт сам, списками ``normalized`` и ``redirects``.
    """
    query = payload.get("query", {}) if isinstance(payload, dict) else {}
    hops: dict[str, str] = {}
    for kind in ("normalized", "redirects"):
        for hop in query.get(kind, []) or []:
            hops[hop.get("from", "")] = hop.get("to", "")
    pages = {page.get("title", ""): page for page in query.get("pages", []) or []}
    about: dict[tuple[str, int | None], str] = {}
    entities: dict[tuple[str, int | None], str] = {}
    for key, names in candidates.items():
        for name in names:
            seen = name
            for _ in range(3):  # нормализация, затем перенаправление; больше не бывает
                seen = hops.get(seen, seen)
            page = pages.get(seen)
            props = (page or {}).get("pageprops") or {}
            extract = (page or {}).get("extract") or ""
            if not page or page.get("missing") or "disambiguation" in props:
                continue
            if not confirms(extract, key[1]):
                continue
            about[key] = extract
            if props.get("wikibase_item"):
                entities[key] = props["wikibase_item"]
            break
    return about, entities


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


def _cached(wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
    """Что уже лежит на диске. Битый кэш — как пустой: перечитаем из сети."""
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[tuple[str, int | None], Fact] = {}
    for key in wanted:
        row = raw.get(_key(*key))
        if isinstance(row, dict):
            out[key] = Fact(
                about=str(row.get("about", "")),
                rating=str(row.get("rating", "")),
                runtime=str(row.get("runtime", "")),
            )
    return out


def _remember(found: dict[tuple[str, int | None], Fact]) -> None:
    """Дописать найденное в кэш. Не вышло записать — молчим: это не путь показа."""
    if not found:
        return
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, ValueError):
        raw = {}
    for key, fact in found.items():
        raw[_key(*key)] = {"about": fact.about, "rating": fact.rating, "runtime": fact.runtime}
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except OSError:
        pass
