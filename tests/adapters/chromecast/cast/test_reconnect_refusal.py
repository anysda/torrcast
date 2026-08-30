"""Несостоявшийся коннект: отсутствие приёмника и легшее переподключение - разные беды.

🔴 Предмет тут - не текст отказа и не его класс сам по себе, а СУДЬБА ПОКАЗА. Показ
ловит :class:`StartRefusedError` и поднимает картинку лестницей воскрешения
(:func:`torrcast.usecases.playback._play._play`); голый :class:`InfraError` идёт мимо
этого разбора и кончает юнит показа кодом возврата 2 при живом ТВ и пустом экране.

Замер на приставке 30-08-2026 (TC-916), 2 прогона из 2: сеть рвётся через 0.35 с ПОСЛЕ
ушедшего LOAD, ``NotConnected`` не приходит вовсе, показ уходит в чистое приложение - и
умирает на ``device.wait`` переподключения.
"""

from __future__ import annotations

from typing import Any

import pytest

from torrcast.adapters.chromecast.cast.receiver_link import _Link
from torrcast.adapters.chromecast.cast.receiver_talk import _Talk
from torrcast.domain.infra_error import InfraError
from torrcast.domain.start_refused_error import StartRefusedError

GONE = OSError("нет маршрута")


class _Controller:
    """Медиаконтроллер ровно в той мере, в какой его трогает ``_catch_media_error``."""

    def _process_media_status(self, data: dict[str, Any]) -> None:
        """Разбор ответа приёмника: подменяется, но по нему тут ничего не проверяют."""


class _Device:
    """Устройство pychromecast, у которого коннект уже состоялся."""

    def __init__(self) -> None:
        self.media_controller = _Controller()

    def wait(self, timeout: float = 0.0) -> None:
        """Коннект удался - ждать нечего."""

    def quit_app(self) -> None:
        """Закрытие приложения приёмника; чем оно кончилось, тут не спрашивают."""

    def disconnect(self) -> None:
        """Гашение сокета; чем оно кончилось, тут не спрашивают."""


class _Still:
    """Часы, которые не идут: выжидать паузы приёмника тесту незачем."""

    def monotonic(self) -> float:
        return 0.0

    def wall(self) -> float:
        return 0.0

    def sleep(self, seconds: float) -> None:
        """Пауза перед повтором LOAD тут ничего не сторожит."""


def _answers(monkeypatch: pytest.MonkeyPatch, *answers: object) -> None:
    """Подставить ответы ``get_chromecast_from_host`` по одному на каждый коннект."""
    given = list(answers)

    def once(*_a: object, **_k: object) -> Any:
        answer = given.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr("pychromecast.get_chromecast_from_host", once)


def test_a_receiver_that_was_never_there_buries_the_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ПЕРВЫЙ коннект не удался - приёмника нет в сети, и показывать нечем.

    ⚠️ Отрицательная сторона правила, и она обязана держаться: смягчить ЭТОТ отказ
    значило бы заставить зрителя смотреть на пустой экран весь бюджет старта ради ТВ,
    которого в сети нет вовсе.
    """
    _answers(monkeypatch, GONE)
    receiver = _Link("10.0.0.50")

    with pytest.raises(InfraError, match="не принял каст") as fell:
        receiver._device()

    assert not isinstance(fell.value, StartRefusedError), (
        "приёмника нет в сети - поднимать лестницей нечего, показ кончается тут же"
    )


def test_a_reconnect_to_a_receiver_that_answered_once_is_a_load_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ПЕРЕподключение к отвечавшему приёмнику - отказ загрузки, а не конец показа.

    🔴 Это и есть беда TC-916. Приёмник в этом показе уже отвечал, значит он есть;
    легшее соединение лечится следующей попыткой с чистым сокетом, и делает её лестница
    воскрешения. До этой правки отсюда уходил голый :class:`InfraError`, показ его не
    разбирал, и юнит кончался кодом 2 при живом ТВ.
    """
    _answers(monkeypatch, _Device(), GONE)
    receiver = _Link("10.0.0.50")
    receiver._device()  # первый коннект удался - приёмник в сети ЕСТЬ
    receiver._cast = None  # ровно это делает ``_restart_app`` перед повтором LOAD

    with pytest.raises(StartRefusedError, match="не отозвался на переподключение"):
        receiver._device()


def test_the_show_stays_reconnectable_after_the_link_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Признак связи липкий: ``_restart_app`` гасит соединение, но не факт наличия ТВ.

    Приёмник, ответивший однажды, остаётся «тем, который есть» до конца показа: иначе
    первое же чистое приложение возвращало бы показ в разряд «ТВ нет в сети», и беда
    TC-916 вернулась бы следующим повтором LOAD.
    """
    _answers(monkeypatch, _Device(), GONE, GONE)
    receiver = _Link("10.0.0.50")
    receiver._device()

    for attempt in (1, 2):
        receiver._cast = None
        with pytest.raises(StartRefusedError):
            receiver._device()
        assert receiver._linked is True, f"связь была - попытка {attempt} это не отменяет"


def test_a_clean_app_restart_does_not_forget_that_the_receiver_is_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Чистое приложение гасит соединение - и обязано оставить признак связи нетронутым.

    🔴 Тест зовёт :meth:`_Talk._restart_app` НАСТОЯЩИЙ, а не повторяет его руками. Пока
    гашение соединения изображалось в тесте присваиванием ``_cast = None``, правка внутри
    самого ``_restart_app`` (скажем, ``self._linked = False`` рядом) вернула бы беду
    TC-916 при всех зелёных тестах: отрицательный щуп по этому месту не кусался. Разница
    ровно в том, что здесь показ проходит своей дорогой.
    """
    _answers(monkeypatch, _Device(), GONE)
    receiver = _Talk("10.0.0.50", clock=_Still())
    receiver._device()

    receiver._restart_app()

    assert receiver._cast is None, "чистое приложение обязано погасить само соединение"
    assert receiver._linked is True, "приёмник отвечал - чистое приложение этого не отменяет"
    with pytest.raises(StartRefusedError, match="не отозвался на переподключение"):
        receiver._device()
