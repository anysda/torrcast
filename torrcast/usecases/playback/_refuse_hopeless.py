"""Отказ до юнита записи, у которой на этом приёмнике картинки не будет.

Зовёт его запуск показа (:func:`torrcast.usecases.playback._launch._launch`).
"""

from __future__ import annotations

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.not_found_error import NotFoundError


def _refuse_hopeless(config: Config, entry: Entry) -> None:
    """Отказать ДО юнита, если этой записи на этом приёмнике картинки не видать.

    🔴 Случай ровно один, и он живой (TC-157): кадр 4К приёмник не берёт вовсе - ни в чужом кодеке,
    ни в своём. Замер 09-08-2026 на Q70D: пять заходов LOAD, каждый — ``IDLE/ERROR`` сразу после
    первого сегмента, картинки нет ни разу (:attr:`torrcast.domain.profile.Profile.recode_frame`).

    ⚠️ TC-222 сузил проверку до одного условия, и это не ослабление. Ужать кадр вниз умеет сплошной
    перекод - значит отказывать надо не «большому кадру», а большому кадру БЕЗ перекода: ``recode:
    false`` в настройках. С включённым перекодированием ровно та же запись теперь играется - 2160p
    уезжает на приёмник как 1080p.

    Отбор такие релизы отбраковывает сам (:meth:`Bench._trouble`), но мимо отбора ведут две двери:
    ``--release N`` / ``--file N`` (там человек выбрал сам, и подмен не бывает) и продолжение
    записи, попавшей в состояние через них же. Без этой проверки обе кончались одинаково: 86 с «жду
    телевизор», код 2 и ни слова о причине. Теперь причина печатается за доли секунды, а ffmpeg и
    раздача не поднимаются вовсе.

    Молчим там, где не знаем: кадр ноль — это записи прежних версий, они играются как раньше."""
    profile = _state.detect_profile(config).profile
    if not entry.frame or entry.frame <= profile.recode_frame:
        return
    if config.recode:
        return
    raise NotFoundError(
        phrase(
            "playback.frame_too_big",
            quality=entry.quality or f"{entry.frame}p",
            limit=profile.recode_frame,
        )
    )
