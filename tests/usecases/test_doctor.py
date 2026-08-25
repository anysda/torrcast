"""Сценарий doctor сообщает все проверки и итог."""

from dataclasses import dataclass

from tests.fakes.configuration_source import FakeConfigurationSource
from tests.fakes.console import FakeConsole
from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.domain.indexer_health import CORE_INDEXERS
from torrcast.domain.settings import Settings
from torrcast.usecases.doctor import Doctor, _cache, _mdns


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
    """Среда, в которой отвечают все: тогда видно полный набор строк по порядку.

    Здоровая машина - это та, где заведены ОБА опорных источника (TC-697): доктор
    отчитывается по каждому из них своей строкой.
    """
    return FakeHealthEnvironment(
        payloads={
            "health": [],
            "indexer": [
                {"id": number, "name": name, "enable": True}
                for number, name in enumerate(CORE_INDEXERS, start=7)
            ],
            "indexerstatus": [],
        }
    )


def test_checkup_keeps_every_probe_and_their_order() -> None:
    """Порядок проб - часть договора: сначала консоль, потом службы, потом ТВ."""
    lines = list(Doctor.checkup(_config(), _answering()))

    assert len(lines) == 19, [line for line, _ in lines]
    assert "терминал" in lines[0][0] and "локаль" in lines[1][0] and "ffmpeg" in lines[2][0]
    assert "Prowlarr ходит к трекерам по IPv4" in lines[3][0]
    assert "индексеров 2" in lines[4][0]
    # По строке живой пробы и по строке опорного на каждого: их два, и молчит доктор ни
    # о ком (TC-697 - установка при отказе отправляет человека смотреть именно сюда).
    assert "Knaben ответил" in lines[5][0] and "RuTor ответил" in lines[6][0]
    assert "Knaben на месте" in lines[7][0] and "RuTor на месте" in lines[8][0]
    assert "TorrServer" in lines[9][0] and "кэша неизвестен" in lines[10][0]
    assert "ТВ 10.0.0.50" in lines[11][0] and "порт 8009" in lines[12][0]
    # 🔴 TC-503. Аптайм и связь идут сразу за портом: приёмник спрашивается один раз.
    assert "приёмник" in lines[13][0]
    assert "тишина" in lines[14][0] and "профиль приёмника" in lines[15][0]
    assert "раздача" in lines[16][0] and "кэши в" in lines[17][0] and "след" in lines[18][0]


def test_a_checkup_of_a_healthy_machine_stays_passing() -> None:
    """Ни одной красной строки: «внимание» вердикт не валит."""
    assert all(ok for _, ok in Doctor.checkup(_config(), _answering()))


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


def test_an_unreadable_torrserver_does_not_fail_the_checkup() -> None:
    """Молчащий TorrServer - это «внимание»: про него уже сказала строка выше.

    Красной строкой тут доктор жаловался бы дважды на одну и ту же беду.
    """
    line, ok = _cache(_config(), FakeHealthEnvironment(settings=None))

    assert ok and "неизвестен" in line, line


def test_a_cache_that_leaves_no_room_for_the_warmup_is_bad() -> None:
    """Раздел, где кэшу место есть, а прогреву уже нет, - это «плохо».

    Обещание «показ переживает обрыв» держат оба сразу, и кэш, съевший раздел, ломает
    его ровно так же, как отсутствие кэша: место под прогрев считается сверх кэша.
    """
    environment = FakeHealthEnvironment(
        settings={"CacheSize": 4 * 1024**3, "UseDisk": True, "TorrentsSavePath": "/кэш"},
        free=30 * 1024**3,
    )

    line, ok = _cache(_config(), environment)

    assert not ok, f"30 ГиБ на раздел под кэш и прогрев - этого не хватает: {line}"
    assert "прогреву места не остаётся" in line, line


def test_what_the_warming_already_took_is_not_asked_of_the_partition_twice() -> None:
    """🔴 TC-725. Свободное место раздела уже не содержит того, что прогрев занял.

    Тот же раздел, что и в пробе выше, и то же свободное место - но половина бюджета
    прогрева на нём уже лежит, и просить её у раздела второй раз значит объявить
    здоровую машину больной. Ценой этой ошибки был не отчёт: установка тем же
    вычитанием получала под кэш ноль и уводила его в память, где служба весит вдвое
    против кэша (замер стенда: 5.9 ГиБ при 8 ГБ у машины вместо 104 МиБ на диске).
    """
    environment = FakeHealthEnvironment(
        settings={"CacheSize": 4 * 1024**3, "UseDisk": True, "TorrentsSavePath": "/кэш"},
        free=30 * 1024**3,
        warmed=15 * 1024**3,
    )

    line, ok = _cache(_config(), environment)

    assert ok, f"занятое прогревом посчитано дважды: {line}"


def test_the_receivers_heard_in_the_air_are_named_in_the_line() -> None:
    """Эфир ответил - в строке имена: они и есть весь смысл mDNS.

    Адреса найдёт и обход подсетей; имён взять больше неоткуда, и без них человек
    выбирает телевизор по номеру в сети.
    """
    environment = FakeHealthEnvironment(heard=(["Samsung Q70D"], "", ""))

    line, ok = _mdns(environment)

    assert ok and line.startswith("ок"), line
    assert "Samsung Q70D" in line
