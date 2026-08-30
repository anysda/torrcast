"""Соединение с pychromecast и свежий статус приёмника - и ничего кроме.

Наследует его разговор приёмника; на стенде подменяют именно эти ручки."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.chromecast.cast.hush_cosmetic_noise import hush_cosmetic_noise
from torrcast.adapters.chromecast.cast.receiver_state import _State
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.why import why


class _Link(_State):
    """Живое соединение с приёмником: поднять, спросить статус, назвать причину отказа."""

    def _status(self) -> Any:
        """Свежий статус приёмника. ``update_status`` обязателен: без него pychromecast
        отдаёт последний присланный статус, и позиция замирает навсегда — сторож считает,
        что показ стоит, окно сегментов не чистится и tmpfs растёт до конца фильма.
        """
        controller = self._device().media_controller
        self._stale = False
        # ⚠️ На закрытом ресивере update_status ПЕРЕЗАПУСКАЕТ пустой Default Media
        # Receiver - «вышел в Home, а каст открылся снова». Поэтому
        # чужой app_id проверяем раньше и статус не трогаем.
        if getattr(self._cast.status, "app_id", None) != self.MEDIA_APP:
            return controller.status
        try:
            controller.update_status()
        except Exception:
            # 🔴 Отказ тут не шум, и глотать его нельзя: это ЕДИНСТВЕННЫЙ признак, по
            # которому «зритель убрал показ» отличается от «источник умер» на первом же
            # тёмном опросе. Сокет 8009 падает вместе с приложением, свежего статуса
            # взять неоткуда, и всё, что ниже вернётся, - прошлый ответ: экран числится
            # НАШИМ, а значит показ числится незакрытым (:func:`_viewer_closed`).
            # Замер на приставке 30-08-2026: жест пультом, ``NotConnected``, и волю
            # человека приёмник назвал лишь следующим, переподключившимся опросом (TC-880).
            self._stale = True
        return controller.status

    def _why(self) -> str:
        status = self._status()
        state = status.player_state or phrase("chromecast_talk.no_status")
        said = f"{state}/{status.idle_reason}" if status.idle_reason else str(state)
        if self._error_code is not None:
            return said + phrase("chromecast_talk.with_code", code=self._error_code)
        return said

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

    def _no_link(self, exc: BaseException) -> InfraError:
        """Чем отвечать на несостоявшийся коннект: отсутствием ТВ или отказом загрузки.

        🔴 Выбор тут не косметический, он решает судьбу показа. Оба класса - авария
        инфраструктуры, но :class:`StartRefusedError` показ ПОДНИМАЕТ лестницей
        воскрешения (:func:`torrcast.usecases.playback._play._play` ловит именно его), а
        голый :class:`InfraError` проходит мимо этого разбора и хоронит юнит показа кодом
        возврата 2 при живом ТВ.

        ПЕРВЫЙ коннект за показ не удался - приёмника нет в сети: показывать некому и
        нечем, и висеть перед пустым экраном весь бюджет старта незачем. Это
        :class:`InfraError`, как и было.

        ПЕРЕподключение (:attr:`_linked`) - другое событие: в этом показе приёмник уже
        отвечал, значит он есть, а легшее соединение лечится следующей попыткой с чистым
        сокетом. Замер на приставке 30-08-2026 (TC-916), 2 прогона из 2: сеть рвётся через
        0.35 с ПОСЛЕ ушедшего LOAD. ``NotConnected`` при этом не приходит вовсе, и
        :func:`torrcast.adapters.chromecast.cast.while_connecting._while_connecting` сюда
        не достаёт - он стоит на самой команде, а легло соединение ПОД ней. Показ
        досиживает :data:`_Settings.STUCK_SECONDS`, уходит в чистое приложение
        (:meth:`torrcast.adapters.chromecast.cast.receiver_talk._Talk._restart_app`, он же
        гасит :attr:`_cast`) - и умирал ровно здесь, на ``device.wait``: чёрный экран,
        код 2, и ни одной записи ``play/revive`` в ленте.

        ⚠️ Своих повторов тут нет и быть не должно. Считает их лестница воскрешения, и
        потолок ей ставят :data:`torrcast.domain.revive_settings.REVIVE_TRIES` (три
        попытки на обрыв) и :data:`torrcast.domain.revive_settings.REVIVE_LIMIT` (900 с
        темноты). Ещё один счётчик рядом с ними означал бы произведение потолков, а не
        потолок.
        """
        if not self._linked:
            return InfraError(
                phrase("chromecast_talk.tv_rejected_cast", address=self.address, reason=why(exc))
            )
        return StartRefusedError(
            phrase("chromecast_talk.tv_no_reconnect_answer", address=self.address, reason=why(exc))
        )

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
                raise self._no_link(exc) from exc
            # Приёмник ответил - дальше его отсутствием отказ коннекта уже не объясняется
            # (:meth:`_no_link`). Ставится ДО разбора ответов: связь состоялась здесь.
            self._linked = True
            self._catch_media_error(device.media_controller)
            self._cast = device
        return self._cast
