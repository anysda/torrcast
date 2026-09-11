"""``cast stop`` в чате проходит всегда, даже когда исполнитель занят долгим подъёмом.

Зовёт его бот (:class:`tgbot.bot.Bot`) на ``cast stop`` и на кнопку ⏹.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import suppress

from tgbot.telegram_choice_environment import TelegramChoiceEnvironment
from tgbot.telegram_control import TelegramControl
from torrcast.ports.abandon.slot import install as install_abandon
from torrcast.runtime.stop_command import stop_command


class StopNow:
    """Остановка, которой не нужен свободный исполнитель.

    🔴 Исполнитель у бота один, и прежде ``cast stop`` вставал к нему в ту же очередь, что и
    показы: пока шёл чужой долгий подъём, на остановку бот отвечал «Предыдущий запрос cast
    ещё выполняется», а кнопка ⏹ не делала ничего (прод 11-09-2026, три команды подряд).
    Свободен исполнитель - остановка идёт к нему обычным путём. Занят - здесь же, в потоке
    опроса, и тремя делами разом: отказ от подъёма ставится фактом, который подъём читает
    на своих поворотах (:mod:`torrcast.ports.abandon.slot`), ждущий ответа выбор снимается,
    а идущий показ гасится тем же вызовом, что и у ``cast stop``, отдельным потоком.
    """

    def __init__(
        self,
        enqueue: Callable[[list[str]], bool],
        choice: TelegramChoiceEnvironment,
        control: TelegramControl,
        stop: Callable[[], object] | None = None,
    ) -> None:
        self._enqueue = enqueue
        self._choice = choice
        self._control = control
        self._stop = stop or stop_command
        self._asked = threading.Event()
        # Про отказ человека знает только бот: назначается это при его сборке, как у моста.
        install_abandon(self._asked.is_set)

    def __call__(self) -> None:
        """Остановить: через исполнителя, если он свободен, иначе на месте."""
        if self._enqueue(["stop"]):
            return
        self._asked.set()
        self._choice.drop()
        threading.Thread(target=self._put_out, daemon=True, name="telegram-stop").start()

    def forget(self) -> None:
        """Новая команда принята: отказ был от ПРОШЛОГО подъёма, а не от неё."""
        self._asked.clear()

    def _put_out(self) -> None:
        with suppress(Exception):
            self._stop()
        self._control.clean()
