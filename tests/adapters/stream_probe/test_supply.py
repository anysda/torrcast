"""Расспрос источника: чем именно болен показ и возврат раздачи магнитом с трекерами."""

from __future__ import annotations

import time
from typing import Any

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


#: Длительность и размер выбраны так, чтобы нужная скорость вышла ровно 17.81 Мбит/с -
#: как в следе стенда `.136` за 03-09-2026, на котором снят приговор здоровому рою.
_DUR = 2000.0
_SIZE = int(17.81 * 1_000_000 / 8 * _DUR)
#: Дословный приговор рою из того же следа.
_THIN = "the swarm delivers 0.20 Mbit/s against the needed 17.81 Mbit/s - supply is short (0.01x)"


class _Session:
    """Служба, отвечающая ПО СЦЕНАРИЮ сеанса: замер за замером, последний - навсегда.

    Последний повторяется не для удобства: после того как показ сдался, тянуть перестали,
    и служба показывает эту же упавшую скорость на каждый следующий вопрос - в том числе
    на все посмертные (:data:`SOURCE_TRIES`).
    """

    def __init__(self, mbits: list[float]) -> None:
        self.mbits, self.asked = mbits, 0

    def alive(self) -> bool:
        return True

    def listed(self, torrent_hash: str) -> bool:
        return True

    def status(self, torrent_hash: str) -> dict[str, object]:
        mbit = self.mbits[min(self.asked, len(self.mbits) - 1)]
        self.asked += 1
        return {
            "download_speed": mbit * 1_000_000 / 8,
            "file_stats": [
                {"id": 0, "path": "s01e01.mkv", "length": _SIZE},
                {"id": 1, "path": "s01e02.mkv", "length": _SIZE},
            ],
        }

    def add(self, magnet: str) -> str:
        return "hash"


def _session(mbits: list[float]) -> tuple[list[str], Supply, _Tape]:
    """Прогнать сеанс из названных скоростей и вернуть ответы, источник и ленту следа."""
    tape = _Tape()
    install(tape)
    supply = Supply(server=_Session(mbits), torrent_hash="hash-1", magnet="magnet:?xt=1")
    supply.duration = _DUR
    try:
        answers = [supply.check() for _ in mbits]
    finally:
        install(Silent())
    return answers, supply, tape


def test_the_reading_taken_after_the_show_gave_up_does_not_convict_a_healthy_swarm() -> None:
    """🔴 TC-1009. Весь сеанс рой вёз втрое сверх нужного, а виноватым назвали его.

    Замер 03-09-2026 на стенде `.136`: след писал долю 2.99-3.61 (53-64 Мбит/с при нужных
    17.81), последним показанием - 0.20 Мбит/с, снятым уже после сдачи показа. Именно оно
    и уезжало человеку строкой «источник не читается».
    """
    answers, supply, tape = _session([64.3, 53.4, 57.0, 61.2, 0.20])

    assert [round(measure[0], 2) for measure in tape.measures] == [3.61, 3.0, 3.2, 3.44, 0.01]
    assert [round(value, 2) for value in tape.measures[-1][1:3]] == [0.2, 17.81]
    assert answers[-1] == "", "рой, доказавший себя за сеанс, за темноту не отвечает"
    assert supply.kept_up


def test_a_swarm_that_never_kept_up_is_still_named_out_loud() -> None:
    """Вторая ветка той же строки: рой не тянул НИ РАЗУ - приговор ему верен и остаётся."""
    answers, supply, _ = _session([0.31, 0.22, 0.18, 0.20])

    assert answers[-1] == _THIN
    assert not supply.kept_up


def test_the_window_belongs_to_the_episode_and_not_to_the_unit() -> None:
    """Источник живёт на весь юнит, а серий за ним проходит сколько угодно."""
    _, supply, _ = _session([64.3, 0.20])
    supply.file_index = 1  # следующая серия того же юнита, тот же источник

    assert supply.check() == _THIN, "здоровье прошлой серии эту не оправдывает"
    assert not supply.kept_up


def test_one_source_second_per_wall_second_is_the_named_boundary() -> None:
    supply = _supply(_Server(speed=1_000_000))
    supply.duration = 1000.0

    assert supply.check() == ""
