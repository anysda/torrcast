"""Достаёт ключ состояния играющего показа из окружения живого задания; зовёт ``cast status``."""

from __future__ import annotations

from torrcast.adapters.launchd._launchd_call import LaunchdCall, _domain, _launchd, _running
from torrcast.domain.unit_naming import _JOB_KEY_ENV, _UNIT_NAME


def job_key(unit: str = _UNIT_NAME, *, call: LaunchdCall = _launchd) -> str:
    """Ключ состояния играющего показа - из окружения живого задания.

    Описания, где systemd держит ключ, у launchd нет, зато ``launchctl print``
    показывает окружение задания, и ключ едет в нём
    (:data:`~torrcast.domain.unit_naming._JOB_KEY_ENV`). Свежайшая запись в state для
    этого не годится: рядом мог писать другой ход, и ``status`` соврал бы.

    🔴 Читается окружение только ЖИВОГО задания: регистрация переживает процесс
    (аналога ``--collect`` нет), и без проверки состояния ``status`` называл бы
    картину, которая уже погасла.

    ``call`` - чем звать launchd; боевое умолчание одно, и меняет его только стенд.
    """
    done = call("launchctl", "print", f"{_domain()}/{unit}")
    if done.returncode != 0 or not _running(done.stdout):
        return ""
    marker = f"{_JOB_KEY_ENV} => "
    for line in done.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(marker):
            return stripped[len(marker) :].strip()
    return ""
