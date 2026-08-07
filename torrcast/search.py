"""Поиск релизов через собственный Prowlarr: внешних API и учёток нет, индексеры
публичные, apikey локальный и генерится ``install.sh``. Модуль возвращает
сырую выдачу; смысл ей придаёт :mod:`torrcast.parse`.

⚠️ Две особенности, выясненные на живом Prowlarr 2.5.2: агрегат по всем
индексерам живёт на ``/api/v1/search``, а ``/api/v2.0/indexers/all/results`` — это
Jackett, у Prowlarr 404 (Torznab-XML отдаётся по индексеру ``/<id>/api`` и его
разбирает :func:`from_torznab` — он же путь совместимости с Jackett'ом); ``magnetUrl``
в выдаче — ссылка-прокси на сам Prowlarr, опора только ``infoHash``, magnet собираем
сами и вешаем публичные трекеры (пиры — magnet + DHT + публичные ретрекеры).
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

if TYPE_CHECKING:
    import requests

__all__ = ["PUBLIC_TRACKERS", "Prowlarr", "RawResult", "from_torznab", "magnet_for", "to_releases"]

_SEARCH_PATH: Final = "/api/v1/search"
#: Потолок ожидания выдачи. Prowlarr отдаёт её, только когда опрошены ВСЕ индексеры,
#: поэтому потолок здесь - это не «сколько ждём обычно» (обычно 1-3 с), а «сколько
#: терпим одного залипшего». Залипания замерены: живой индексер, который из консоли
#: отвечает за 0.2 с, изредка держит запрос Prowlarr около 100 с, после чего выдача
#: приходит целиком. Прежние 60 с рубили такой поиск начисто - вместе с находками
#: остальных индексеров, то есть ровно там, где ответ уже был.
_TIMEOUT: Final = 150.0
#: Кино, сериалы и «Other» — под последней RuTor отдаёт вообще всё (категорий у него нет).
_CATEGORIES: Final = (2000, 5000, 8000)
_TORZNAB_NS: Final = "{http://torznab.com/schemas/2015/feed}"
_HASH_RE: Final = re.compile(r"^[0-9a-fA-F]{40}$")
#: Сырые поля одной строки выдачи в порядке :meth:`RawResult.build`.
_Row = tuple[Any, Any, Any, Any, Any]

#: Открытые трекеры, которые мы дописываем в каждый magnet. У раздач RuTracker
#: из Knaben публичных ретрекеров нет, у RuTor нет ``tr=`` вообще — без этого
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
        self._session: requests.Session | None = None

    def search(self, query: str, limit: int = 100) -> list[RawResult]:
        """Найти раздачи во всех подключённых индексерах: :class:`InfraError` — Prowlarr
        недоступен или ответил не тем, :class:`NotFoundError` — пригодных раздач нет.
        """
        cats = "".join(f"&categories={c}" for c in _CATEGORIES)
        url = (
            f"{self.base_url}{_SEARCH_PATH}?apikey={quote(self.apikey)}"
            f"&query={quote(query)}&type=search&limit={limit}{cats}"
        )
        results = from_json(self._get_json(url))
        if not results:
            raise NotFoundError(f"по запросу «{query}» ничего не нашлось")
        return results

    def _get_json(self, url: str) -> Any:
        import requests

        if self._session is None:
            self._session = requests.Session()
        try:
            response = self._session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise InfraError(f"Prowlarr не отвечает ({self.base_url}): {why(exc)}") from exc
        except ValueError as exc:
            raise InfraError("Prowlarr вернул не JSON") from exc


def to_releases(results: list[RawResult]) -> list[Release]:
    """Разобрать сырую выдачу в релизы, перенеся размер, сиды и magnet."""
    return [
        replace(
            parse_release_name(item.title),
            size=item.size,
            seeders=item.seeders,
            magnet=item.magnet,
            indexer=item.indexer,
        )
        for item in results
    ]


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
