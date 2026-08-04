"""Поиск релизов через собственный Prowlarr (Torznab).

Внешних API и учёток нет: индексеры публичные, apikey локальный и генерится
``install.sh`` (§3 ТЗ). Модуль возвращает сырую выдачу; смысл ей придаёт
:mod:`torrcast.parse`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

from torrcast import InfraError, NotFoundError
from torrcast.parse import Release, parse_release_name

if TYPE_CHECKING:
    import requests

__all__ = ["Prowlarr", "RawResult", "to_releases"]

_RESULTS_PATH: Final = "/api/v2.0/indexers/all/results"
_TIMEOUT: Final = 20.0


@dataclass(frozen=True, slots=True)
class RawResult:
    """Строка выдачи Torznab до разбора имени."""

    title: str
    magnet: str
    size: int = 0
    seeders: int = 0
    indexer: str = ""

    @classmethod
    def from_json(cls, item: dict[str, Any]) -> RawResult | None:
        """Собрать результат из ответа Prowlarr; без magnet строка бесполезна."""
        magnet = str(item.get("magnetUrl") or item.get("guid") or "")
        if not magnet.startswith("magnet:"):
            return None
        return cls(
            title=str(item.get("title", "")),
            magnet=magnet,
            size=int(item.get("size") or 0),
            seeders=int(item.get("seeders") or 0),
            indexer=str(item.get("indexer", "")),
        )


class Prowlarr:
    """Тонкий клиент Torznab-эндпоинта Prowlarr."""

    def __init__(self, base_url: str, apikey: str, timeout: float = _TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.apikey = apikey
        self.timeout = timeout
        self._session: requests.Session | None = None

    def search(self, query: str) -> list[RawResult]:
        """Найти раздачи по запросу.

        :raises InfraError: Prowlarr недоступен или ответил не тем.
        :raises NotFoundError: запрос отработал, но выдача пуста.
        """
        url = f"{self.base_url}{_RESULTS_PATH}?apikey={quote(self.apikey)}&query={quote(query)}"
        payload = self._get_json(url)
        if not isinstance(payload, list):
            raise InfraError("Prowlarr вернул неожиданный ответ")
        results = [r for r in (RawResult.from_json(i) for i in payload if isinstance(i, dict)) if r]
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
            raise InfraError(f"Prowlarr не отвечает ({self.base_url}): {exc}") from exc
        except ValueError as exc:
            raise InfraError("Prowlarr вернул не JSON") from exc


def to_releases(results: list[RawResult]) -> list[Release]:
    """Разобрать сырую выдачу в релизы, перенеся размер, сиды и magnet."""
    releases: list[Release] = []
    for item in results:
        parsed = parse_release_name(item.title)
        releases.append(
            Release(
                raw_name=parsed.raw_name,
                title=parsed.title,
                original=parsed.original,
                year=parsed.year,
                quality=parsed.quality,
                codec=parsed.codec,
                voices=parsed.voices,
                size=item.size,
                seeders=item.seeders,
                magnet=item.magnet,
                indexer=item.indexer,
                kind=parsed.kind,
            )
        )
    return releases
