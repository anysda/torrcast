"""Адрес отдельного файла со звуком для того файла, который играем прямо сейчас.

Спрашивают его юнит показа и сборка прогрева следующей серии.
"""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.voice_beside import voice_beside
from torrcast.ports.torrent_engine import TorrentEngine


def voice_source(torrserver: TorrentEngine, torrent_hash: str, entry: Entry) -> str:
    """Откуда показ возьмёт звук; пусто - из самого видеофайла.

    Файл ищется у раздачи каждый раз заново и тем же правилом, каким его нашёл отбор
    (:func:`torrcast.domain.voice_beside.voice_beside`). Это и есть весь смысл: у сериала
    файл звука свой на каждую серию, а запись состояния помнит только, что звук лежит
    отдельно (:attr:`torrcast.domain._playing._Playing.voiced_apart`).

    Правило вдруг не нашло файла - показ идёт звуком из видео, как шёл бы без всего
    этого. Врать тут нечем: второго входа просто не будет.
    """
    if not entry.voiced_apart:
        return ""
    files = torrserver.files(torrent_hash)
    video = next((item for item in files if item.index == entry.file_idx), None)
    found = None if video is None else voice_beside(video, files)
    return "" if found is None else torrserver.stream_url(torrent_hash, found.index)
