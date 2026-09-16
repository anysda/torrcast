"""Пульт Telegram и договор его одноразовых команд."""

from pathlib import Path
from typing import cast

import pytest

from tests.test_telegram_menu import _Api
from tgbot.telegram_api import TelegramApi
from tgbot.telegram_control import VOL_STEP, TelegramControl, _TelegramError
from tgbot.transport import _TelegramResult


def test_stop_is_an_application_command_and_never_a_tv_power_command(tmp_path: Path) -> None:
    api = _Api()
    control = TelegramControl(cast(TelegramApi, api), "-100", tmp_path / "control")

    control.show("Пульт")
    assert control.command("control:stop") == "stop"

    buttons = cast(list[list[dict[str, str]]], api.sent[0][2])
    callbacks = [button["callback_data"] for row in buttons for button in row]
    labels = [button["text"] for row in buttons for button in row]
    assert "⏪" in labels and "⏩" in labels
    assert all("30" not in label for label in labels)
    assert "control:stop" in callbacks
    assert not (tmp_path / "control").exists()
    assert all("power" not in callback.casefold() for callback in callbacks)


def test_volume_keeps_the_small_cinemacast_step(tmp_path: Path) -> None:
    control = TelegramControl(cast(TelegramApi, _Api()), "-100", tmp_path / "control")

    assert VOL_STEP == 0.02
    assert control.command("control:volume 0.02") == "volume 0.02"
    assert (tmp_path / "control").read_text("utf-8") == "volume 0.02"


def test_a_refused_remote_rises_with_its_status_instead_of_a_silent_zero(
    tmp_path: Path,
) -> None:
    """Отказ Telegram не прячется за нулевым номером: у него есть имя и статус."""

    class Refused(_Api):
        def __init__(self, result: _TelegramResult) -> None:
            super().__init__()
            self.result = result

        def post(self, *_args: object, **_kwargs: object) -> _TelegramResult:
            return self.result

    dead_token = TelegramControl(
        cast(TelegramApi, Refused(_TelegramResult(401, "Unauthorized"))),
        "-100",
        tmp_path / "control",
    )
    with pytest.raises(_TelegramError, match="401"):
        dead_token.show("Пульт")

    network = TelegramControl(
        cast(TelegramApi, Refused(_TelegramResult(0, "Timeout"))),
        "-100",
        tmp_path / "control",
    )
    with pytest.raises(_TelegramError) as refusal:
        network.show("Пульт")
    assert "Timeout" in str(refusal.value)
    assert "401" not in str(refusal.value)


def test_a_found_cover_rides_the_same_message_as_the_remote(tmp_path: Path) -> None:
    """Обложка и кнопки едут одной посылкой, а не картинкой и пультом по отдельности."""
    api = _Api()
    control = TelegramControl(
        cast(TelegramApi, api),
        "-100",
        tmp_path / "control",
        poster=lambda: b"\xff\xd8jpeg",
    )

    control.show("Дюна (2021)")

    assert api.sent == []
    chat, body, caption, buttons = api.photos[0]
    assert (chat, body, caption) == ("-100", b"\xff\xd8jpeg", "Дюна (2021)")
    assert buttons == TelegramControl.buttons()
    assert len(api.photos) == 1


def test_a_missing_cover_still_leaves_the_remote_standing(tmp_path: Path) -> None:
    """Обложки нет - пульт остаётся прежним текстовым, с теми же кнопками."""
    api = _Api()
    control = TelegramControl(
        cast(TelegramApi, api), "-100", tmp_path / "control", poster=lambda: None
    )

    control.show("Дюна (2021)")

    assert api.photos == []
    assert api.sent == [("-100", "Дюна (2021)", TelegramControl.buttons())]


def test_a_refused_photo_falls_back_to_the_text_remote(tmp_path: Path) -> None:
    """Картинку Telegram не взял - человек теряет её, а не кнопки."""

    class NoPhoto(_Api):
        def photo(self, *_args: object, **_kwargs: object) -> _TelegramResult:
            return _TelegramResult(400, "PHOTO_INVALID_DIMENSIONS")

    api = NoPhoto()
    control = TelegramControl(
        cast(TelegramApi, api), "-100", tmp_path / "control", poster=lambda: b"\xff\xd8broken"
    )

    control.show("Дюна (2021)")

    assert api.sent == [("-100", "Дюна (2021)", TelegramControl.buttons())]


def test_a_cover_that_arrives_late_replaces_the_text_remote_once(tmp_path: Path) -> None:
    """Доехавшая обложка одевает висящий пульт один раз, а не плодит вторую карточку."""
    api = _Api()
    arrived: list[bytes | None] = [None, b"\xff\xd8jpeg", b"\xff\xd8jpeg"]
    control = TelegramControl(
        cast(TelegramApi, api), "-100", tmp_path / "control", poster=lambda: arrived.pop(0)
    )

    control.show("Дюна (2021)")
    control.show("Дюна (2021)")
    control.show("Дюна (2021) пауза")

    assert len(api.sent) == 1
    assert len(api.photos) == 1
    assert api.deleted == [42]
    assert api.captions == [("-100", 77, "Дюна (2021) пауза", TelegramControl.buttons())]
