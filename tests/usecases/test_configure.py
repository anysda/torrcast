"""Сценарий configure сохраняет названный или найденный телевизор."""

import pytest

from tests.fakes.configuration_store import FakeConfigurationStore
from tests.fakes.console import FakeConsole
from tests.fakes.receiver_finder import FakeReceiverFinder
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.receiver_info import ReceiverInfo
from torrcast.domain.settings import Settings
from torrcast.usecases.configure import Configure


def test_configure_saves_named_mock_receiver() -> None:
    store = FakeConfigurationStore()
    console = FakeConsole()

    assert Configure(store, FakeReceiverFinder(), console).run("mock") == 0
    assert store.settings.tv == "mock"
    assert store.settings.receiver == "mock"
    assert console.messages == ["ТВ: mock (headless-приёмник, каста наружу нет)"]


def test_the_only_receiver_found_is_taken_without_a_question() -> None:
    """Найденный один приёмник берётся молча: в своей сети он чужим быть не может.

    Это то, что позволяет установке заканчиваться самой: ровно один откликнувшийся
    приёмник - он и есть телевизор, и вопрос «какой из одного» был бы ручкой ради
    ручки. Вопрос остаётся только там, где выбор настоящий, - приёмников несколько.
    """
    store = FakeConfigurationStore()
    console = FakeConsole()
    finder = FakeReceiverFinder([ReceiverInfo("Гостиная", "192.0.2.5")])

    Configure(store, finder, console).run()

    assert console.questions == [], "единственный найденный приёмник не спрашивается"
    assert store.settings.tv == "192.0.2.5"
    assert console.messages[-1] == "ТВ: Гостиная - 192.0.2.5"


def test_the_mock_receiver_leaves_no_trace_of_the_former_tv_address() -> None:
    """`cast --tv mock` - установка на машине без телевизора.

    Она обязана переключить приёмник, иначе такая машина полезла бы кастить на Chromecast.
    И обратно тоже: адрес ТВ возвращает штатный приёмник, а от прежнего значения не
    остаётся и следа.
    """
    store = FakeConfigurationStore(Settings(tv="10.0.0.50", receiver="chromecast"))
    console = FakeConsole()

    assert Configure(store, FakeReceiverFinder(), console).run("mock") == 0
    assert (store.settings.tv, store.settings.receiver) == ("mock", "mock")
    assert "headless" in console.messages[-1]

    assert Configure(store, FakeReceiverFinder(), console).run("10.0.0.50") == 0
    assert (store.settings.tv, store.settings.receiver) == ("10.0.0.50", "chromecast")


def test_the_rest_of_the_settings_survive_the_write() -> None:
    """Пишется весь конфиг, а не срез сценария: чужие поля переживают установку ТВ."""
    store = FakeConfigurationStore(Settings(prowlarr_apikey="ключ", hls_port=9999))

    Configure(store, FakeReceiverFinder(), FakeConsole()).run("10.0.0.50")

    assert store.settings.prowlarr_apikey == "ключ"
    assert store.settings.hls_port == 9999


def test_the_found_receivers_are_offered_as_a_numbered_list() -> None:
    """`cast --tv` без адреса - финал установки: список приёмников и ответ номером.

    Адрес телевизора человеку взять негде: в меню ТВ он спрятан через три экрана, а в
    роутер пускают не всех. Поэтому спрашиваем не адрес, а «какой из этих телевизоров
    твой», и в конфиг уезжает ровно то же поле, что и при заданном руками адресе.
    """
    store = FakeConfigurationStore()
    console = FakeConsole(answers=["2"])
    finder = FakeReceiverFinder(
        [ReceiverInfo("Samsung Q70D", "10.0.0.50"), ReceiverInfo("", "10.0.0.60", "Chromecast")]
    )

    assert Configure(store, finder, console).run() == 0

    listed = "\n".join(console.messages)
    assert "  1. Samsung Q70D - 10.0.0.50" in listed
    assert "  2. Chromecast - 10.0.0.60" in listed, "безымянный пункт называется моделью"
    assert (store.settings.tv, store.settings.receiver) == ("10.0.0.60", "chromecast")


def test_finding_nobody_says_why_and_keeps_the_manual_way() -> None:
    """Пустой список - не «ошибка сети», а причина и выход: ТВ выключен либо не в той сети.

    Заодно вслух говорится о подсети, которую мы не обходили: умолчать о ней - значит
    оставить человека гадать, почему его телевизор не нашёлся.
    """
    store = FakeConfigurationStore()
    console = FakeConsole()
    finder = FakeReceiverFinder(remarks=["подсеть 10.5.0.0/16 на 65534 адресов"])

    with pytest.raises(NotFoundError) as caught:
        Configure(store, finder, console).run()

    assert "10.5.0.0/16" in "\n".join(console.messages)
    refusal = str(caught.value)
    assert "включён" in refusal and "той же сети" in refusal
    assert "cast --tv <ip>" in refusal
    assert store.saved == [], "неудачный поиск конфиг не трогает"


def test_several_receivers_without_a_terminal_are_not_picked_blindly() -> None:
    """Спросить некого, а найдено несколько - молча записать первый попавшийся нельзя.

    Это ровно тот же отказ, что и в меню картин: любой дефолт тут означает чужое
    устройство в конфиге, а не оттенок выбора. Отказ обязан назвать найденное (список) и
    оставить человеку ручной путь (`cast --tv <ip>`), а не просто сказать «не выбираю».
    """
    store = FakeConfigurationStore()
    console = FakeConsole(tty=False)
    finder = FakeReceiverFinder(
        [ReceiverInfo("", "10.0.0.50"), ReceiverInfo("Гостиная", "10.0.0.60")]
    )

    with pytest.raises(NotFoundError) as caught:
        Configure(store, finder, console).run()

    listed = "\n".join(console.messages)
    assert "10.0.0.50" in listed and "Гостиная - 10.0.0.60" in listed
    assert "вслепую не выбираю" in str(caught.value)
    assert "cast --tv <ip>" in str(caught.value)
    assert store.saved == [], "отказ конфиг не трогает"
