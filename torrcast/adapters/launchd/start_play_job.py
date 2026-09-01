"""Запускает показ заданием launchd; зовёт его команда ``cast``."""

from __future__ import annotations

import os
import plistlib
import sys
from collections.abc import Sequence
from typing import Final

from torrcast.adapters.launchd._job_files import _log_path, _plist_path
from torrcast.adapters.launchd._launchd_call import LaunchdCall, _domain, _launchd
from torrcast.adapters.launchd.stop_play_job import stop_play_job
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.unit_naming import _JOB_KEY_ENV, _PASS_ENV, _UNIT_NAME

#: PATH задания показа. У launchd он голый - ``/usr/bin:/bin:/usr/sbin:/sbin``, и под
#: ``sudo`` у процесса ``cast`` ровно тот же secure_path (замер 02-09-2026 на macOS 26):
#: наследовать ``os.environ["PATH"]`` значило бы оставить задание без ffmpeg, который
#: ставится в ``/usr/local/bin`` (Intel; сюда же ссылку кладёт установщик на кремнии)
#: или ``/opt/homebrew/bin`` (кремний Apple). Поэтому PATH назван явно, как это делает
#: ``write_unit`` в ``install.sh``, а не взят из окружения зовущего.
_JOB_PATH: Final = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def start_play_job(
    key: str,
    unit: str = _UNIT_NAME,
    *,
    call: LaunchdCall = _launchd,
    program: Sequence[str] | None = None,
) -> None:
    """Запустить показ заданием launchd: ``cast`` завершился - показ продолжается,
    журнал бесплатно пишется в файл. Переменные окружения проброшены, иначе задание
    возьмёт прод-пути конфига и состояния вместо dev-овских.

    Задание пишется plist'ом и поднимается ``bootstrap``, а не объявленным устаревшим
    ``submit``: у того нет ни проброса окружения, ни путей журнала. ``RunAtLoad``
    поднимает показ сразу с регистрацией; ключ едет окружением - описания, где его
    держит systemd, у launchd нет (:data:`~torrcast.domain.unit_naming._JOB_KEY_ENV`).
    Журнал стирается перед стартом: строки прошлого показа - не причина молчания нового.

    🔴 Запускается ``-m torrcast.runtime``, то есть композиционный корень, а не пакет
    команд: показу нужны собранные порты. ``program`` - что поднять заданием;
    умолчание - боевой показ, а щупы поднимают свою долгую команду под своей меткой.

    ``call`` - чем звать launchd; боевое умолчание одно и то же у всех команд задания
    (:data:`~torrcast.adapters.launchd._launchd_call.LaunchdCall`). Погашение прошлого
    показа идёт ТЕМ ЖЕ ``call``: гасить и запускать врозь нельзя - иначе стенд видит
    запуск, но не видит, чем погашен прошлый показ, а живой ``launchctl bootout``
    уходит на хозяйскую машину прямо посреди сухого теста.
    """
    stop_play_job(unit, call=call)
    _log_path(unit).unlink(missing_ok=True)
    env = {name: os.environ[name] for name in _PASS_ENV if name in os.environ}
    env["PATH"] = _JOB_PATH
    env[_JOB_KEY_ENV] = key
    command = list(program) if program is not None else [
        sys.executable, "-m", "torrcast.runtime", "--play-key", key,
    ]  # fmt: skip
    _plist_path(unit).write_bytes(
        plistlib.dumps(
            {
                "Label": unit,
                "ProgramArguments": command,
                "RunAtLoad": True,
                "EnvironmentVariables": env,
                "StandardOutPath": str(_log_path(unit)),
                "StandardErrorPath": str(_log_path(unit)),
            },
            sort_keys=False,
        )
    )
    done = call("launchctl", "bootstrap", _domain(), str(_plist_path(unit)))
    if done.returncode != 0:
        detail = done.stderr.strip()[:120] or "launchctl"
        raise InfraError(phrase("launchd.job_did_not_start", job=unit, detail=detail))
