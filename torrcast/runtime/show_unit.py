"""Кем играется показ на этой машине: systemd на Linux, launchd на macOS.

Договор юнита один (:mod:`torrcast.ports.show_unit`), а исполнителей двое, и выбор
между ними делает композиционный корень, а не чей-то импорт. Сделан он тут один раз
для обеих точек подстановки: кто отвечает за портом (:func:`show_unit` зовёт
:mod:`torrcast.runtime.wire`) и кто поднимает юнит (:data:`start_play_unit` зовёт
:mod:`torrcast.runtime.wire_show`). Разведи выбор по местам подстановки - половины
разошлись бы молча: ``status`` спрашивал бы systemd о задании launchd.
"""

from __future__ import annotations

import sys

from torrcast.ports.show_unit.show_unit import ShowUnit

if sys.platform == "darwin":
    from torrcast.adapters.launchd.launchd_show_unit import LaunchdShowUnit as _ShowUnit
    from torrcast.adapters.launchd.start_play_job import start_play_job as start_play_unit
else:
    from torrcast.adapters.systemd.start_play_unit import start_play_unit
    from torrcast.adapters.systemd.transient_show_unit import TransientShowUnit as _ShowUnit

__all__ = ["show_unit", "start_play_unit"]


def show_unit() -> ShowUnit:
    """Юнит показа этой платформы для слота порта."""
    return _ShowUnit()
