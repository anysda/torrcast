"""Запись показа по выбранной раздаче: дорожка, звук рядом и место в сериале.

Собирают её команда показа (:func:`torrcast.usecases.cast_command._cmd_play._cmd_play`) перед
юнитом и карточка, когда её отбор кончился: голова показа греется заранее ровно по той
записи, которую потом получит юнит (:class:`torrcast.usecases.playback.head_ahead.HeadAhead`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.cast_command._entry_for import _entry_for
from torrcast.usecases.rank.pick_voice import pick_voice
from torrcast.usecases.select._remembered import _remembered
from torrcast.usecases.select._studio_seen import _studio_seen

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.entry import Entry
    from torrcast.domain.watch_state import WatchState
    from torrcast.usecases.select._prep import _Prep
    from torrcast.usecases.select.plan import Plan


def _entry_of(
    state: WatchState,
    found: tuple[str, Entry] | None,
    plan: Plan,
    prep: _Prep,
    args: Args,
) -> tuple[Entry, int]:
    """Запись показа и номер её дорожки.

    Дорожку выбирают у того файла, из которого её и возьмёт показ: у видео, а когда русская
    лежит рядом отдельным файлом (:attr:`_Prep.apart`) - у него. Номер дорожки считается
    ВНУТРИ выбранного файла, и туда же смотрит показ. Студия из памяти картины тоже едет в
    запись: вынужденный дефолт её не переписывает, и знать прежнюю обязан и показ.
    """
    key = plan.picture.key
    audio, voice = pick_voice(
        prep.voiced,
        args,
        _remembered(state, key, found),
        plan.picture.native,
        prep.release.studios,
    )
    seen = _studio_seen(state, key, found)
    entry = _entry_for(plan, prep, prep.release, prep.want, prep.found, audio, voice, seen, args)
    return entry, audio
