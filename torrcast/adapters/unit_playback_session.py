"""Сеанс показа снаружи: живой юнит, запись состояния, служба раздач и адрес потока.
Через него смотрят на показ сценарии ``cast stop`` и ``cast status``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from typing import Any

from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.torrent_hash import _torrent_hash


class UnitPlaybackSession:
    """Реализация порта сеанса поверх systemd, состояния и TorrServer.

    Всё внешнее приходит зависимостями конструктора: так сценарий не знает ни про
    systemd, ни про службу раздач, а подмена на стенде остаётся одной строкой сборки.

    Прочитанную запись сеанс помнит: снимок отдаёт сценарию ровно то, что тому нужно
    словами, а запас в кэше спрашивается по той же записи, из которой снимок и сделан.
    """

    def __init__(
        self,
        *,
        configuration: Callable[[], Any],
        state: Callable[[], Any],
        active: Callable[[], bool],
        unit_key: Callable[[], str],
        stop_unit: Callable[[], None],
        release_torrents: Callable[[Any, Sequence[str]], list[str]],
        cache_reserve: Callable[[Any, Any], str],
        stream_address: Callable[[Any], str],
    ) -> None:
        self._configuration = configuration
        self._state = state
        self._active = active
        self._unit_key = unit_key
        self._stop_unit = stop_unit
        self._release_torrents = release_torrents
        self._cache_reserve = cache_reserve
        self._stream_address = stream_address
        self._entries: dict[str, Any] = {}

    def active(self) -> bool:
        return bool(self._active())

    def key(self) -> str:
        """Ключ показа берётся у ЖИВОГО юнита: у мёртвого описания уже не узнать."""
        return str(self._unit_key())

    def stop(self) -> None:
        self._stop_unit()

    def snapshot(self, key: str = "") -> PlaybackSnapshot | None:
        """Запись играющего показа: ключ - из ``--description`` юнита, а не «самая свежая».

        Рядом мог писать другой ход — тогда свежайшая запись не та, что играет.
        """
        state = self._state()
        entry = state.get(key) if key else None
        found = (key, entry) if entry is not None else state.latest()
        if found is None:
            return None
        self._entries[found[0]] = found[1]
        return self._snapshot_of(*found)

    def release(self, torrent_hash: str) -> None:
        """Снести раздачу, пережившую свой юнит; уборка не вправе провалить остановку."""
        with contextlib.suppress(TorrcastError):
            self._release_torrents(self._configuration(), [torrent_hash])

    def cache_reserve(self, snapshot: PlaybackSnapshot) -> str:
        """Запас показа в кэше службы - по той же записи, из которой сделан снимок."""
        entry = self._entries.get(snapshot.key)
        if entry is None:
            return ""
        return self._cache_reserve(self._configuration(), entry)

    def stream_address(self) -> str:
        """Откуда ТВ забирает поток; адреса нет - статус показа это не отменяет."""
        where = "адрес раздачи не определён"
        with contextlib.suppress(TorrcastError):
            where = str(self._stream_address(self._configuration()))
        return where

    def receiver_name(self) -> str:
        return str(self._configuration().receiver)

    @staticmethod
    def _snapshot_of(key: str, entry: Any) -> PlaybackSnapshot:
        return PlaybackSnapshot(
            key=key,
            title=entry.title,
            position=entry.pos,
            duration=entry.dur,
            label=entry.label,
            quality=entry.quality,
            dark_since=entry.dark,
            dark_reason=entry.dark_why,
            warm=entry.warm,
            file_index=entry.file_idx,
            audio_index=entry.audio,
            torrent_hash=_torrent_hash(entry.magnet),
            video_bitrate_mbit=entry.vbps,
            video_bitrate_estimated=entry.vbps_estimated,
            done=entry.done,
        )
