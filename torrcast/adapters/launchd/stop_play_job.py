"""Гасит задание показа; зовут команды ``cast stop`` и запуск нового показа."""

from __future__ import annotations

from torrcast.adapters.launchd._job_files import _plist_path
from torrcast.adapters.launchd._launchd_call import LaunchdCall, _domain, _launchd
from torrcast.domain.unit_naming import _UNIT_NAME


def stop_play_job(unit: str = _UNIT_NAME, *, call: LaunchdCall = _launchd) -> None:
    """Погасить задание и дождаться смерти процесса: по SIGTERM сторож дописывает
    позицию в state. Отсутствие задания ошибкой не считается.

    ``bootout`` и гасит процесс, и снимает регистрацию: аналога ``--collect`` у launchd
    нет, и оставленная регистрация не пустила бы следующий показ (повторный
    ``bootstrap`` отвечает ошибкой 5). За ней стирается plist: задание транзитное, и
    файл его не должен пережить. Журнал остаётся - ``why()`` отвечает и о погашенном
    показе, как journald у systemd.

    ``call`` - чем звать launchd; боевое умолчание одно, и меняет его только стенд.
    """
    call("launchctl", "bootout", f"{_domain()}/{unit}")
    _plist_path(unit).unlink(missing_ok=True)
