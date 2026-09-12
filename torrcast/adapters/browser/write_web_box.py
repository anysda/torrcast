"""Кладёт задание вкладке: что играть, с какого места и каким ключом подписывать позицию.

Зовёт его :class:`torrcast.adapters.browser.browser_receiver.BrowserReceiver` из
:meth:`~torrcast.adapters.browser.browser_receiver.BrowserReceiver.play`, когда приёмник -
сама вкладка, и композиционный корень (:mod:`torrcast.usecases.playback._play`, через
:data:`torrcast.usecases.playback._show_state.publish_box`) на любом другом приёмнике - без
этого второго зова вкладка не узнавала про показ, начатый прямо на ТВ (TC-1224).
"""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser._write_json import _write_json
from torrcast.adapters.browser.web_box_path import web_box_path


def write_web_box(
    out: Path,
    url: str,
    title: str,
    at: float,
    key: str,
    profile: str = "",
    container: str = "",
    tv: bool = False,
) -> None:
    """Записать задание: ``url``, ``title``, место старта ``at`` и ключ сеанса ``key``.

    Ключ вкладка обязана вернуть с каждой позицией
    (:mod:`torrcast.adapters.browser.write_web_position`): им отличают текущий сеанс от
    чужой вкладки и от эха прошлого показа. ``profile`` (ключ профиля приёмника) и
    ``container`` - то, чем показ упакован: с ними «На ТВ» зовёт ТВ тем же LOAD, что и
    прямой показ на ТВ (:mod:`web.to_tv`). ``tv`` - истинный приёмник этого запуска
    (:data:`torrcast.domain.config.Config.receiver` не ``browser``): вкладка, подключившаяся
    к уже идущему показу на ТВ, должна заглушить себя сразу же (:mod:`web.box`), а не ждать
    отдельного слова каста (:mod:`web.tv_session`), которого тут не будет вовсе.
    """
    task = {"url": url, "title": title, "at": at, "key": key}
    _write_json(web_box_path(out), {**task, "profile": profile, "container": container, "tv": tv})
