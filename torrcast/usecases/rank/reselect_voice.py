"""Выбор дорожки заново, когда тот же показ переходит на другой файл."""

from __future__ import annotations

from dataclasses import dataclass, replace

from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.usecases.rank.pick_voice import pick_voice


@dataclass(slots=True)
class _Automatic:
    """Узкий довод общего выбора: человек новую дорожку сейчас не называл."""

    voice: int | str | None = None


def reselect_voice(entry: Entry, media: Media) -> Entry:
    """Вернуть запись с номером дорожки именно этого файла.

    ``audio`` - координата внутри одного файла, поэтому пережить переход может только
    именованная память ``voice``. Паспорт уже прочитан для нового файла, отдельного
    похода к ffprobe этот выбор не делает.
    """
    if not media.tracks:
        return entry
    audio, _voice = pick_voice(media, _Automatic(), entry.voice)
    return replace(entry, audio=audio)
