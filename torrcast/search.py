"""Поиск релизов через собственный Prowlarr: внешних API и учёток нет, индексеры
публичные, apikey локальный и генерится ``install.sh``. Модуль возвращает
сырую выдачу; смысл ей придаёт :mod:`torrcast.parse`.

⚠️ Две особенности, выясненные на живом Prowlarr 2.5.2: агрегат по всем
индексерам живёт на ``/api/v1/search``, а ``/api/v2.0/indexers/all/results`` — это
Jackett, у Prowlarr 404 (Torznab-XML отдаётся по индексеру ``/<id>/api`` и его
разбирает :func:`from_torznab` — он же путь совместимости с Jackett'ом); ``magnetUrl``
в выдаче — ссылка-прокси на сам Prowlarr, опора только ``infoHash``, magnet собираем
сами и вешаем публичные трекеры (пиры — magnet + DHT + публичные ретрекеры).

⚠️ Третья: у агрегата нет частичного ответа, поэтому спрашиваем индексеры врозь -
каждого своим запросом и в свой бюджет (:meth:`Prowlarr._apart`). Иначе один молчащий
индексер держит в себе находки всех остальных.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote
from xml.etree import ElementTree

from torrcast import InfraError, NotFoundError, why
from torrcast.parse import Release, parse_release_name
from torrcast.timing import mark

if TYPE_CHECKING:
    import requests

__all__ = [
    "PUBLIC_TRACKERS",
    "Prowlarr",
    "RawResult",
    "from_torznab",
    "magnet_for",
    "merge",
    "to_releases",
]

_SEARCH_PATH: Final = "/api/v1/search"
_INDEXERS_PATH: Final = "/api/v1/indexer"
#: Потолок общего запроса - того, которым спрашиваем, когда список индексеров недоступен
#: (:meth:`Prowlarr._known`). Такой запрос отдаётся, только когда опрошены ВСЕ индексеры,
#: поэтому потолок здесь - это не «сколько ждём обычно» (обычно 1-3 с), а «сколько терпим
#: одного залипшего». Прежние 60 с рубили такой поиск начисто - вместе с находками
#: остальных индексеров, то есть ровно там, где ответ уже был.
_TIMEOUT: Final = 150.0
#: Личный бюджет ОДНОГО индексера. Замеры на живом стенде (1985 запросов к четырём
#: индексерам): половина ответов до 0.5 с, 99-я доля - 5.6 с, самый долгий честный
#: ответ - 16 с (отказ трекера и повтор внутри Prowlarr). Всё, что дольше, - уже не
#: медленный ответ, а молчание: канал рвёт поток посреди тела, и Prowlarr сидит на нём
#: до своей сотой секунды. Бюджет отрезает такое молчание, не задев ни одного живого
#: ответа, и стоит поиску не 100 с, а этих секунд - да и то лишь молчуну.
_INDEXER_TIMEOUT: Final = 20.0
#: Список индексеров - локальная страница Prowlarr, сеть в ней не участвует.
_LIST_TIMEOUT: Final = 15.0
#: Кино, сериалы и «Other» - под последней RuTor отдаёт вообще всё (категорий у него нет).
_CATEGORIES: Final = (2000, 5000, 8000)
_TORZNAB_NS: Final = "{http://torznab.com/schemas/2015/feed}"
_HASH_RE: Final = re.compile(r"^[0-9a-fA-F]{40}$")
#: Сырые поля одной строки выдачи в порядке :meth:`RawResult.build`.
_Row = tuple[Any, Any, Any, Any, Any]

#: Открытые трекеры, которые мы дописываем в каждый magnet. У раздач RuTracker
#: из Knaben публичных ретрекеров нет, у RuTor нет ``tr=`` вообще - без этого
#: списка пиры искались бы только через DHT.
PUBLIC_TRACKERS: Final = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://opentracker.io:6969/announce",
)


def magnet_for(info_hash: str, title: str = "") -> str:
    """Собрать magnet из hash, имени и списка публичных трекеров."""
    parts = [f"magnet:?xt=urn:btih:{info_hash.lower()}"]
    if title:
        parts.append(f"dn={quote(title)}")
    parts += [f"tr={quote(t, safe='')}" for t in PUBLIC_TRACKERS]
    return "&".join(parts)


@dataclass(frozen=True, slots=True)
class RawResult:
    title: str
    info_hash: str
    size: int = 0
    seeders: int = 0
    indexer: str = ""
    #: Сколькими строками выдачи приехала эта раздача: индексеры зеркалят друг друга, и
    #: один торрент приходит от нескольких сразу. :func:`merge` оставляет одну строку, но
    #: помнит, сколько их было - иначе счёт «сколько нашлось» зависел бы от того, как
    #: устроен опрос индексеров, а не от каталога.
    copies: int = 1

    @property
    def magnet(self) -> str:
        return magnet_for(self.info_hash, self.title)

    @classmethod
    def build(cls, title: Any, info_hash: Any, size: Any, seeders: Any, indexer: Any) -> RawResult:
        """Собрать результат из сырых полей; без валидного hash строка бесполезна."""
        text = str(info_hash or "").strip()
        if not _HASH_RE.match(text) or not str(title or "").strip():
            raise ValueError("нет hash или имени")
        return cls(str(title), text, _int(size), _int(seeders), str(indexer or ""))


def _collect(rows: Iterable[_Row]) -> list[RawResult]:
    """Собрать строки выдачи, молча пропуская непригодные (без hash или имени)."""
    out: list[RawResult] = []
    for row in rows:
        try:
            out.append(RawResult.build(*row))
        except ValueError:
            continue
    return out


def from_json(payload: Any) -> list[RawResult]:
    """Разобрать ответ ``/api/v1/search``."""
    if not isinstance(payload, list):
        raise InfraError("Prowlarr вернул неожиданный ответ")
    return _collect(
        (i.get("title"), i.get("infoHash"), i.get("size"), i.get("seeders"), i.get("indexer"))
        for i in payload
        if isinstance(i, dict)
    )


def from_torznab(xml: str) -> list[RawResult]:
    """Разобрать Torznab-RSS: ``infohash`` и ``seeders`` лежат в ``torznab:attr``."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise InfraError(f"индексер вернул битый XML: {exc}") from exc
    rows: list[_Row] = []
    for item in root.iter("item"):
        attrs = {a.get("name", ""): a.get("value", "") for a in item.iter(f"{_TORZNAB_NS}attr")}
        indexer = item.findtext("prowlarrindexer") or item.findtext("jackettindexer") or ""
        title, size = item.findtext("title"), item.findtext("size")
        rows.append((title, attrs.get("infohash"), size, attrs.get("seeders"), indexer))
    return _collect(rows)


class Prowlarr:
    def __init__(self, base_url: str, apikey: str, timeout: float = _TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.apikey = apikey
        self.timeout = timeout
        #: Индексеры, не уложившиеся в личный бюджет последнего поиска - по именам.
        self.silent: tuple[str, ...] = ()
        self._session: requests.Session | None = None
        self._indexers: tuple[tuple[int, str], ...] | None = None

    def search(self, query: str, limit: int = 100) -> list[RawResult]:
        """Найти раздачи во всех подключённых индексерах: :class:`InfraError` — Prowlarr
        недоступен или ответил не тем, :class:`NotFoundError` — пригодных раздач нет.

        Спрашиваем КАЖДЫЙ индексер отдельным запросом (см. :meth:`_apart`): у общего
        запроса нет частичного ответа, и один молчун держит в себе выдачу всех
        остальных. Список индексеров не отдали - остаётся прежний общий запрос.
        """
        found = self._apart(query, limit)
        results = found if found is not None else from_json(self._get_json(self._url(query, limit)))
        if not results:
            raise NotFoundError(f"по запросу «{query}» ничего не нашлось")
        return results

    def _url(self, query: str, limit: int, indexer: int | None = None) -> str:
        cats = "".join(f"&categories={c}" for c in _CATEGORIES)
        one = f"&indexerIds={indexer}" if indexer is not None else ""
        return (
            f"{self.base_url}{_SEARCH_PATH}?apikey={quote(self.apikey)}"
            f"&query={quote(query)}&type=search&limit={limit}{cats}{one}"
        )

    def _apart(self, query: str, limit: int) -> list[RawResult] | None:
        """Круг по индексерам, где у каждого свой бюджет; ``None`` - список не отдали.

        🔴 Зачем врозь, если у Prowlarr есть общий запрос. Он отвечает, только когда
        опрошены ВСЕ индексеры, и вернуть половину выдачи не умеет. Один залипший
        индексер поэтому стоил не своей задержки, а всего поиска: замерено на живом
        стенде - три индексера ответили за 0.1-0.6 с, четвёртый молчал, и `cast`
        отдал меню через 100.1 с (внутри Prowlarr это ``Failed to read complete http
        response`` ровно на сотой секунде - потолок его собственного HTTP-клиента).
        Второй круг по латинскому названию удваивал цену: человек ждал две минуты
        на живой франшизе. Врозь молчун стоит только своего бюджета, а находки
        остальных приезжают за их обычные 0.1-0.6 с.

        Параллель тут не «побольше потоков», а ровно та же, что была: общий запрос
        Prowlarr сам опрашивает индексеры разом. На хост по-прежнему приходится один
        запрос за круг - это важно для тех трекеров, что рассыпаются от нескольких
        одновременных.

        Выдачи склеиваются :func:`merge`, то есть по ``infoHash``: один и тот же торрент
        из двух индексеров - одна раздача, а не две. Общий запрос отдавал такие строки
        дважды (на живом стенде «матрица»: 190 строк против 179 склеенных).
        """
        from concurrent.futures import ThreadPoolExecutor

        known = self._known()
        if not known:
            return None
        self._session = self._session or self._new_session()
        got: list[list[RawResult]] = []
        counts: dict[str, int] = {}
        lost: list[str] = []
        why_lost = ""
        with ThreadPoolExecutor(max_workers=len(known)) as pool:
            asked = [(name, pool.submit(self._one, query, limit, num)) for num, name in known]
        for name, task in asked:
            try:
                rows = task.result()
            except InfraError as exc:
                lost.append(name)
                why_lost = str(exc)
            else:
                got.append(rows)
                counts[name] = len(rows)
        self.silent = tuple(lost)
        from torrcast import trace

        # Полный расклад круга в недельный след: кто сколько отдал и кто смолчал. mark ниже
        # заводится лишь на потерю (это фаза старта), а следу нужен и весь ответивший круг.
        trace.emit("search", "indexers", got=counts, silent=list(lost))
        if lost:
            mark("индексеры", молчат=lost, бюджет=_INDEXER_TIMEOUT)
        if not got:  # молчат все до одного - это не «ничего не нашлось», а инфра
            raise InfraError(why_lost)
        return merge(*got)

    def _one(self, query: str, limit: int, indexer: int) -> list[RawResult]:
        """Выдача одного индексера в его личный бюджет."""
        return from_json(self._get_json(self._url(query, limit, indexer), _INDEXER_TIMEOUT))

    def _known(self) -> tuple[tuple[int, str], ...]:
        """Включённые индексеры (номер, имя); пусто - спрашивать придётся общим запросом."""
        if self._indexers is None:
            try:
                payload = self._get_json(
                    f"{self.base_url}{_INDEXERS_PATH}?apikey={quote(self.apikey)}", _LIST_TIMEOUT
                )
            except InfraError:
                return ()
            if not isinstance(payload, list):
                return ()
            self._indexers = tuple(
                (int(i["id"]), str(i.get("name") or i["id"]))
                for i in payload
                if isinstance(i, dict) and i.get("enable") and str(i.get("id", "")).isdigit()
            )
        return self._indexers

    def _new_session(self) -> requests.Session:
        """Сессия, поднятая ДО потоков: ленивая её сборка внутри них - гонка."""
        import requests

        return requests.Session()

    def _get_json(self, url: str, timeout: float | None = None) -> Any:
        import requests

        if self._session is None:
            self._session = self._new_session()
        try:
            response = self._session.get(url, timeout=timeout or self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise InfraError(f"Prowlarr не отвечает ({self.base_url}): {why(exc)}") from exc
        except ValueError as exc:
            raise InfraError("Prowlarr вернул не JSON") from exc


def merge(*batches: list[RawResult]) -> list[RawResult]:
    """Склеить выдачи нескольких запросов, оставив каждую раздачу один раз.

    Один и тот же торрент приходит и по русскому названию, и по латинскому, а
    ещё и из разных индексеров - тождество тут ровно одно, ``infoHash``. Порядок
    сохраняем: раздачи первого запроса идут первыми.

    ⚠️ Сколькими строками раздача приехала - не пустяк, а :attr:`RawResult.copies`. Пока
    индексеры спрашивались общим запросом, зеркальный торрент считался столько раз,
    сколько индексеров его несут, и все замеры «сколько нашлось» сделаны в этих строках.
    Склейка их обнулять не вправе: иначе один и тот же каталог выглядит то полным, то
    тощим - смотря как опрошены индексеры. Считаем по РАЗНЫМ индексерам, а не по строкам:
    добор вторым именем приносит те же раздачи от тех же индексеров, и складывать круги
    значило бы удваивать каталог на ровном месте.
    """
    seen: dict[str, RawResult] = {}
    sources: dict[str, set[str]] = {}
    carried: dict[str, int] = {}
    for batch in batches:
        for item in batch:
            key = item.info_hash.lower()
            seen.setdefault(key, item)
            sources.setdefault(key, set()).add(item.indexer)
            carried[key] = max(carried.get(key, 1), item.copies)
    return [replace(r, copies=max(len(sources[k]), carried[k])) for k, r in seen.items()]


def to_releases(results: list[RawResult]) -> list[Release]:
    """Разобрать сырую выдачу в релизы, перенеся размер, сиды и magnet."""
    return [
        replace(
            parse_release_name(item.title),
            size=item.size,
            seeders=item.seeders,
            magnet=item.magnet,
            indexer=item.indexer,
            copies=item.copies,
        )
        for item in results
    ]


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
