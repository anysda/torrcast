"""Проверяет включение службы бота: чем поднимается и что переживает перезагрузку."""

from __future__ import annotations

import subprocess

import pytest

from tgbot.enable_bot_unit import BOT_UNIT, SystemctlCall, enable_bot_unit
from torrcast.domain.infra_error import InfraError


def _answers(seen: list[tuple[str, ...]], code: int = 0) -> SystemctlCall:
    def call(*args: str) -> subprocess.CompletedProcess[str]:
        seen.append(args)
        return subprocess.CompletedProcess(["systemctl", *args], code, "", "Unit not found.")

    return call


def test_the_bot_is_both_switched_on_for_boot_and_started_right_now() -> None:
    """🔴 Одного запуска мало: машину перезагрузят, и бот не вернётся.

    Ровно этим кончилась живая настройка 31-08-2026: мастер сказал «сохранено», в чат
    ушла проверочная надпись, а опрашивать Telegram было некому - службы не существовало.
    Поэтому ход к systemd проверяется целиком: сперва ``enable`` (переживёт
    перезагрузку), потом ``restart`` (поднимет сейчас, а живому отдаст новую настройку).
    """
    seen: list[tuple[str, ...]] = []
    enable_bot_unit(call=_answers(seen))

    assert seen == [("enable", BOT_UNIT), ("restart", BOT_UNIT)], (
        "служба обязана и включиться на будущее, и подняться сейчас"
    )


def test_a_running_bot_is_restarted_so_that_a_fresh_token_takes_effect() -> None:
    """Поднятой службе нужен именно ``restart``: ``enable --now`` её не тронет.

    Мастер зовут и по второму разу - сменить токен или прокси. Стой тут ``start`` - и
    бот продолжил бы ходить в Telegram со СТАРЫМ токеном, показывая ту же немоту, ради
    ухода от которой службу и завели.
    """
    seen: list[tuple[str, ...]] = []
    enable_bot_unit(call=_answers(seen))

    assert seen[-1][0] == "restart", "новая настройка обязана дойти до живого бота"


def test_a_service_that_did_not_come_up_is_told_about_out_loud() -> None:
    """Не поднялась служба - беда словами, а не «сохранено» и тишина в чате."""
    with pytest.raises(InfraError, match=r"unit .* did not start"):
        enable_bot_unit(call=_answers([], code=1))
