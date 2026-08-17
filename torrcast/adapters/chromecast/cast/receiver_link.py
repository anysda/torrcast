"""Соединение с pychromecast и свежий статус приёмника - и ничего кроме.

Наследует его разговор приёмника; на стенде подменяют именно эти ручки."""

from __future__ import annotations

import contextlib
from typing import Any

from torrcast.adapters.chromecast.cast.hush_cosmetic_noise import hush_cosmetic_noise
from torrcast.adapters.chromecast.cast.receiver_state import _State
from torrcast.domain.infra_error import InfraError
from torrcast.domain.why import why


class _Link(_State):
    """Живое соединение с приёмником: поднять, спросить статус, назвать причину отказа."""

    def _status(self) -> Any:
        """Свежий статус приёмника. ``update_status`` обязателен: без него pychromecast
        отдаёт последний присланный статус, и позиция замирает навсегда — сторож считает,
        что показ стоит, окно сегментов не чистится и tmpfs растёт до конца фильма.
        """
        controller = self._device().media_controller
        # ⚠️ На закрытом ресивере update_status ПЕРЕЗАПУСКАЕТ пустой Default Media
        # Receiver - «вышел в Home, а каст открылся снова». Поэтому
        # чужой app_id проверяем раньше и статус не трогаем.
        if getattr(self._cast.status, "app_id", None) != self.MEDIA_APP:
            return controller.status
        with contextlib.suppress(Exception):
            controller.update_status()
        return controller.status

    def _why(self) -> str:
        status = self._status()
        state = status.player_state or "нет статуса"
        said = f"{state}/{status.idle_reason}" if status.idle_reason else str(state)
        return f"{said}, код {self._error_code}" if self._error_code is not None else said

    def _catch_media_error(self, controller: Any) -> None:
        """Сохранить ``detailedErrorCode``, который pychromecast обычно выбрасывает.

        Приёмник называет код ДВУМЯ разными ответами, и оба обязаны быть сняты:
        ``MEDIA_STATUS`` с мёртвой сессией - это показ, умерший на ходу, а
        ``LOAD_FAILED`` - отказ на самой загрузке, то есть отказ повтора после смерти.
        Снимать только первый мало: у показа, который умер и не поднялся, вся причина
        уходит именно во второй ответ, и в журнале остаётся «без кода» при названном коде.

        ⚠️ Ответ без кода два канала обрабатывают ПО-РАЗНОМУ, и это намеренно. Мёртвая
        сессия без кода причину сбрасывает: это новый отказ, и приписывать ему прошлый код
        нельзя. Отказ загрузки без кода не сбрасывает ничего: приёмник называет им тот же
        отказ вторым ответом, и снятый код терять не на чем. Общий ноль ставит только
        новый LOAD (:meth:`_load`).
        """
        original = controller._process_media_status

        def process(data: dict[str, Any]) -> None:
            statuses = data.get("status") or []
            if statuses:
                raw = statuses[0]
                if raw.get("playerState") == "IDLE" and raw.get("idleReason") == "ERROR":
                    code = raw.get("detailedErrorCode")
                    self._error_code = code if isinstance(code, int) else None
            original(data)

        controller._process_media_status = process
        rejected = getattr(controller, "_process_load_failed", None)
        if rejected is None:  # разбора отказа загрузки в этой версии нет - снимать нечего
            return

        def failed(data: dict[str, Any]) -> None:
            code = data.get("detailedErrorCode")
            # Отказ без кода прежнюю причину не стирает: это тот же отказ, названный
            # вторым ответом, и терять уже снятый код на нём нельзя.
            if isinstance(code, int):
                self._error_code = code
            rejected(data)

        controller._process_load_failed = failed

    def _device(self) -> Any:
        if self._cast is None:
            import uuid

            import pychromecast

            hush_cosmetic_noise()  # косметика 8443 на каждом подключении - не наша беда
            try:
                device = pychromecast.get_chromecast_from_host(
                    (self.address, 8009, uuid.UUID(int=0), None, None), timeout=10
                )
                device.wait(timeout=20)
            except Exception as exc:
                raise InfraError(f"ТВ {self.address} не принял каст: {why(exc)}") from exc
            self._catch_media_error(device.media_controller)
            self._cast = device
        return self._cast
