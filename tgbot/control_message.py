"""Память о пульте между запусками процесса показа: номер сообщения и его род."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path


class ControlMessage:
    """Где записан висящий пульт; писать некуда - память молча пуста.

    Род сообщения хранится рядом с номером не для порядка: подпись картинки и текст
    правятся РАЗНЫМИ вызовами Bot API, и забытый род означал бы 400 на каждом тике
    наблюдателя после перезапуска процесса показа
    (:class:`tgbot.telegram_control.TelegramControl`).
    """

    def __init__(self, path: Path | None) -> None:
        self.path = path

    def read(self) -> tuple[int, bool]:
        """Пульт прежнего процесса: его номер и был ли он картинкой."""
        if self.path is None:
            return 0, False
        with suppress(OSError, ValueError):
            kept = self.path.read_text(encoding="ascii").split()
            return int(kept[0]), kept[1:] == ["photo"]
        return 0, False

    def write(self, number: int, *, photo: bool) -> None:
        """Записать пульт, чтобы следующий процесс правил его, а не слал второй."""
        if self.path is None or not number:
            return
        with suppress(OSError):
            self.path.write_text(f"{number} photo" if photo else str(number), encoding="ascii")

    def forget(self) -> None:
        """Забыть убранный пульт: писать про него следующему процессу нечего."""
        if self.path is None:
            return
        self.path.unlink(missing_ok=True)
