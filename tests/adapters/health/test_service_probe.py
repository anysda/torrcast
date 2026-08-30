"""Проверяет пробы служб: отказ вокруг становится значением, а не исключением."""

import pytest

from torrcast.adapters.health.service_probe import ServiceProbe
from torrcast.domain.config import Config


def test_the_cast_port_is_the_one_the_search_knows() -> None:
    """Порт приёмника берётся у поиска, а не пишется числом второй раз."""
    assert ServiceProbe.cast_port() == 8009


def test_a_named_base_is_taken_as_is_without_any_network() -> None:
    """Заданный руками адрес раздачи перебивает всё - маршрут для него не нужен."""
    assert ServiceProbe.hls_base(Config(hls_base_url="http://10.0.0.7:8080/")) == (
        "http://10.0.0.7:8080",
        "",
    )


def test_a_base_without_a_tv_comes_back_as_a_reason() -> None:
    """Адрес не собрался - проба отвечает причиной, а вердикт выносит домен."""
    base, error = ServiceProbe.hls_base(Config(tv=""))
    assert base == "" and "no route" in error, error


@pytest.mark.machine
def test_a_closed_port_is_a_readable_refusal() -> None:
    """Отказ соединения должен доехать до человека словами, а не трейсбеком."""
    assert ServiceProbe.port_error("127.0.0.1", 1, 1.0) != ""


@pytest.mark.machine
def test_a_dead_address_answers_none_to_every_network_probe() -> None:
    """Молчание службы - это ``None`` у каждой пробы, а не исключение наружу."""
    dead = "http://127.0.0.1:1"
    assert ServiceProbe.get_json(f"{dead}/api", {}, 1.0) is None
    assert ServiceProbe.torrserver_echo(dead, 1.0) is None
    assert ServiceProbe.torrserver_settings(dead, 1.0) is None
    assert ServiceProbe.search_titles(dead, "x" * 32, 7, "matrix", 1.0) is None
