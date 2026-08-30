"""Приёмник, чей сокет 8009 переподключается: ждём его, а не роняем юнит показа."""

from __future__ import annotations

from typing import Any

import pytest
from pychromecast.error import NotConnected

from tests.adapters.chromecast.cast.wired import Device, Status, Wired
from tests.fakes.clock import FakeClock
from torrcast.adapters.chromecast.cast.while_connecting import _while_connecting
from torrcast.cli.answered import answered
from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install

#: Дословно то, чем отвечает pychromecast на команду в переподключающийся сокет
#: (``socket_client.py``); замер на стенде 30-08-2026 - этой строкой юнит показа и умер.
CONNECTING = "Chromecast 192.168.1.90:8009 is connecting..."


class _Connecting:
    """Медиаконтроллер приёмника, чей сокет 8009 переподключается ``refuses`` раз."""

    def __init__(self, refuses: int, status: Status | None = None) -> None:
        self.refuses = refuses
        self.status = status if status is not None else Status(state="IDLE")
        self.loads: list[float] = []

    def play_media(self, url: str, kind: str, **rest: Any) -> None:
        del url, kind
        if self.refuses:
            self.refuses -= 1
            raise NotConnected(CONNECTING)
        self.loads.append(float(rest["current_time"]))

    def block_until_active(self, timeout: float = 0.0) -> None:
        del timeout

    def update_status(self) -> None:
        return None


def _receiver(refuses: int, clock: FakeClock | None = None) -> Wired:
    device = Device()
    device.media_controller = _Connecting(refuses)  # type: ignore[assignment]
    made = Wired(device=device, clock=clock if clock is not None else FakeClock())
    made._url, made._title = "http://дом/поток.m3u8", "Моана"
    return made


def test_a_reconnecting_socket_is_waited_out_and_the_command_still_goes_through(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Приёмник, который «is connecting», через секунду-другую готов - ждём его.

    Замер на стенде 30-08-2026: сокет 8009 живёт дольше одной серии (между сериями
    приложение приёмника не закрывается), и на стыке он оказался в переподключении.
    """
    clock = FakeClock()
    receiver = _receiver(refuses=2, clock=clock)

    receiver._load(1272.4)

    controller = receiver.device.media_controller
    assert isinstance(controller, _Connecting)
    assert controller.loads == [1272.4], "LOAD дошёл до приёмника, а не сгорел на отказе"
    assert clock.sleeps == [receiver.CONNECT_PAUSE] * 2
    said = capsys.readouterr().out
    assert "сокет приёмника переподключается" in said
    assert said.count("переподключается") == 1, "строка про ожидание говорится один раз"


def test_the_wait_has_a_ceiling_and_ends_with_an_honest_refusal_not_a_crash() -> None:
    """🔴 Ретрай без потолка запрещён: занятый чужим показом приёмник «connecting» вечно.

    Потолок - :data:`_Settings.CONNECT_WAIT`, и исчерпав его, отказываем СВОИМ классом:
    отказ загрузки показ не хоронит, его поднимает лестница воскрешения уже с чистым
    соединением. Чужое исключение на этом месте командная строка перевела бы в трейсбек.
    """
    clock = FakeClock()
    receiver = _receiver(refuses=10_000, clock=clock)

    with pytest.raises(StartRefusedError, match="переподключается дольше 12 с") as caught:
        receiver._load(1272.4)

    assert CONNECTING in str(caught.value), "в отказе названо дословное слово приёмника"
    assert clock.now == receiver.CONNECT_WAIT, "ждали ровно свой потолок и ни секундой дольше"
    controller = receiver.device.media_controller
    assert isinstance(controller, _Connecting)
    assert 10_000 - controller.refuses == 7, "попыток конечное число, а не бесконечная петля"


def test_a_failure_that_is_not_a_reconnect_goes_out_untouched() -> None:
    """Ловится РОВНО ``NotConnected``: чужой отказ тут глушить значило бы стирать признак."""
    receiver = _receiver(refuses=0)

    def burst() -> None:
        raise RuntimeError("ТВ выдернули из розетки")

    with pytest.raises(RuntimeError, match="из розетки"):
        _while_connecting(receiver, "LOAD", burst)


def test_a_reconnecting_socket_does_not_end_the_session_with_an_unhandled_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 Сторож стоит против того самого падения: код 1 и трейсбек на стыке серий.

    Дословно из журнала стенда 30-08-2026::

        pychromecast.error.NotConnected: Chromecast 192.168.1.90:8009 is connecting...
        torrcast-play.service: Main process exited, code=exited, status=1/FAILURE

    ``NotConnected`` командной строке не родня (:class:`TorrcastError`), поэтому она его
    не ловила вовсе: исключение уходило в трейсбек, а процесс - кодом 1. Меряется тут
    именно НЕОБРАБОТАННОСТЬ: сорвись лечение - и :func:`answered` не вернёт ничего,
    а бросит, потому что бросать наружу тут больше нечему.
    """
    install(Silent())
    receiver = _receiver(refuses=10_000)

    def show() -> int:
        receiver.play("http://дом/поток.m3u8", "Моана")
        return EXIT_OK

    code = answered(show)

    assert code == EXIT_INFRA, "отказ инфраструктуры, а не «не найдено» и не трейсбек"
    assert code != EXIT_NOT_FOUND
    assert CONNECTING in capsys.readouterr().err, "человеку сказано, чем именно отказал ТВ"
