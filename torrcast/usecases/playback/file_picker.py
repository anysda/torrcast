"""Какой файл раздачи играть: серия сериала, крупнейший файл фильма или ручка ``--file N``.

Зовёт его команда показа (:func:`torrcast.usecases.cast_command._cmd_play`) и стенд отбора.
"""

from __future__ import annotations

from collections.abc import Callable

import torrcast.usecases.playback._show_state as _state
from torrcast.domain._name_data.data_3 import VIDEO_EXT
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.playback._numbered import _Numbered
from torrcast.usecases.select.plan import Plan


def _default_file(plan: Plan, release: Release, files: list[TorrFile]) -> TorrFile:
    """Фильму — самый крупный видеофайл, сериалу — файл нужной серии."""
    return plan.series.choose(release, files) if plan.series else _state.pick_video_file(files)


def file_picker(args: _Numbered) -> Callable[[Plan, Release, list[TorrFile]], TorrFile]:
    """``--file N`` — отладочная ручка: взять N-й видеофайл раздачи."""
    if args.file is None:
        return _default_file

    def chosen(_plan: Plan, _release: Release, files: list[TorrFile]) -> TorrFile:
        ordered = sorted(files, key=lambda f: f.index)
        videos = [f for f in ordered if f.name.lower().endswith(VIDEO_EXT)]
        if not 1 <= (args.file or 0) <= len(videos):
            raise NotFoundError(f"видеофайлов в раздаче {len(videos)}, номера {args.file} нет")
        return videos[(args.file or 1) - 1]

    return chosen
