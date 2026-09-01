"""Пульт следует за снимком показа, а не за тем, кто запустил команду."""

from pathlib import Path
from typing import cast

from tgbot.playback_observer import PlaybackObserver
from tgbot.telegram_api import TelegramApi
from tgbot.telegram_control import TelegramControl


class _Api:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.edited: list[tuple[int, str, object]] = []
        self.deleted: list[int] = []

    def send(self, _chat: str, text: str, _buttons: object = None) -> int:
        message_id = 40 + len(self.sent)
        self.sent.append((message_id, text))
        return message_id

    def edit(self, _chat: str, message_id: int, text: str, buttons: object = None) -> object:
        self.edited.append((message_id, text, buttons))
        return object()

    def delete(self, _chat: str, message_id: int) -> object:
        self.deleted.append(message_id)
        return object()


def test_observer_keeps_one_control_message_across_episode_and_stop(tmp_path: Path) -> None:
    api = _Api()
    titles = iter(["Домохозяйки (2004) s1e17", "Домохозяйки (2004) s1e18", ""])
    control = TelegramControl(cast(TelegramApi, api), "-100", tmp_path / "control")
    observer = PlaybackObserver(control, lambda: next(titles))

    observer.sync()
    observer.sync()
    observer.sync()

    assert api.sent == [(40, "Домохозяйки (2004) s1e17")]
    assert api.edited[0][:2] == (40, "Домохозяйки (2004) s1e18")
    assert api.edited[0][2] == control.buttons(), "кнопки пережили смену серии"
    assert api.deleted == [40]


def test_failed_deletion_disarms_the_old_control(tmp_path: Path) -> None:
    class Refused(_Api):
        def delete(self, _chat: str, message_id: int) -> object:
            self.deleted.append(message_id)
            raise RuntimeError("forbidden")

    api = Refused()
    titles = iter(["Мумия (1999)", ""])
    observer = PlaybackObserver(
        TelegramControl(cast(TelegramApi, api), "-100", tmp_path / "control"),
        lambda: next(titles),
    )

    observer.sync()
    observer.sync()

    assert api.edited == [(40, "Nothing is playing.", None)]


def test_restart_reuses_and_cleans_the_remembered_control(tmp_path: Path) -> None:
    api = _Api()
    path = tmp_path / "control"
    first = TelegramControl(cast(TelegramApi, api), "-100", path)
    first.show("Мумия (1999)")

    PlaybackObserver(
        TelegramControl(cast(TelegramApi, api), "-100", path), lambda: ""
    ).sync()

    assert api.sent == [(40, "Мумия (1999)")]
    assert api.deleted == [40]
    assert not path.with_suffix(".message").exists()
