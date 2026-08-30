"""Запускает показ отдельным transient-юнитом; зовёт его команда ``cast``."""

from __future__ import annotations

import os
import sys

from torrcast.adapters.systemd._systemd_call import SystemdCall, _systemd
from torrcast.adapters.systemd.stop_play_unit import stop_play_unit
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.unit_naming import _PASS_ENV, _UNIT_NAME, _UNIT_TAG


def start_play_unit(key: str, unit: str = _UNIT_NAME, *, call: SystemdCall = _systemd) -> None:
    """Запустить показ в transient-юните: ``cast`` завершился — показ продолжается,
    логи бесплатно в journald. Переменные окружения проброшены, иначе юнит возьмёт
    прод-пути конфига и состояния вместо dev-овских.

    🔴 Запускается ``-m torrcast.runtime``, то есть композиционный корень, а не пакет
    команд: показу нужны собранные порты. Строка проверяется живьём
    (``tests/runtime/test___main__.py``) - пока пакет команд был одним модулем, тут
    стояло ``-m torrcast.cli``, и после разворота в пакет каст падал строкой «No module
    named torrcast.cli.__main__», которую ни один сухой тест не видел.

    ``call`` - чем звать systemd; боевое умолчание одно и то же у всех команд юнита
    (:data:`~torrcast.adapters.systemd._systemd_call.SystemdCall`). Погашение прошлого
    показа идёт ТЕМ ЖЕ ``call``: гасить и запускать врозь нельзя - иначе стенд видит
    запуск, но не видит, чем погашен прошлый показ, а живой ``systemctl stop`` уходит
    на хозяйскую машину прямо посреди сухого теста.
    """
    stop_play_unit(unit, call=call)
    env = [f"--setenv={n}={os.environ[n]}" for n in _PASS_ENV if n in os.environ]
    done = call(
        "systemd-run", f"--unit={unit}", "--collect", "--quiet",
        f"--description={_UNIT_TAG}{key}", *env,
        sys.executable, "-m", "torrcast.runtime", "--play-key", key,
    )  # fmt: skip
    if done.returncode != 0:
        detail = done.stderr.strip()[:120] or "systemd-run"
        raise InfraError(phrase("systemd.unit_did_not_start", unit=unit, detail=detail))
