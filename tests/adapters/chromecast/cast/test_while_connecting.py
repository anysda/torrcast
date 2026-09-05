"""Приёмник, чей сокет 8009 переподключается: ждём его, а не роняем юнит показа."""

from __future__ import annotations

from typing import Any

import pytest
from pychromecast.error import NotConnected

from tests.adapters.chromecast.cast.wired import Device, Status, Wired
from tests.fakes.clock import FakeClock
from torrcast.adapters.chromecast.cast.receiver_link import _Link
from torrcast.adapters.chromecast.cast.receiver_settings import _Settings
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
    assert "socket is reconnecting" in said
    assert said.count("reconnecting") == 1, "строка про ожидание говорится один раз"


def test_the_wait_has_a_ceiling_and_ends_with_an_honest_refusal_not_a_crash() -> None:
    """🔴 Ретрай без потолка запрещён: занятый чужим показом приёмник «connecting» вечно.

    Потолок - :data:`_Settings.CONNECT_WAIT`, и исчерпав его, отказываем СВОИМ классом:
    отказ загрузки показ не хоронит, его поднимает лестница воскрешения уже с чистым
    соединением. Чужое исключение на этом месте командная строка перевела бы в трейсбек.
    """
    clock = FakeClock()
    receiver = _receiver(refuses=10_000, clock=clock)

    with pytest.raises(StartRefusedError, match="reconnecting for over 12 s") as caught:
        receiver._load(1272.4)

    assert CONNECTING in str(caught.value), "в отказе названо дословное слово приёмника"
    assert clock.now == receiver.CONNECT_WAIT, "ждали ровно свой потолок и ни секундой дольше"
    controller = receiver.device.media_controller
    assert isinstance(controller, _Connecting)
    assert 10_000 - controller.refuses == 13, "попыток конечное число, а не бесконечная петля"


def test_the_reconnect_schedule_is_set_by_us_and_not_taken_from_the_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Ждём на обрыве не конца обрыва, а очередной попытки коннекта - значит наше и оно.

    Замер живым сокетом на 127.0.0.1 05-09-2026: pychromecast повторяет коннект с
    удвоением паузы, на 0, ``r``, ``3r``, ``7r``, ``15r`` секундах от обрыва. При
    библиотечном умолчании ``r = 5`` это 0, 5, 15, 35, и в потолок
    :data:`_Settings.CONNECT_WAIT` попадает РОВНО ОДНА попытка: обрыв 5.5 с получал тот же
    отказ на 12.00 с, что и обрыв 25 с. Меряется тут БОЕВАЯ ПРОВОДКА, а не число в
    настройках: не дойди аргумент до библиотеки - расписание осталось бы её собственным,
    и все числа рядом врали бы про покрытие.
    """
    given: dict[str, Any] = {}

    class _Made(Device):
        """Устройство, каким его отдаёт библиотека: с ``wait`` и разбором ответов."""

        def __init__(self) -> None:
            super().__init__()
            self.media_controller._process_media_status = lambda data: None  # type: ignore[attr-defined]

        def wait(self, timeout: float = 0.0) -> None:
            del timeout

    def connect(host: Any, **rest: Any) -> Any:
        del host
        given.update(rest)
        return _Made()

    monkeypatch.setattr("pychromecast.get_chromecast_from_host", connect)
    receiver = _Link("10.0.0.50")

    receiver._device()

    assert given.get("retry_wait") == receiver.RECONNECT_PACE, (
        "паузу повтора коннекта задаём мы, иначе библиотека берёт свои 5 с"
    )


def test_the_ceiling_holds_the_fourth_reconnect_attempt_and_deliberately_not_the_fifth() -> None:
    """Потолок опирается на расписание повторов, а не на длину обрыва.

    Покрытие обрыва держит ПОСЛЕДНЯЯ попытка, уместившаяся в потолок. Четвёртая (``7r``)
    обязана уместиться с запасом хотя бы в круг опроса, иначе покрытие схлопывается на
    третью. Пятая (``15r``) не умещается намеренно: за неё платил бы лишними секундами
    черноты каждый, кому приёмник не ответит вовсе.
    """
    made = _Settings()

    assert made.CONNECT_PAUSE < made.RECONNECT_PACE, "круг опроса не имеет права проспать повтор"
    assert 7 * made.RECONNECT_PACE + made.CONNECT_PAUSE <= made.CONNECT_WAIT, (
        "четвёртая попытка коннекта обязана попасть в потолок, и с запасом на круг опроса"
    )
    assert 15 * made.RECONNECT_PACE > made.CONNECT_WAIT, (
        "пятая попытка потолком не покупается: она стоит дороже, чем приносит"
    )


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
