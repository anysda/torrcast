"""Выбор дорожки заново, когда тот же показ переходит на другой файл."""

from __future__ import annotations

from dataclasses import dataclass, replace

from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.domain.studios_named import studios_named
from torrcast.usecases.rank.pick_voice import pick_voice


@dataclass(slots=True)
class _Automatic:
    """Узкий довод общего выбора: человек новую дорожку сейчас не называл."""

    voice: int | str | None = None


def reselect_voice(entry: Entry, media: Media) -> Entry:
    """Вернуть запись с номером дорожки именно этого файла.

    ``audio`` - координата внутри одного файла, поэтому пережить переход может только
    именованная память ``voice``. Паспорт уже прочитан для нового файла, отдельного
    похода к ffprobe этот выбор не делает. Судят его те же признак языка картины и студии
    раздачи, что и первый запуск (:mod:`torrcast.usecases.cast_command._entry_of`). Они
    лежат в записи: без них голая ``rus`` пака не узнаётся по студии, а своя дорожка
    картины проигрывает переозвучке.
    """
    if not media.tracks:
        return entry
    studios = studios_named(entry.studios)
    audio, _voice = pick_voice(media, _Automatic(), entry.voice, entry.native, studios)
    return replace(entry, audio=audio)
