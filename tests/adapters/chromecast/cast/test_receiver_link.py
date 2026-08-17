"""Соединение и статус: свежесть обязательна, а закрытый приёмник трогать нельзя."""

from __future__ import annotations

from typing import Any

import pytest

from tests.adapters.chromecast.cast.wired import Controller, Device, Status, Wired
from torrcast.adapters.chromecast.cast.receiver_link import _Link
from torrcast.domain.infra_error import InfraError


class _Counting(Controller):
    """Медиаконтроллер, который считает, сколько раз у него просили свежий статус."""

    def __init__(self) -> None:
        super().__init__()
        self.refreshed = 0

    def update_status(self) -> None:
        self.refreshed += 1


def _device(app: str = "CC1AD845") -> Device:
    made = Device(app=app)
    made.media_controller = _Counting()
    return made


def test_the_status_is_refreshed_because_a_stale_one_freezes_the_show() -> None:
    """Без ``update_status`` pychromecast отдаёт последний присланный статус.

    Позиция тогда замирает навсегда: сторож считает, что показ стоит, окно сегментов не
    чистится, и tmpfs растёт до конца фильма.
    """
    receiver = Wired(device=_device())

    receiver._status()

    controller = receiver.device.media_controller
    assert isinstance(controller, _Counting)
    assert controller.refreshed == 1


def test_a_foreign_app_is_not_touched_because_asking_would_reopen_it() -> None:
    """На закрытом ресивере ``update_status`` ПЕРЕЗАПУСКАЕТ пустой Default Media Receiver.

    «Вышел в Home, а каст открылся снова» - ровно это и происходило, поэтому чужой
    ``app_id`` проверяется раньше, а статус не трогается вовсе.
    """
    receiver = Wired(device=_device(app="чужое"))

    receiver._status()

    controller = receiver.device.media_controller
    assert isinstance(controller, _Counting)
    assert controller.refreshed == 0


def test_the_reason_of_a_refusal_names_the_state_and_the_code() -> None:
    """Строку читает человек в журнале показа: без кода отказ не отличить от отказа."""
    receiver = Wired()
    receiver.device.media_controller.status = Status(state="IDLE", idle_reason="ERROR")

    assert receiver._why() == "IDLE/ERROR"

    receiver._error_code = 905
    assert receiver._why() == "IDLE/ERROR, код 905"


def test_a_receiver_that_is_not_there_is_named_by_a_human_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Приёмника нет в сети - это понятная беда инфраструктуры, а не трассировка."""

    def refuse(*_a: object, **_k: object) -> Any:
        raise OSError("нет маршрута")

    monkeypatch.setattr("pychromecast.get_chromecast_from_host", refuse)
    receiver = _Link("10.0.0.50")

    with pytest.raises(InfraError, match="не принял каст"):
        receiver._device()


def test_the_error_code_of_a_dead_session_is_taken_before_the_answer_is_parsed() -> None:
    """pychromecast не переносит ``detailedErrorCode`` в свой статус - снимаем сами."""
    receiver = Wired()
    seen: list[dict[str, Any]] = []

    class _Controller:
        def _process_media_status(self, data: dict[str, Any]) -> None:
            seen.append(data)

    controller = _Controller()
    receiver._catch_media_error(controller)
    controller._process_media_status(
        {"status": [{"playerState": "IDLE", "idleReason": "ERROR", "detailedErrorCode": 905}]}
    )

    assert receiver._error_code == 905
    assert len(seen) == 1, "разбор чужой библиотеки продолжается как ни в чём не бывало"


def test_a_load_failure_without_a_code_does_not_erase_the_one_already_taken() -> None:
    """Отказ загрузки без кода - тот же отказ вторым ответом: терять снятый код не на чем.

    Мёртвая сессия без кода, наоборот, причину сбрасывает: это новый отказ.
    """
    receiver = Wired()

    class _Controller:
        def _process_media_status(self, data: dict[str, Any]) -> None:
            return None

        def _process_load_failed(self, data: dict[str, Any]) -> None:
            return None

    controller = _Controller()
    receiver._catch_media_error(controller)
    controller._process_load_failed({"detailedErrorCode": 905})
    assert receiver._error_code == 905

    controller._process_load_failed({})
    assert receiver._error_code == 905, "отказ без кода не стирает уже снятый"

    controller._process_media_status({"status": [{"playerState": "IDLE", "idleReason": "ERROR"}]})
    assert receiver._error_code is None, "новая мёртвая сессия без кода - новая причина"
