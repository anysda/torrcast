"""Запускает показ отдельным transient-юнитом; зовёт его команда ``cast``."""

from __future__ import annotations

import os
import sys

from torrcast.adapters.systemd._systemd_call import _systemd
from torrcast.adapters.systemd.stop_play_unit import stop_play_unit
from torrcast.domain.infra_error import InfraError
from torrcast.domain.unit_naming import _PASS_ENV, _UNIT_NAME, _UNIT_TAG


def start_play_unit(key: str, unit: str = _UNIT_NAME) -> None:
    """Запустить показ в transient-юните: ``cast`` завершился — показ продолжается,
    логи бесплатно в journald. Переменные окружения проброшены, иначе юнит возьмёт
    прод-пути конфига и состояния вместо dev-овских.

    🔴 Запускается ``-m torrcast.runtime``, то есть композиционный корень, а не пакет
    команд: показу нужны собранные порты. Строка проверяется живьём
    (``tests/runtime/test___main__.py``) - пока пакет команд был одним модулем, тут
    стояло ``-m torrcast.cli``, и после разворота в пакет каст падал строкой «No module
    named torrcast.cli.__main__», которую ни один сухой тест не видел.
    """
    stop_play_unit(unit)
    env = [f"--setenv={n}={os.environ[n]}" for n in _PASS_ENV if n in os.environ]
    done = _systemd(
        "systemd-run", f"--unit={unit}", "--collect", "--quiet",
        f"--description={_UNIT_TAG}{key}", *env,
        sys.executable, "-m", "torrcast.runtime", "--play-key", key,
    )  # fmt: skip
    if done.returncode != 0:
        raise InfraError(f"не запустился юнит {unit}: {done.stderr.strip()[:120] or 'systemd-run'}")
