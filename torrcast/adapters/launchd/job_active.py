"""Отвечает, идёт ли показ прямо сейчас; спрашивают ``cast status`` и щупы."""

from __future__ import annotations

from torrcast.adapters.launchd._launchd_call import LaunchdCall, _domain, _launchd, _running
from torrcast.domain.unit_naming import _UNIT_NAME


def job_active(unit: str = _UNIT_NAME, *, call: LaunchdCall = _launchd) -> bool:
    """Идёт ли показ прямо сейчас.

    Отсутствие задания - обычный ответ ``launchctl print`` (код 113), а не авария.

    ``call`` - чем звать launchd; боевое умолчание одно, и меняет его только стенд.
    """
    done = call("launchctl", "print", f"{_domain()}/{unit}")
    return done.returncode == 0 and _running(done.stdout)
