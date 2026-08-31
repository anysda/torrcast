"""Честная строка про звук, когда русской дорожки в файле не оказалось; зовёт запуск показа."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.media import Media
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.rank.spoken import spoken


def sound_note(
    media: Media,
    audio: int,
    pool: list[Release],
    release: Release | None = None,
    files: Sequence[TorrFile] = (),
    *,
    native: bool = False,
) -> str:
    """Честная строка про звук, когда русской дорожки в файле не оказалось; иначе пусто.

    Решение продукта по аниме: субтитров не делаем — значит японский тайтл без
    перевода останется японским, и показ обязан сказать это ДО картинки, а не оставить
    человека выяснять на слух. Показ при этом играет: решает он сам, наше дело —
    предупредить честно.

    Строки три, и разница между ними не косметическая:

    * перевод в каталоге есть, но в этом релизе его не оказалось — строка называет и
      запасной ход: выбрать раздачу руками;
    * 🔴 TC-191: перевод в каталоге есть, но только ОТДЕЛЬНЫМ ФАЙЛОМ
      (:attr:`~torrcast.domain.release.Release.external_dub`, «[RUS(ext)]») — тогда выбирать
      руками нечего: играть звук из соседнего файла показ не умеет, и честнее сказать
      это прямо, чем отправить человека по кругу за тем же японским;
    * перевода нет вообще ни у кого в выдаче — «только японский звук, перевода в
      каталоге нет», и делать тут больше нечего.

    Чей звук играет, читается из дорожки (:func:`spoken`), а не додумывается: у
    французского фильма без перевода японского звука взяться неоткуда.
    """
    if not media.tracks or any(t.is_russian for t in media.tracks):
        return ""
    track = media.tracks[audio] if audio < len(media.tracks) else media.tracks[0]
    if not track.named:
        if native:
            return ""
        # Раздача язык дорожки не назвала (тег ``und``). Единственная косвенная улика -
        # имя раздачи: русский маркер в нём (:attr:`Release.dubbed`) - повод СКАЗАТЬ про
        # русскую, назвав источник, а не молча подставить её (и не выдать за неё). Улики
        # нет - язык так и остаётся неизвестным, и об этом честная строка.
        if release is not None and release.dubbed:
            return phrase("rank.no_language_tag_dub_by_name")
        return phrase("rank.language_unknown")
    lang = spoken(track)
    if any(r is not release and r.dubbed and r.seeders > 0 for r in pool):
        return phrase("rank.only_lang_other_release", lang=lang)
    if _russian_audio_file(files) or any(r.external_dub and r.seeders > 0 for r in pool):
        return phrase("rank.only_lang_separate_file", lang=lang)
    return phrase("rank.only_lang_no_dub", lang=lang)


_AUDIO_FILE_EXT: Final = frozenset(
    {".aac", ".ac3", ".dts", ".eac3", ".flac", ".m4a", ".mka", ".mp3", ".ogg", ".opus", ".wav"}
)
_RU_FILE_RE: Final = re.compile(
    r"(?:^|[ ._\[(+-])(?:rus|russian|рус(?:ский|ская)?)(?:$|[ ._\])+-])", re.I
)


def _russian_audio_file(files: Sequence[TorrFile]) -> bool:
    """Есть ли в раздаче отдельный файл звука, прямо названный русским."""
    return any(
        Path(file.name).suffix.casefold() in _AUDIO_FILE_EXT and _RU_FILE_RE.search(file.base)
        for file in files
    )
