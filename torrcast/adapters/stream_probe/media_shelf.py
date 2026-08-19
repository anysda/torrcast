"""Паспорт медиа на полке: версия формата, место записи, чтение и запись.

Зовёт её щуп паспорта (:func:`probe`), и только он."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Final

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.stream_probe.opt_str import _opt_str
from torrcast.adapters.stream_probe.shelf import _touch, _trim
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.warm_open import PROBE_KEPT

#: Версия формата паспорта на полке (:func:`_read_media`). Растёт, когда в паспорт
#: добавляется поле, от которого зависит РЕШЕНИЕ показа: старая запись такого поля не
#: несёт, и молчание в ней неотличимо от честного ответа. ``2`` - формат кадра и профиль,
#: ``3`` - кривая яркости (:attr:`Media.hdr`), ``4`` - развёртка (:attr:`Media.interlaced`).
_MEDIA_VERSION: Final = 4


def _media_cache(source_url: str) -> Path:
    """Где лежит снятый паспорт этого файла (:func:`probe`).

    Ключ тот же, что у карты опорных кадров (:func:`_keys_cache`), и по той же причине:
    в URL потока лежат hash раздачи и номер файла, то есть ровно то, что определяет
    содержимое. Меняться паспорту негде: длительность, дорожки и кодек - это сам файл.
    """
    return (
        state_path().parent / "probe" / f"{hashlib.sha1(source_url.encode()).hexdigest()[:16]}.json"
    )


def _read_media(cache: Path) -> Media | None:
    """Паспорт с полки; ``None`` - полки нет, запись битая или снята прежней версией.

    ⚠️ Версия проверяется, и это не бюрократия. Паспорта прежних версий не несут формата
    кадра, то есть про десятибитный H.264 молчат ровно так же, как молчал старый ffprobe:
    прими мы такой паспорт за правду - и показ снова уехал бы копией на приёмник, который
    её не декодирует (:func:`recodes_whole`). Цена отказа - один ffprobe на файл, один
    раз; цена доверия - вечная петля на экране.
    """
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        saved = json.loads(cache.read_text("utf-8"))
        if int(saved.get("v") or 0) < _MEDIA_VERSION:
            return None
        media = Media(
            duration=float(saved["duration"]),
            tracks=tuple(AudioTrack(**track) for track in saved["tracks"]),
            video=_opt_str(saved.get("video")),
            profile=_opt_str(saved.get("profile")),
            pix_fmt=_opt_str(saved.get("pix_fmt")),
            color_trc=_opt_str(saved.get("color_trc")),
            field_order=_opt_str(saved.get("field_order")),
            height=int(saved.get("height") or 0),
            width=int(saved.get("width") or 0),
            video_bps=float(saved.get("video_bps") or 0.0),
        )
        _touch(cache)  # полка живёт по времени обращения (:func:`_trim`)
        return media
    return None


def _keep_media(cache: Path, media: Media, kept: int = PROBE_KEPT) -> None:
    """Положить паспорт в кэш. Осечка записи молча игнорируется: кэш - ускорение, а не
    источник правды, и показ обязан идти и без него.

    ``kept`` - сколько паспортов остаётся на полке. Умолчание боевое (512); называет своё
    только стенд, которому нужен потолок в несколько файлов, а не в пять сотен."""
    if media.duration <= 0 or not media.tracks:
        # Паспорт без длительности и дорожек - это не паспорт, а недочитанный заголовок:
        # такой в кэш класть нельзя, иначе осечка одного запуска станет вечной.
        return
    with contextlib.suppress(OSError, TypeError, ValueError):
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(f".{os.getpid()}-{threading.get_ident()}.tmp")
        tmp.write_text(
            json.dumps(
                {
                    "v": _MEDIA_VERSION,
                    "duration": media.duration,
                    "tracks": [asdict(track) for track in media.tracks],
                    "video": media.video,
                    "profile": media.profile,
                    "pix_fmt": media.pix_fmt,
                    "color_trc": media.color_trc,
                    "field_order": media.field_order,
                    "height": media.height,
                    "width": media.width,
                    "video_bps": media.video_bps,
                }
            ),
            encoding="utf-8",
        )
        tmp.replace(cache)
    _trim(cache.parent, kept)
