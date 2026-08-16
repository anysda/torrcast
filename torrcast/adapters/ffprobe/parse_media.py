"""Разбирает JSON ffprobe в паспорт медиа; его вызывает адаптер щупа."""

import contextlib
import json
from typing import Any

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _video_bps(stream: dict[str, Any], duration: float) -> float:
    raw = stream.get("tags")
    tags: dict[str, Any] = raw if isinstance(raw, dict) else {}
    named = {str(key).upper(): value for key, value in tags.items()}
    for key, value in named.items():
        if key == "BPS" or key.startswith("BPS-"):
            with contextlib.suppress(TypeError, ValueError):
                found = float(value)
                if found > 0:
                    return found
    with contextlib.suppress(TypeError, ValueError):
        found = float(stream.get("bit_rate") or 0)
        if found > 0:
            return found
    for key, value in named.items():
        if (key == "NUMBER_OF_BYTES" or key.startswith("NUMBER_OF_BYTES-")) and duration > 0:
            with contextlib.suppress(TypeError, ValueError):
                found = float(value) * 8 / duration
                if found > 0:
                    return found
    return 0.0


def _track(index: int, stream: dict[str, Any]) -> AudioTrack:
    raw = stream.get("tags")
    tags: dict[str, Any] = raw if isinstance(raw, dict) else {}
    return AudioTrack(
        index=index,
        language=_optional_string(tags.get("language")),
        title=_optional_string(tags.get("title")),
        codec=_optional_string(stream.get("codec_name")),
        channels=int(stream.get("channels") or 0),
    )


def parse_media(text: str) -> Media:
    """Разобрать stdout ffprobe, сохранив прежние ошибки и приоритет битрейта."""
    try:
        payload: Any = json.loads(text)
    except ValueError as exc:
        raise InfraError("ffprobe вернул не JSON") from exc
    if not isinstance(payload, dict):
        raise InfraError("ffprobe вернул не тот JSON")
    fmt = payload.get("format")
    duration = float((fmt or {}).get("duration") or 0.0) if isinstance(fmt, dict) else 0.0
    raw = payload.get("streams")
    streams = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    video = [item for item in streams if item.get("codec_type") == "video"]
    picture = video[0] if video else {}
    return Media(
        duration=duration,
        tracks=tuple(_track(index, item) for index, item in enumerate(audio)),
        video=_optional_string(picture.get("codec_name")),
        profile=_optional_string(picture.get("profile")),
        pix_fmt=_optional_string(picture.get("pix_fmt")),
        color_trc=_optional_string(picture.get("color_transfer")),
        field_order=_optional_string(picture.get("field_order")),
        height=int(picture.get("height") or 0),
        width=int(picture.get("width") or 0),
        video_bps=_video_bps(picture, duration) if video else 0.0,
    )
