"""Сценарий doctor сообщает все проверки и итог."""

import socket
import threading
import time
from dataclasses import dataclass, field

import pytest

from tests.fakes.configuration_source import FakeConfigurationSource
from tests.fakes.console import FakeConsole
from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.domain.indexer_health import KEY_INDEXER
from torrcast.domain.settings import Settings
from torrcast.usecases.doctor import (
    _INDEXER_TIMEOUT,
    _TIMEOUT,
    Doctor,
    _cache,
    _live_indexers,
    _mdns,
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


def test_a_pause_and_a_silent_live_probe_both_reach_the_answer() -> None:
    """Флаг ``enable`` не здоровье: пауза Prowlarr и пустая живая проба обе краснят ответ.

    Строки эти приходят из разных источников - одна из статусов службы, другая из
    настоящего поиска, - и потерять любую значит объявить мёртвый индексер здоровым.
    """
    environment = FakeHealthEnvironment(
        payloads={
            "health": [],
            "indexer": [{"id": 7, "name": KEY_INDEXER, "enable": True}],
            "indexerstatus": [{"indexerId": 7, "disabledTill": "2026-08-09T12:30:00Z"}],
        },
        titles=None,
    )

    lines = list(_prowlarr(_config(), environment))

    text = "\n".join(line for line, _ in lines)
    assert f"индексер {KEY_INDEXER} отключён Prowlarr до 2026-08-09 12:30:00" in text
    assert f"индексер {KEY_INDEXER} не ответил на живой поиск - выдача неполная" in text
    assert any(not good for _, good in lines)


def test_zero_indexers_ends_the_prowlarr_leg_right_there() -> None:
    """Индексеров ноль - дальше спрашивать нечего и некого: строка одна и красная."""
    environment = FakeHealthEnvironment(payloads={"health": [], "indexer": []})

    lines = list(_prowlarr(_config(), environment))

    assert len(lines) == 1 and lines[0][1] is False
    assert [url.rsplit("/", 1)[-1] for url in environment.urls] == ["health", "indexer"]


@pytest.mark.machine
def test_the_live_probes_never_run_as_one_volley() -> None:
    """Проверка сама не имеет права перегружать общий путь индексеров залпом.

    Prowlarr отвечает третьему одновременному запросу 504 на шестнадцатой секунде, а
    после серии таких уводит индексер в бан на три часа: залп доктора лечился бы потом
    сутки. Меряется тут не число рабочих, а то, ради чего оно названо, - сколько проб
    оказалось в воздухе разом.
    """

    @dataclass
    class Counting(FakeHealthEnvironment):
        """Среда, считающая, сколько живых проб шло одновременно."""

        peak: int = 0
        inflight: int = 0
        guard: threading.Lock = field(default_factory=threading.Lock)

        def search_titles(
            self, url: str, apikey: str, indexer: int, query: str, timeout: float
        ) -> list[str] | None:
            with self.guard:
                self.inflight += 1
                self.peak = max(self.peak, self.inflight)
            time.sleep(0.05)
            with self.guard:
                self.inflight -= 1
            return super().search_titles(url, apikey, indexer, query, timeout)

    environment = Counting()
    payload = [{"id": number, "name": f"Indexer {number}", "enable": True} for number in (1, 2, 3)]

    lines = list(_live_indexers(_config(), payload, environment))

    assert len(lines) == 3
    assert environment.peak == 1, f"в воздухе оказалось проб разом: {environment.peak}"


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


def test_the_receivers_heard_in_the_air_are_named_in_the_line() -> None:
    """Эфир ответил - в строке имена: они и есть весь смысл mDNS.

    Адреса найдёт и обход подсетей; имён взять больше неоткуда, и без них человек
    выбирает телевизор по номеру в сети.
    """
    environment = FakeHealthEnvironment(heard=(["Samsung Q70D"], "", ""))

    line, ok = _mdns(environment)

    assert ok and line.startswith("ок"), line
    assert "Samsung Q70D" in line


@pytest.mark.machine
def test_a_closed_port_still_turns_the_indexer_line_red() -> None:
    """Мёртвый индексер краснеет НАСТОЯЩИМ отказом порта, а не подделанной средой.

    Остальные проверки живой пробы отвечают за индексер подделкой, поэтому честности
    доктора они не доказывают: под подделкой красным становится ровно то, что ей велели
    вернуть. Здесь порт закрыт по-настоящему, запрос уходит настоящий, и красной строку
    делает сам отказ соединения.

    Заодно снимается срок. У живого поиска терпение своё и длинное
    (:data:`torrcast.usecases.doctor._INDEXER_TIMEOUT`), а идут пробы по одной - и
    закрытый порт не имеет права выесть это терпение целиком, иначе доктор на десятке
    мёртвых индексеров встал бы на минуты вместо мгновенного отказа.
    """
    spare = socket.socket()
    spare.bind(("127.0.0.1", 0))
    dead = spare.getsockname()[1]
    spare.close()  # порт освобождён и больше никем не занят - соединение получит отказ
    settings = Settings(prowlarr_url=f"http://127.0.0.1:{dead}", prowlarr_apikey="x" * 32)

    began = time.monotonic()
    lines = list(_live_indexers(settings, [{"id": 7, "name": "RuTor", "enable": True}]))
    spent = time.monotonic() - began

    assert lines, "мёртвый индексер обязан оставить строку, а не промолчать"
    assert all(not good for _, good in lines), f"закрытый порт прошёл как здоровый: {lines}"
    assert "индексер RuTor не ответил на живой поиск" in lines[0][0]
    assert spent < _INDEXER_TIMEOUT, f"отказ порта ждали {spent:.1f} с вместо мгновенного"
