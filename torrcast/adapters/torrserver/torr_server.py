"""Обращается к TorrServer и ждёт метаданные раздачи через порт часов."""

import threading
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from torrcast.adapters.torrserver.add_once import add_once
from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.adapters.torrserver.disconnect_timeout import disconnect_timeout
from torrcast.adapters.torrserver.file_stats import file_stats
from torrcast.adapters.torrserver.warmup import Warmup
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.swarm_alive import swarm_alive
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.why import why
from torrcast.ports.clock import Clock

# Договор отсрочки берётся портом, а не своим классом: службе раздач она приходит от
# сценария, и знать здесь надо ровно то, что обещано порту. Часы же ведёт наша ContactWait
# выше по импорту, и по ней же отличается «отсрочка с часами» от голого числа секунд.
from torrcast.ports.contact_wait import ContactWait as ContactWaitPort

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


class TorrServer:
    """HTTP-клиент движка раздач с прежними таймаутами и обработкой ошибок."""

    def __init__(self, base_url: str, timeout: float = 30.0, clock: Clock | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.clock = clock or _RealClock()
        self._session: requests.Session | None = None

    def add(self, magnet: str) -> str:
        payload = add_once(self._post, magnet)
        if not isinstance(payload, dict):
            raise ServerDownError(phrase("torrserver.unexpected_answer_add"))
        torrent_hash = str(payload.get("hash", ""))
        if not torrent_hash:
            raise ServerDownError(phrase("torrserver.no_hash"))
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
        began = self.clock.monotonic()
        deadline = began + timeout
        hopeless = began + float(grace)
        empty_since: float | None = None
        step = META_STEP
        while True:
            status = self.status(torrent_hash)
            files = file_stats(status)
            if files:
                return files
            now = self.clock.monotonic()
            if swarm_alive(status) is False:
                empty_since = now if empty_since is None else empty_since
            else:  # хоть один контакт был - отсрочка считается заново от этой секунды
                empty_since = None
            if isinstance(grace, ContactWait):
                activated = grace.activated_at
                if activated is None:
                    self.clock.sleep(min(step, META_STEP_MAX))
                    step = min(step * META_STEP_GROW, META_STEP_MAX)
                    continue
                # 🔴 TC-739. Прогрев спрашивает рой с той секунды, как раздача добавлена,
                # а не с той, как до неё дошла очередь: своё ожидание он уже отстоял, и
                # начинать бюджеты заново значит ждать по второму разу то же самое.
                # Приговор при этом не выносится раньше вопроса: до него релиз никому не
                # мешает, и объявлять его негодным незачем.
                deadline = max(activated, began + timeout)
                hopeless = max(
                    activated, (empty_since if empty_since is not None else now) + grace.seconds
                )
            seconds = grace.seconds if isinstance(grace, ContactWait) else float(grace)
            if seconds > 0 and now >= hopeless and swarm_alive(status) is False:
                raise SwarmError(
                    phrase("torrserver.swarm_empty", seconds=f"{seconds:.0f}"), waited=seconds
                )
            left = deadline - now
            if left <= 0:
                raise SwarmError(
                    phrase("torrserver.metadata_timeout", timeout=f"{timeout:.0f}"), waited=timeout
                )
            self.clock.sleep(min(step, left))
            step = min(step * META_STEP_GROW, META_STEP_MAX)

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"{self.base_url}/stream?link={quote(torrent_hash)}&index={index}&play"

    def alive(self) -> bool:
        import requests

        if self._session is None:
            self._session = requests.Session()
        try:
            with self._session.get(f"{self.base_url}/echo", timeout=PROBE_TIMEOUT) as response:
                response.raise_for_status()
        except requests.RequestException:
            return False
        return True

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
        return self._torrent_action("rem", torrent_hash)

    def park(self, torrent_hash: str) -> bool:
        """Закрыть раздачу, кэш на диске оставить: ``drop`` службы, в отличие от ``rem``."""
        return self._torrent_action("drop", torrent_hash)

    def _torrent_action(self, action: str, torrent_hash: str) -> bool:
        try:
            self._post("/torrents", {"action": action, "hash": torrent_hash}, json_body=False)
        except InfraError:
            return False
        return True

    def _post(self, path: str, body: dict[str, Any], json_body: bool = True) -> Any:
        import requests

        if self._session is None:
            self._session = requests.Session()
        try:
            with self._session.post(
                f"{self.base_url}{path}", json=body, timeout=self.timeout
            ) as response:
                response.raise_for_status()
                if not json_body:
                    return None
                try:
                    return response.json()
                except ValueError as exc:
                    raise ServerDownError(phrase("torrserver.not_json")) from exc
        except requests.RequestException as exc:
            raise ServerDownError(
                phrase("torrserver.unresponsive", base_url=self.base_url, reason=why(exc))
            ) from exc
