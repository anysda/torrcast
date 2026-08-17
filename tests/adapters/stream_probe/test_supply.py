"""Расспрос источника: чем именно болен показ и возврат раздачи магнитом с трекерами."""

from __future__ import annotations

import time
from typing import Any

from torrcast.adapters.stream_probe.supply import Supply
from torrcast.domain.infra_error import InfraError
from torrcast.domain.probe_settings import META_GRACE


class _Server:
    """Служба раздач ровно в том объёме, в каком её спрашивает расспрос источника."""

    def __init__(self, *, up: bool = True, listed: bool = True, files: bool = True) -> None:
        self.up, self.listed_, self.files_ = up, listed, files
        self.added: list[str] = []

    def alive(self) -> bool:
        if self.up is None:
            raise InfraError("TorrServer не отвечает")
        return self.up

    def listed(self, torrent_hash: str) -> bool:
        return self.listed_

    def files(self, torrent_hash: str) -> list[object]:
        return [object()] if self.files_ else []

    def add(self, magnet: str) -> str:
        self.added.append(magnet)
        return "hash"


def _supply(server: Any, magnet: str = "magnet:?xt=1&tr=udp://tracker") -> Supply:
    return Supply(server=server, torrent_hash="hash-1", magnet=magnet)


def test_a_healthy_source_is_answered_by_silence() -> None:
    """Служба отвечает, раздача на месте, аварии за ней не числится - говорить не о чем."""
    supply = _supply(_Server())

    assert supply.check() == ""
    assert not supply.restored


def test_a_dead_service_is_named_and_not_confused_with_a_thin_swarm() -> None:
    """Разница между «просел рой» и «службы не стало» - вся разница для человека."""
    supply = _supply(_Server(up=False))

    assert supply.check() == "TorrServer не отвечает"
    assert supply.lost == "TorrServer не отвечает", "авария запоминается до разбора"


def test_a_lost_torrent_comes_back_by_the_magnet_with_its_trackers() -> None:
    """Раздача без трекеров ищет пиров одним DHT и за 25 с не приносит ни байта."""
    server = _Server(listed=False)
    supply = _supply(server)

    assert supply.check() == "", "вернули - значит источник и правда в порядке"
    assert server.added == ["magnet:?xt=1&tr=udp://tracker"]
    assert supply.restored and supply.lost == ""
    assert supply.restored_at > 0.0


def test_a_torrent_without_metadata_is_the_one_added_by_a_bare_hash() -> None:
    """Она числится в списке точно так же, как здоровая, - отличают её метаданные."""
    server = _Server(files=False)
    supply = _supply(server)

    assert supply.check() == ""
    assert server.added, "раздачу вернули магнитом"


def test_a_torrent_just_restored_is_given_its_grace() -> None:
    """Метаданные после возврата ещё едут, и второй возврат подряд был бы вознёй впустую."""
    server = _Server(files=False)
    supply = _supply(server)
    supply.restored_at = time.monotonic()
    supply.lost = ""

    assert supply.check() == ""
    assert server.added == [], "внутри отсрочки раздачу не переоткрывают"
    assert META_GRACE > 0.0


def test_without_a_magnet_there_is_nothing_to_restore_from() -> None:
    """Магнит берётся из записи картины и ниоткуда больше: ходить в индексеры посреди
    аварии - второй способ не показать кино."""
    server = _Server(listed=False)
    supply = _supply(server, magnet="")

    assert supply.check() == "TorrServer потерял нашу раздачу"
    assert server.added == []


def test_without_our_hash_the_supply_keeps_quiet() -> None:
    """Чужие раздачи в службе не наше дело - ни считать, ни возвращать."""
    server = _Server(up=False)

    assert Supply(server=server).check() == ""
