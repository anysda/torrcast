"""Отказ пульту показу во вкладке: перемотка и переключатель ей не по силам.

🔴 TC-1210. Приёмник-вкладка (:class:`torrcast.adapters.browser.browser_receiver.
BrowserReceiver`) не умеет ``seek``/``pause``/``resume`` - раньше команда молча терялась
в канале (:func:`torrcast.usecases.choice._ctl._ctl`), а щёлк на пульте ложно
защёлкивался «взятым» (:meth:`hass.motion.Motion.commanded`). Вкладку узнаём по её же
ящику - он снимается перед КАЖДЫМ новым показом
(:func:`torrcast.usecases.playback._launch._launch`), так что брошенный ящик мёртвой
вкладки не солжёт про живой каст на ТВ.

⚠️ Ящик кладёт не только вкладка. Показ, поднятый прямо на приёмнике-ТВ, тоже заводит
ящик - чтобы вкладка, подключившаяся к нему карточкой, знала что открыть
(:func:`torrcast.adapters.browser.write_web_box.write_web_box`, поле ``tv``). Голого
``url`` тут мало: он верно отличает вкладку от пустого экрана, но НЕ отличает вкладку
от показа на ТВ, ящик которого известил бы о себе тем же полем. Пульт настоящего ТВ
кладёт ``tv: true`` - и это единственное поле, честно говорящее «этим показом правда
играет вкладка, а не ТВ». Поля нет (старый ящик, до этого поля) - по умолчанию ``False``,
то есть «вкладка», как было до появления показа прямо на ТВ.
"""

from __future__ import annotations

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.domain.config import Config
from torrcast.ports.journal.slot import journal
from torrcast.usecases.playback.hls_root import hls_root


def remote_refused(config: Config, command: str) -> bool:
    """Показ во вкладке этой командой не управляется - отказать и сказать почему в ленту."""
    box = read_web_box(hls_root(config.hls_dir))
    if not box.get("url") or box.get("tv", False):
        return False
    journal().emit("bridge", "remote_refused", command=command, why="no_remote")
    return True
