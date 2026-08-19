"""Зеркало :mod:`torrcast.usecases.doctor_prowlarr`: пробы поиска и его индексеров."""

import socket
import threading
import time
from dataclasses import dataclass, field

import pytest

from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.domain.indexer_health import KEY_INDEXER
from torrcast.domain.settings import Settings
from torrcast.usecases.doctor_probe import _INDEXER_TIMEOUT, _TIMEOUT
from torrcast.usecases.doctor_prowlarr import _live_indexers, _probe_indexer, _prowlarr


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


@pytest.mark.machine
def test_a_closed_port_still_turns_the_indexer_line_red() -> None:
    """Мёртвый индексер краснеет НАСТОЯЩИМ отказом порта, а не подделанной средой.

    Остальные проверки живой пробы отвечают за индексер подделкой, поэтому честности
    доктора они не доказывают: под подделкой красным становится ровно то, что ей велели
    вернуть. Здесь порт закрыт по-настоящему, запрос уходит настоящий, и красной строку
    делает сам отказ соединения.

    Заодно снимается срок. У живого поиска терпение своё и длинное
    (:data:`torrcast.usecases.doctor_probe._INDEXER_TIMEOUT`), а идут пробы по одной - и
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
