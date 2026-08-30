"""Пульт Telegram и договор его одноразовых команд."""

from pathlib import Path
from typing import cast

from tests.test_telegram_menu import _Api
from tgbot.telegram_api import TelegramApi
from tgbot.telegram_control import VOL_STEP, TelegramControl


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
