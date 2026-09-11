#!/usr/bin/env python3
"""Бот без Telegram, теми же вызовами: проходит ли ``cast stop`` посреди чужого долгого подъёма.

Первая команда занимает исполнитель бота долгим подъёмом, вторая - ``cast stop``. Подъём
поддельный и слушает отказ на своих поворотах, как настоящий
(:func:`torrcast.usecases.playback.refuse_called_off.refuse_called_off`); ``stop_command``
подменён, чтобы щуп не гасил ничей настоящий показ. Сеть Telegram не нужна: сообщения идут
в :meth:`tgbot.bot.Bot.dispatch` прямо, ответы бота копятся в поддельном ``Api``.

Меряется дерево, названное первым аргументом (приёмка передаёт свой ``--repo``), без него -
своё. Какое дерево взято на деле, щуп печатает сам: замер без этого не воспроизвести.

    .venv/bin/python scripts/botstop_probe.py [ДЕРЕВО]

Вывод - одна строка JSON: ``busy`` (бот ответил «занято»), ``stop`` (остановка позвана),
``ended`` (через сколько секунд после «cast stop» подъём кончился; ``null`` - шёл дальше),
``tree`` (откуда взят ``tgbot``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if len(sys.argv) > 1:
    sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

import json
import threading
import time
from collections.abc import Sequence
from typing import Any, cast

import tgbot.bot as bot_module
from tgbot.bot import Bot
from tgbot.config import Config
from tgbot.i18n import i18n
from tgbot.transport import _TelegramResult
from torrcast.ports.abandon import slot as abandon_slot

#: Сколько поддельный подъём держит исполнитель, если его не отменили, секунды.
RAISE_S = 20.0


class _Api:
    """Telegram в объёме того, что бот зовёт на две команды: всё сказанное копится."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(
        self, _chat: Any, text: str, _buttons: Any = None, reply_to_message_id: Any = None
    ) -> int:
        self.sent.append(text)
        return 1

    def post(
        self, _chat: Any, text: str, _buttons: Any = None, reply_to_message_id: Any = None
    ) -> _TelegramResult:
        self.sent.append(text)
        return _TelegramResult(200, "", {"message_id": 1})

    def delete(self, _chat: Any, _message_id: Any) -> object:
        return object()

    def answer(self, _callback_id: Any, _text: str = "") -> object:
        return object()

    def edit(self, _chat: Any, _message_id: Any, _text: str, _buttons: Any = None) -> object:
        return object()

    def updates(self, _offset: Any) -> list[Any]:
        return []


def main() -> int:
    stopped = threading.Event()
    try:
        import tgbot.stop_now as stop_now
    except ImportError:  # дерево до разведения стопа: команда шла тем же исполнителем
        pass
    else:
        # подмена на время щупа: у старого дерева нет параметра ``stop`` у бота
        setattr(stop_now, "stop_command", stopped.set)  # noqa: B010
    raised = threading.Event()
    ended: list[float] = []

    def launch(argv: Sequence[str] | None) -> int:
        raised.set()
        began = time.monotonic()
        while time.monotonic() - began < RAISE_S:
            if abandon_slot.abandoned():
                ended.append(time.monotonic())
                return 130
            time.sleep(0.05)
        return 0

    api = _Api()
    bot = Bot(
        Config("token", "-100"),
        api=cast(Any, api),
        command=launch,
        assemble=lambda: None,
        title=lambda: "",
    )
    worker = threading.Thread(target=bot.run_one, daemon=True)
    worker.start()
    bot.dispatch({"message": {"chat": {"id": -100}, "message_id": 5, "text": "cast интерстеллар"}})
    raised.wait(5.0)
    time.sleep(0.5)
    asked = time.monotonic()
    bot.dispatch({"message": {"chat": {"id": -100}, "message_id": 6, "text": "cast stop"}})
    stopped.wait(5.0)
    worker.join(RAISE_S + 5.0)
    said = {
        "busy": i18n("busy") in api.sent,
        "stop": stopped.is_set(),
        "ended": round(ended[0] - asked, 2) if ended else None,
        "tree": str(Path(bot_module.__file__).resolve().parent.parent),
    }
    print(json.dumps(said, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
