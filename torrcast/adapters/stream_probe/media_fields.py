"""Вес видеодорожки и звуковая дорожка из ответа ffprobe - вторая копия этих двух.

Живой разбор паспорта считает их своими (:mod:`torrcast.adapters.ffprobe.parse_media`);
эти остались совместимому фасаду потока и больше никем не зовутся."""

from __future__ import annotations

import contextlib
from typing import Any

from torrcast.adapters.stream_probe.opt_str import _opt_str
from torrcast.domain.audio_track import AudioTrack


def _video_bps(stream: dict[str, Any], duration: float) -> float:
    """Битрейт видеодорожки, бит/с; ``0.0`` — в паспорте его нет.

    Три источника по убыванию надёжности, и все три уже читаются тем же ffprobe:

    * тег ``BPS`` (с языковым суффиксом или без) — его пишет mkvmerge в голову mkv, то
      есть у всех релизов, собранных обычным путём («Моана 2» 14 333 020, «Тачки 3»
      14 096 894);
    * поле ``bit_rate`` потока — его отдаёт mp4/WEB-DL, где тегов mkvmerge нет вовсе;
    * ``NUMBER_OF_BYTES`` на длительность — на случай, когда mkvmerge написал вес
      дорожки, но не её битрейт.

    Не нашлось ничего — ноль, и профиль тяжести честно возвращается к слепой калибровке
    по первым выложенным сегментам (:meth:`torrcast.adapters.recode.weights.Weights.calibrate`).
    """
    raw = stream.get("tags")
    tags: dict[str, Any] = raw if isinstance(raw, dict) else {}
    named = {str(k).upper(): v for k, v in tags.items()}
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
        language=_opt_str(tags.get("language")),
        title=_opt_str(tags.get("title")),
        codec=_opt_str(stream.get("codec_name")),
        channels=int(stream.get("channels") or 0),
    )
