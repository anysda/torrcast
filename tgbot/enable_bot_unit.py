"""Служба бота: включает её мастер после живой проверки настройки."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Final, TypeAlias

from torrcast.domain.infra_error import InfraError

#: Имя службы; юнит кладёт на диск установщик (``install.sh``, ``setup_bot_unit``), а
#: включает тот, кто настроил Telegram. Имя названо поимённо в двух местах, поэтому
#: живёт здесь одно: разойдись оно - мастер включал бы несуществующую службу и молчал.
BOT_UNIT: Final = "torrcast-bot.service"

#: Чем звать systemd. Боевое умолчание одно (:func:`_systemctl`); стенду довод нужен,
#: чтобы не заводить настоящих юнитов на машине, где идёт проверка.
SystemctlCall: TypeAlias = Callable[..., subprocess.CompletedProcess[str]]


def _systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    """Позвать системный systemctl: юнит бота лежит в ``/etc/systemd/system``.

    Пользовательской области тут нарочно нет, в отличие от юнитов показа: бот обязан
    жить без вошедшего в систему человека и подниматься при загрузке машины.
    """
    return subprocess.run(
        ["systemctl", *args], capture_output=True, text=True, check=False, timeout=60
    )


def enable_bot_unit(unit: str = BOT_UNIT, *, call: SystemctlCall = _systemctl) -> None:
    """Включить службу бота на будущее и поднять её сейчас.

    🔴 Два хода, а не один. ``enable`` без перезапуска оставил бы чат немым до
    перезагрузки; ``start`` без ``enable`` - ровно до первой перезагрузки, после которой
    бота снова нет. Живой отказ 31-08-2026 был вторым родом: настройка сохранена,
    проверочная надпись в чат ушла, а опрашивать Telegram некому.

    Поднятой службе нужен именно ``restart``: ``enable --now`` работающую не трогает
    (тот же трюк расписан у ``run_service`` в ``install.sh``), и бот остался бы ходить
    со старым токеном - а мастер зовут как раз затем, чтобы сменить его.
    """
    for step in ("enable", "restart"):
        done = call(step, unit)
        if done.returncode != 0:
            detail = done.stderr.strip()[:120] or f"systemctl {step}"
            raise InfraError(f"unit {unit} did not start: {detail}")
