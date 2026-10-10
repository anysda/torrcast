"""Обращается к TorrServer и ждёт метаданные раздачи через порт часов."""

import threading
from functools import partial
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from torrcast.adapters.system_clock import CLOCK
from torrcast.adapters.torrserver.add_once import add_once
from torrcast.adapters.torrserver.cache_readers import cache_readers
from torrcast.adapters.torrserver.describer import DESCRIBER
from torrcast.adapters.torrserver.disconnect_timeout import disconnect_timeout
from torrcast.adapters.torrserver.echoed import PROBE_TIMEOUT, echoed
from torrcast.adapters.torrserver.engine_restart import ENGINE
from torrcast.adapters.torrserver.file_stats import file_stats
from torrcast.adapters.torrserver.reading import Stop, reading
from torrcast.adapters.torrserver.restart_recovery import RECOVERY
from torrcast.adapters.torrserver.wait_files import wait_files
from torrcast.adapters.torrserver.warmup import Warmup
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.why import why
from torrcast.ports.clock import Clock

# Договор отсрочки - порт: она приходит от сценария, и знать надо обещанное порту. Реализация
# читает часы ContactWait; по ней «отсрочка с часами» отличается от числа секунд.
from torrcast.ports.contact_wait import ContactWait as ContactWaitPort

if TYPE_CHECKING:
    import requests


class TorrServer:
    """HTTP-клиент движка раздач с прежними таймаутами и обработкой ошибок."""

    def __init__(self, base_url: str, timeout: float = 30.0, clock: Clock | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.clock = clock or CLOCK
        self._session: requests.Session | None = None

    def add(self, magnet: str) -> str:
        payload = add_once(self._post, magnet)
        if not isinstance(payload, dict):
            raise ServerDownError(phrase("torrserver.unexpected_answer_add"))
        torrent_hash = str(payload.get("hash", ""))
        if not torrent_hash:
            raise ServerDownError(phrase("torrserver.no_hash"))
        RECOVERY.remember(torrent_hash, magnet)
        DESCRIBER.later(self.base_url, torrent_hash)  # описание без пиров, если есть .torrent
        return torrent_hash

    def warm(self, magnet: str) -> Warmup:
        warmup = Warmup(magnet=magnet, clock=self.clock)
        thread = threading.Thread(target=self._warm, args=(warmup,), daemon=True)
        warmup.thread = thread
        thread.start()
        return warmup

    def _warm(self, warmup: Warmup) -> None:
        try:
            warmup.torrent_hash = self.add(warmup.magnet)
        except InfraError as exc:
            warmup.error = exc

    def status(self, torrent_hash: str) -> dict[str, Any]:
        payload = self._post("/torrents", {"action": "get", "hash": torrent_hash})
        if not isinstance(payload, dict):
            raise ServerDownError(phrase("torrserver.unexpected_answer_files"))
        return payload

    def cache(self, torrent_hash: str) -> dict[str, Any]:
        payload = self._post("/cache", {"action": "get", "hash": torrent_hash})
        if not isinstance(payload, dict):
            raise ServerDownError(phrase("torrserver.unexpected_answer_cache"))
        return payload

    def files(self, torrent_hash: str) -> list[TorrFile]:
        return file_stats(self.status(torrent_hash))

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float | ContactWaitPort = 0.0
    ) -> list[TorrFile]:
        return wait_files(self.status, torrent_hash, timeout, grace, self.clock)

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"{self.base_url}/stream?link={quote(torrent_hash)}&index={index}&play"

    def alive(self) -> bool:
        import requests

        self._session = self._session or requests.Session()
        return echoed(self._session, self.base_url)

    def reading(self, stop: Stop) -> bool | None:
        return reading(lambda path, body: self._ask(path, body, True, PROBE_TIMEOUT), stop)

    def disconnect_timeout(self) -> float:
        return disconnect_timeout(self.base_url, self._post)

    def listed(self, torrent_hash: str) -> bool:
        return torrent_hash.casefold() in self.hashes()

    def hashes(self) -> set[str]:
        """Хэши всех раздач в базе службы, закрытые (``drop``) тоже, в нижнем регистре."""
        payload = self._post("/torrents", {"action": "list"})
        if not isinstance(payload, list):
            raise ServerDownError(phrase("torrserver.unexpected_answer_list"))
        return {str(i["hash"]).casefold() for i in payload if isinstance(i, dict) and i.get("hash")}

    def drop(self, torrent_hash: str) -> bool:
        return self._close("rem", torrent_hash)

    def park(self, torrent_hash: str) -> bool:
        """Закрыть раздачу, кэш на диске оставить: ``drop`` службы, в отличие от ``rem``."""
        return self._close("drop", torrent_hash)

    def _close(self, action: str, torrent_hash: str) -> bool:
        def idle() -> bool:
            return cache_readers(self._post, torrent_hash) == 0

        RECOVERY.forget(torrent_hash)
        remove = partial(self._torrent_action, action, torrent_hash)
        return DESCRIBER.close(torrent_hash, remove, idle)

    def _torrent_action(self, action: str, torrent_hash: str) -> bool:
        try:
            self._post("/torrents", {"action": action, "hash": torrent_hash}, json_body=False)
        except InfraError:
            return False
        return True

    def _post(self, path: str, body: dict[str, Any], json_body: bool = True) -> Any:
        ask = partial(self._ask, path, body, json_body)
        return ENGINE.answered(
            self.base_url,
            self,
            ask,
            self.timeout,
            body.get("action") == "add",
            RECOVERY.for_request(path, body, self.add),
        )

    def _ask(self, path: str, body: dict[str, Any], json_body: bool, timeout: float) -> Any:
        import requests

        self._session = self._session or requests.Session()
        try:
            with self._session.post(f"{self.base_url}{path}", json=body, timeout=timeout) as answer:
                answer.raise_for_status()
                if not json_body:
                    return None
                try:
                    return answer.json()
                except ValueError as exc:
                    raise ServerDownError(phrase("torrserver.not_json")) from exc
        except requests.RequestException as exc:
            raise ServerDownError(
                phrase("torrserver.unresponsive", base_url=self.base_url, reason=why(exc))
            ) from exc
