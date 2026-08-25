"""Правило «звук лежит отдельным файлом рядом с видео»: какой файл относится к какому."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, TypeVar

from torrcast.domain._name_data.data_3 import VIDEO_EXT
from torrcast.domain.file_like import FileLike

#: Расширения, которыми раздачи подписывают отдельную звуковую дорожку. ``.mka`` первым
#: не случайно: студии озвучки кладут дорожку именно так, и в аниме это типовая раскладка.
_AUDIO_EXT: Final = (".mka", ".ac3", ".dts", ".eac3", ".flac", ".aac", ".m4a", ".mp3", ".opus")

#: Правило отвечает файлом ТОГО ЖЕ вида, что ему дали: зовущему нужен его номер в раздаче.
_File = TypeVar("_File", bound=FileLike)


def voice_beside(video: _File, files: Sequence[_File]) -> _File | None:
    """Файл со звуком, относящийся именно к этому видео; ``None`` - такого нет.

    Правил ровно два, и оба отвечают «не знаю» там, где не уверены: подмешать чужую
    дорожку хуже, чем не подмешать никакой.

    * **то же имя** - у файла звука та же основа имени, что у видео, а лежать он может
      где угодно (студии кладут дорожки в отдельную папку). Это правило и держит
      сериалы: у каждой серии свой файл звука, и связывает их имя, а не порядок;
    * **единственный** - и файл звука, и видеофайл в раздаче по одному. Так раздают
      фильм: видео плюс дорожка, и спутать не с чем.

    Больше одного файла звука при несовпадающих именах - это «не знаю»: язык у соседних
    дорожек разный (замер по спискам файлов: рядом с русской лежат чужие, у одной
    раздачи первый по номеру файл звука английский), и брать первый попавшийся значит
    включить зрителю чужой язык молча.

    Опознание ЯЗЫКА сюда не относится вовсе и по имени не делается: в аниме имя файла
    звука не называет язык никогда (194 файла из 194), и отвечает на это ``ffprobe``
    самого файла.
    """
    sound = [item for item in files if item.name.lower().endswith(_AUDIO_EXT)]
    if not sound:
        return None
    want = _stem(video.name)
    same = [item for item in sound if _stem(item.name) == want]
    if len(same) == 1:
        return same[0]
    videos = [item for item in files if item.name.lower().endswith(VIDEO_EXT)]
    return sound[0] if len(sound) == 1 and len(videos) == 1 else None


def _stem(path: str) -> str:
    """Основа имени файла: без пути и без расширения, в нижнем регистре."""
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0].casefold()
