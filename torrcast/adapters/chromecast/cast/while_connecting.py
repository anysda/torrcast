"""Команда приёмнику, чей сокет 8009 ещё переподключается: подождать, а не упасть.

Зовёт его LOAD (:meth:`torrcast.adapters.chromecast.cast.receiver_talk._Talk._load`) -
единственный разговор с приёмником, которому отказ «is connecting» стоит всего показа."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.chromecast.cast.receiver_state import _State
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.why import why


def _connecting(exc: BaseException) -> bool:
    """Это ли отказ ``NotConnected`` - «сокет 8009 ещё переподключается».

    Класс спрашивается у самой библиотеки, а не по тексту сообщения и не по имени типа:
    переименуй его pychromecast - и разбор обязан сломаться громко, тестом, а не тихо
    пропустить то самое исключение, ради которого он поставлен. Импорт ленивый по той же
    причине, что и в :meth:`torrcast.adapters.chromecast.cast.receiver_link._Link._device`:
    pychromecast тянет за собой zeroconf, и платить за него на импорте пакета незачем.
    """
    from pychromecast.error import NotConnected

    return isinstance(exc, NotConnected)


def _while_connecting(rcv: _State, what: str, do: Callable[[], None]) -> None:
    """Сказать приёмнику ``do``, пережидая переподключение его сокета 8009.

    ``what`` - что именно говорим приёмнику; уезжает и в строку ожидания, и в отказ.

    🔴 Зачем это вообще. Сокет 8009 живёт дольше одной серии: между сериями показ
    приложение приёмника не закрывает (:func:`torrcast.adapters.chromecast.cast.stop._stop`),
    и следующая серия грузится в то же соединение. Соединение это к моменту стыка вправе
    оказаться в переподключении - тогда pychromecast отвечает на любую команду
    ``NotConnected``. Замер на стенде 30-08-2026: ровно так и вышло, только необработанным
    исключением - юнит показа кончился кодом 1, а приёмник остался пустым. Приёмник,
    который «is connecting», через секунду-другую готов, и хоронить показ тут не за что.

    🔴 Потолок ожидания - :data:`_State.CONNECT_WAIT`, и он обязателен: приёмник, занятый
    чужим показом, отвечал бы «is connecting» бесконечно. Исчерпав его, отказываем честно
    и своим классом (:class:`torrcast.domain.start_refused_error.StartRefusedError`): это
    отказ ЗАГРУЗКИ, показ им не хоронится, а поднимается лестницей воскрешения - уже с
    чистым соединением (:func:`torrcast.adapters.chromecast.cast.replay._replay`). Наружу
    при этом уходит наша ошибка, которую командная строка переводит в код возврата, а не
    чужое исключение, которое она переводит в трейсбек.

    ⚠️ Молчать это ожидание не имеет права: пустой экран без строки - та же беда в другой
    обёртке. Строка говорится один раз на ожидание, а не на каждую попытку.

    ⚠️ Ловится РОВНО ``NotConnected``. Любой другой отказ уходит наружу нетронутым: у
    него своя причина и своё лечение, и глушить его здесь значило бы стирать признак.
    """
    deadline = rcv.clock.monotonic() + rcv.CONNECT_WAIT
    said = False
    while True:
        try:
            do()
        except Exception as exc:
            if not _connecting(exc):
                raise
            if rcv.clock.monotonic() >= deadline:
                raise StartRefusedError(
                    phrase(
                        "chromecast_talk.reconnect_timeout",
                        address=rcv.address,
                        timeout=f"{rcv.CONNECT_WAIT:.0f}",
                        what=what,
                        reason=why(exc),
                    )
                ) from exc
            if not said:
                said = True
                print(
                    phrase(
                        "chromecast_talk.reconnect_wait",
                        timeout=f"{rcv.CONNECT_WAIT:.0f}",
                        what=what,
                    ),
                    flush=True,
                )
            rcv.clock.sleep(rcv.CONNECT_PAUSE)
        else:
            return
