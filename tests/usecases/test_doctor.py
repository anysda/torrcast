"""Сценарий doctor сообщает все проверки и итог."""

from dataclasses import dataclass

from tests.fakes.configuration_source import FakeConfigurationSource
from tests.fakes.console import FakeConsole
from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.domain.settings import Settings
from torrcast.usecases.doctor import (
    _INDEXER_TIMEOUT,
    _TIMEOUT,
    Doctor,
    _cache,
    _live_indexers,
    _probe_indexer,
    _prowlarr,
)


@dataclass
class FakeHealthChecks:
    lines: list[tuple[str, bool]]

    def check(self, settings: Settings) -> list[tuple[str, bool]]:
        assert settings.tv == "192.0.2.1"
        return self.lines


def test_doctor_prints_success() -> None:
    console = FakeConsole()
    doctor = Doctor(
        FakeConfigurationSource(Settings(tv="192.0.2.1")),
        FakeHealthChecks([("ок      ffmpeg", True)]),
        console,
    )

    assert doctor.run() == 0
    assert console.messages == ["ок      ffmpeg", "", "всё в порядке"]


def test_doctor_counts_failed_checks() -> None:
    console = FakeConsole()
    doctor = Doctor(
        FakeConfigurationSource(Settings(tv="192.0.2.1")),
        FakeHealthChecks([("плохо   ffmpeg", False), ("плохо   ТВ", False)]),
        console,
    )

    assert doctor.run() == 2
    assert console.messages[-1] == "проблем: 2 - смотри строки «плохо» выше"


def _config() -> Settings:
    return Settings(tv="10.0.0.50", prowlarr_apikey="x" * 32)


def _answering() -> FakeHealthEnvironment:
    """Среда, в которой отвечают все: тогда видно полный набор строк по порядку."""
    return FakeHealthEnvironment(
        payloads={
            "health": [],
            "indexer": [{"id": 7, "name": "Knaben", "enable": True}],
            "indexerstatus": [],
        }
    )


def test_checkup_keeps_every_probe_and_their_order() -> None:
    """Порядок проб - часть договора: сначала консоль, потом службы, потом ТВ."""
    lines = list(Doctor.checkup(_config(), _answering()))

    assert len(lines) == 16, [line for line, _ in lines]
    assert "терминал" in lines[0][0] and "локаль" in lines[1][0] and "ffmpeg" in lines[2][0]
    assert "Prowlarr ходит к трекерам по IPv4" in lines[3][0]
    assert "индексеров 1" in lines[4][0] and "Knaben" in lines[6][0]
    assert "TorrServer" in lines[7][0] and "кэша неизвестен" in lines[8][0]
    assert "ТВ 10.0.0.50" in lines[9][0] and "порт 8009" in lines[10][0]
    assert "тишина" in lines[11][0] and "профиль приёмника" in lines[12][0]
    assert "раздача" in lines[13][0] and "кэши в" in lines[14][0] and "след" in lines[15][0]


def test_a_checkup_of_a_healthy_machine_stays_passing() -> None:
    """Ни одной красной строки: «внимание» вердикт не валит."""
    assert all(ok for _, ok in Doctor.checkup(_config(), _answering()))


def test_prowlarr_is_asked_in_the_agreed_order() -> None:
    """Сначала здоровье, потом список, потом паузы: пустой ключ обрывает всё раньше."""
    environment = _answering()
    lines = list(_prowlarr(_config(), environment))

    assert [url.rsplit("/", 1)[-1] for url in environment.urls[:3]] == [
        "health",
        "indexer",
        "indexerstatus",
    ]
    assert [ok for _, ok in lines] == [True, True, True]
    assert environment.timeouts[0] == _TIMEOUT


def test_an_empty_apikey_costs_no_request_at_all() -> None:
    environment = _answering()
    lines = list(_prowlarr(Settings(), environment))
    assert len(lines) == 1 and not lines[0][1]
    assert environment.urls == []


def test_a_live_probe_gets_its_own_longer_patience() -> None:
    """У живого поиска терпение своё и длинное: общий короткий срок резал ответ."""
    environment = _answering()
    assert _probe_indexer(_config(), 7, "AniLibria", environment) == "irrelevant"
    assert environment.timeouts == [_INDEXER_TIMEOUT]
    assert _INDEXER_TIMEOUT > _TIMEOUT


def test_every_probed_indexer_leaves_a_line() -> None:
    environment = FakeHealthEnvironment(titles=None)
    payload = [{"id": index, "name": f"Indexer {index}", "enable": True} for index in (1, 2)]
    lines = list(_live_indexers(_config(), payload, environment))
    assert [ok for _, ok in lines] == [False, False]
    assert "Indexer 2" in lines[1][0]


def test_a_cache_in_memory_is_measured_by_the_machine() -> None:
    environment = FakeHealthEnvironment(
        settings={"CacheSize": 4 * 1024**3, "UseDisk": False}, memory=8 * 1024**3
    )
    line, ok = _cache(_config(), environment)
    assert not ok and "не влезает" in line, line


def test_a_cache_on_disk_is_measured_by_the_partition() -> None:
    """Память тут не мера: спрашивается место рядом с прогревом."""
    environment = FakeHealthEnvironment(
        settings={"CacheSize": 12 * 1024**3, "UseDisk": True, "TorrentsSavePath": "/кэш"},
        memory=1,
        free=60 * 1024**3,
    )
    line, ok = _cache(_config(), environment)
    assert ok and "на диске" in line, line
    assert environment.urls == ["/кэш"]


def test_a_cache_on_disk_without_a_path_never_touches_the_disk() -> None:
    environment = FakeHealthEnvironment(settings={"CacheSize": 1, "UseDisk": True})
    line, ok = _cache(_config(), environment)
    assert not ok and "путь не задан" in line, line
    assert environment.urls == []
