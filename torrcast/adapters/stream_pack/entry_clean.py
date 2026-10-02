"""Полка сверок входа: откроет ли вкладка копию с закладки, по файлу и месту.

Устроена как полка замеров начала ленты (:mod:`_origin_shelf`): ключ - URL потока, запись
черновиком и ``replace``, подрезка по времени обращения. Сверку (:func:`opens_clean`, два
прогона ffmpeg) делает прогрев записи, пока человек на главной, а показ - отдельный
процесс - берёт ответ с полки. Замер на «Интерстелларе» 5212 МБ с 5000 с: сверка на
прогретом месте 0.43-0.57 с из пяти секунд от клика до кадра.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.stream_pack._keys_draft import _keys_draft
from torrcast.adapters.stream_pack.opens_clean import opens_clean
from torrcast.adapters.stream_probe.shelf import _touch, _trim

#: Сколько сверок держит полка: столько же, сколько карт, запись весит сотню байт.
ENTRY_KEPT = 256


def _entry_cache(source_url: str) -> Path:
    """Где лежит сверка входа этого файла: имя как у карты, каталог соседний."""
    digest = hashlib.sha1(source_url.encode()).hexdigest()[:16]
    return state_path().parent / "entry" / f"{digest}.json"


def _read_entry(source_url: str, seek: float) -> bool | None:
    """Сверка с полки; ``None`` - нет, битая, чужой файл или другое место.

    Ответ верен только для того места, где сверяли: у x264 с ``open-gop`` один вход
    чистый, а соседний несёт MMCO. Поэтому место сравнивается до миллисекунды.
    """
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError, AttributeError):
        cache = _entry_cache(source_url)
        saved = json.loads(cache.read_text("utf-8"))
        clean = saved["clean"]
        if saved["source"] != source_url or saved["seek"] != round(seek, 3):
            return None
        if not isinstance(clean, bool):
            return None
        _touch(cache)
        return clean
    return None


def _keep_entry(source_url: str, seek: float, clean: bool, kept: int = ENTRY_KEPT) -> None:
    """Положить сверку на полку; осечка записи - не беда, это кэш."""
    cache = _entry_cache(source_url)
    with contextlib.suppress(OSError):
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = _keys_draft(cache)
        try:
            record = {"source": source_url, "seek": round(seek, 3), "clean": clean}
            tmp.write_text(json.dumps(record), "utf-8")
            tmp.replace(cache)
        finally:
            tmp.unlink(missing_ok=True)
    _trim(cache.parent, kept)


def entry_clean(
    source_url: str,
    seek: float,
    check: Callable[[str, float], bool | None] = opens_clean,
) -> bool | None:
    """Откроет ли вкладка копию с ``seek``: с полки, иначе сверкой; ответ ложится на полку.

    ``None`` (не сверили) на полку не ложится: следующий спрос сверит заново.
    """
    shelved = _read_entry(source_url, seek)
    if shelved is not None:
        return shelved
    clean = check(source_url, seek)
    if clean is not None:
        _keep_entry(source_url, seek, clean)
    return clean


__all__ = ["ENTRY_KEPT", "entry_clean"]
