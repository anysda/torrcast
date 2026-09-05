"""Расспрос источника: чем именно болен показ и возврат раздачи магнитом с трекерами."""

from __future__ import annotations

import time
from typing import Any

from tests.fakes.swarm_session import SESSION_DUR, THIN_SWARM, SwarmSession
from torrcast.adapters.stream_probe.supply import Supply
from torrcast.domain.infra_error import InfraError
from torrcast.domain.probe_settings import META_GRACE
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install


class _Server:
    """Служба раздач ровно в том объёме, в каком её спрашивает расспрос источника."""

    def __init__(
        self, *, up: bool = True, listed: bool = True, files: bool = True, speed: int | None = None
    ) -> None:
        self.up, self.listed_, self.files_ = up, listed, files
        self.speed = speed
        self.added: list[str] = []

    def alive(self) -> bool:
        if self.up is None:
            raise InfraError("TorrServer не отвечает")
        return self.up

    def listed(self, torrent_hash: str) -> bool:
        return self.listed_

    def files(self, torrent_hash: str) -> list[object]:
        return [object()] if self.files_ else []

    def status(self, torrent_hash: str) -> dict[str, object]:
        files = [{"id": 0, "path": "film.mkv", "length": 1_000_000_000}] if self.files_ else []
        answer: dict[str, object] = {"file_stats": files}
        if self.speed is not None:
            answer["download_speed"] = self.speed
        return answer

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

    assert supply.check() == "TorrServer does not answer"
    assert supply.lost == "TorrServer does not answer", "авария запоминается до разбора"


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

    assert supply.check() == "TorrServer lost our torrent"
    assert server.added == []


def test_without_our_hash_the_supply_keeps_quiet() -> None:
    """Чужие раздачи в службе не наше дело - ни считать, ни возвращать."""
    server = _Server(up=False)

    assert Supply(server=server).check() == ""


class _Tape(Silent):
    def __init__(self) -> None:
        self.measures: list[tuple[float, float, float, bool]] = []

    def supply(self, ratio: float, got: float, need: float, enough: bool) -> None:
        self.measures.append((ratio, got, need, enough))


def test_a_live_but_thin_swarm_is_measured_named_and_written_to_the_tape() -> None:
    tape = _Tape()
    install(tape)
    supply = _supply(_Server(speed=125_000))
    supply.duration = 1000.0

    try:
        answer = supply.check()
    finally:
        install(Silent())

    expected = "the swarm delivers 1.00 Mbit/s against the needed 8.00 Mbit/s - " + (
        "supply is short (0.12x)"
    )
    assert answer == expected
    assert tape.measures == [(0.125, 1.0, 8.0, False)]


def _session(mbits: list[float]) -> tuple[list[str], Supply, _Tape]:
    """Прогнать сеанс из названных скоростей и вернуть ответы, источник и ленту следа."""
    tape = _Tape()
    install(tape)
    supply = Supply(server=SwarmSession(mbits), torrent_hash="hash-1", magnet="magnet:?xt=1")
    supply.duration = SESSION_DUR
    try:
        answers = [supply.check() for _ in mbits]
    finally:
        install(Silent())
    return answers, supply, tape


def test_a_sagging_swarm_is_named_sagging_even_after_a_healthy_session() -> None:
    """🔴 TC-1009. Источник отвечает про СЕЙЧАС: окно сеанса живой ответ не правит.

    Замер 03-09-2026 на стенде `.136`: след писал долю 2.99-3.61 (53-64 Мбит/с при нужных
    17.81), последним показанием - 0.20 Мбит/с, снятым уже после сдачи показа. Само окно
    уезжает в двух фактах (:attr:`Supply.kept_up`, :attr:`Supply.thin`), а судит ими тот,
    кто хоронит показ: на живом показе непустой ответ - это не строка, а ожидание.
    """
    answers, supply, tape = _session([64.3, 53.4, 57.0, 61.2, 0.20])

    assert [round(measure[0], 2) for measure in tape.measures] == [3.61, 3.0, 3.2, 3.44, 0.01]
    assert [round(value, 2) for value in tape.measures[-1][1:3]] == [0.2, 17.81]
    assert answers[-1] == THIN_SWARM, "просадку источник называет просадкой, показ подождёт"
    assert (supply.thin, supply.kept_up) == (True, True), "оба факта сеанса на месте"


def test_a_swarm_that_never_kept_up_leaves_the_window_without_an_alibi() -> None:
    """Вторая ветка той же строки: рой не тянул НИ РАЗУ - снимать приговор нечем."""
    answers, supply, _ = _session([0.31, 0.22, 0.18, 0.20])

    assert answers[-1] == THIN_SWARM
    assert (supply.thin, supply.kept_up) == (True, False)


def test_the_window_belongs_to_the_episode_and_not_to_the_unit() -> None:
    """Источник живёт на весь юнит, а серий за ним проходит сколько угодно."""
    _, supply, _ = _session([64.3, 0.20])
    supply.file_index = 1  # следующая серия того же юнита, тот же источник

    assert supply.check() == THIN_SWARM
    assert not supply.kept_up, "здоровье прошлой серии эту не оправдывает"


def test_a_dead_service_is_no_thin_swarm_and_leaves_the_flag_down() -> None:
    """Служба, легшая насмерть, лежит одинаково и на живом показе, и на мёртвом."""
    _, supply, _ = _session([64.3])
    supply.server = _Server(up=False)

    assert supply.check() == "TorrServer does not answer"
    assert not supply.thin, "окном сеанса эту беду снимать нечем и незачем"


def test_one_source_second_per_wall_second_is_the_named_boundary() -> None:
    supply = _supply(_Server(speed=1_000_000))
    supply.duration = 1000.0

    assert supply.check() == ""
