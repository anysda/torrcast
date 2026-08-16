"""Обращается к TorrServer и ждёт метаданные раздачи через порт часов."""

import threading
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.adapters.torrserver.warmup import Warmup
from torrcast.domain.infra_error import InfraError
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.swarm_alive import swarm_alive
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.why import why
from torrcast.ports.clock import Clock

if TYPE_CHECKING:
    import requests

META_STEP = 0.05
META_STEP_GROW = 1.5
META_STEP_MAX = 0.2
PROBE_TIMEOUT = 3.0


class _RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _file_stats(status: dict[str, Any]) -> list[TorrFile]:
    raw = status.get("file_stats")
    if not isinstance(raw, list):
        return []
    return [
        TorrFile(int(i.get("id") or 0), str(i.get("path", "")), int(i.get("length") or 0))
        for i in raw
        if isinstance(i, dict)
    ]


class TorrServer:
    """HTTP-клиент движка раздач с прежними таймаутами и обработкой ошибок."""

    def __init__(self, base_url: str, timeout: float = 30.0, clock: Clock | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.clock = clock or _RealClock()
        self._session: requests.Session | None = None

    def add(self, magnet: str) -> str:
        payload = self._post("/torrents", {"action": "add", "link": magnet, "save_to_db": False})
        if not isinstance(payload, dict):
            raise ServerDownError("TorrServer вернул неожиданный ответ на добавление")
        torrent_hash = str(payload.get("hash", ""))
        if not torrent_hash:
            raise ServerDownError("TorrServer не отдал hash раздачи")
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
            raise ServerDownError("TorrServer вернул неожиданный ответ на список файлов")
        return payload

    def cache(self, torrent_hash: str) -> dict[str, Any]:
        payload = self._post("/cache", {"action": "get", "hash": torrent_hash})
        if not isinstance(payload, dict):
            raise ServerDownError("TorrServer вернул неожиданный ответ на счётчик кэша")
        return payload

    def files(self, torrent_hash: str) -> list[TorrFile]:
        return _file_stats(self.status(torrent_hash))

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float | ContactWait = 0.0
    ) -> list[TorrFile]:
        began = self.clock.monotonic()
        deadline = began + timeout
        hopeless = began + float(grace)
        step = META_STEP
        while True:
            status = self.status(torrent_hash)
            files = _file_stats(status)
            if files:
                return files
            now = self.clock.monotonic()
            if isinstance(grace, ContactWait):
                activated = grace.activated_at
                if activated is None:
                    self.clock.sleep(min(step, META_STEP_MAX))
                    step = min(step * META_STEP_GROW, META_STEP_MAX)
                    continue
                deadline = activated + timeout
                hopeless = activated + grace.seconds
            seconds = grace.seconds if isinstance(grace, ContactWait) else grace
            if seconds > 0 and now >= hopeless and swarm_alive(status) is False:
                raise SwarmError(f"рой пуст - за {seconds:.0f} с ни одного пира")
            left = deadline - now
            if left <= 0:
                raise SwarmError(f"раздача не отдала метаданные за {timeout:.0f} с - нет пиров")
            self.clock.sleep(min(step, left))
            step = min(step * META_STEP_GROW, META_STEP_MAX)

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"{self.base_url}/stream?link={quote(torrent_hash)}&index={index}&play"

    def alive(self) -> bool:
        import requests

        if self._session is None:
            self._session = requests.Session()
        try:
            response = self._session.get(f"{self.base_url}/echo", timeout=PROBE_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException:
            return False
        return True

    def listed(self, torrent_hash: str) -> bool:
        payload = self._post("/torrents", {"action": "list"})
        if not isinstance(payload, list):
            raise ServerDownError("TorrServer вернул неожиданный ответ на список раздач")
        want = torrent_hash.casefold()
        return any(
            isinstance(item, dict) and str(item.get("hash", "")).casefold() == want
            for item in payload
        )

    def drop(self, torrent_hash: str) -> bool:
        try:
            self._post("/torrents", {"action": "rem", "hash": torrent_hash}, json_body=False)
        except InfraError:
            return False
        return True

    def remove(self, torrent_hash: str) -> bool:
        return self.drop(torrent_hash)

    def _post(self, path: str, body: dict[str, Any], json_body: bool = True) -> Any:
        import requests

        if self._session is None:
            self._session = requests.Session()
        try:
            response = self._session.post(f"{self.base_url}{path}", json=body, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ServerDownError(f"TorrServer не отвечает ({self.base_url}): {why(exc)}") from exc
        if not json_body:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ServerDownError("TorrServer вернул не JSON") from exc
