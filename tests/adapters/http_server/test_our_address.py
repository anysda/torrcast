"""Проверяет, что свой адрес называется со стороны ТВ, а не первым попавшимся."""

from __future__ import annotations

import ipaddress
import socket

import pytest

from torrcast.adapters.http_server import our_address as module


def test_without_a_receiver_there_is_no_address() -> None:
    """Адреса ТВ нет - и нашего адреса «с его стороны» тоже нет."""
    assert module.our_address("") == ""


def test_a_route_that_does_not_exist_gives_an_empty_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Маршрута до ТВ нет - отвечаем пусто, а не наугад: наугад собранная база уводит показ.

    Сокет при этом обязан закрыться: спрашивают адрес на каждом ходу показа, и утёкший
    дескриптор копится молча.
    """
    closed: list[bool] = []

    class _Dead:
        def connect(self, where: tuple[str, int]) -> None:
            raise OSError("нет маршрута")

        def getsockname(self) -> tuple[str, int]:  # pragma: no cover - до него не доходит
            raise AssertionError("имя спрашивают только после connect")

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(socket, "socket", lambda *args: _Dead())
    assert module.our_address("203.0.113.7") == ""
    assert closed == [True], "сокет не закрыт"


@pytest.mark.machine
def test_the_address_is_the_one_the_kernel_picks_for_that_route() -> None:
    """Спрашиваем ядро: ни одного пакета не уходит, а имя сокету присваивается по маршруту.

    У хоста может быть несколько интерфейсов, и показ обязан уехать в том же L2, а не
    лишним хопом через SNAT маршрутизатора.
    """
    found = module.our_address("203.0.113.7")
    if not found:
        pytest.skip("маршрута наружу нет - проверять нечего")
    assert isinstance(ipaddress.ip_address(found), ipaddress.IPv4Address), (
        f"вместо адреса нашей стороны маршрута отдано {found!r}"
    )
