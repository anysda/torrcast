"""Кодировщик тяжёлых кусков: нужен ли он этому показу и с какими порогами.

Зовёт его показ (:func:`_play`) и прогрев следующей серии (:func:`_next_warmer`).
"""

from __future__ import annotations

from pathlib import Path

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import AUDIO_MBIT, TS_OVERHEAD
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.why import why
from torrcast.ports.recode.spot_recoder import SpotRecoder
from torrcast.usecases.playback.media_grid import MediaGrid


def _recoder(
    source: str,
    audio: int,
    grid: MediaGrid,
    spare: Path,
    config: Config,
    video_mbit: float = 0.0,
    profile: Profile = CAUTIOUS,
) -> SpotRecoder | None:
    """Кодировщик тяжёлых кусков или ``None``, если он не нужен и не может помочь.

    Профиль тяжести считается из уже снятой карты опорных кадров: байты и секунды каждого
    сегмента известны до упаковки, и это ноль запросов к рою. Отказ бывает честный —
    выключено настройкой, сетка не по кадрам (тогда границы не совпадут с картой), карта
    снята прошлой версией и смещений не несёт, — и о нём говорится вслух.
    """
    if not config.recode:
        return None
    if not grid.on_keys:
        print("сетка не по опорным кадрам - тяжёлые куски перекодировать не берусь", flush=True)
        return None
    try:
        keys = _state.film_keys(source)
    except InfraError as exc:
        print(f"профиль тяжести не снят ({why(exc)}) - играю как есть", flush=True)
        return None
    # Сколько уедет на ТВ: видеодорожка идёт копией, звук всегда AAC, сверху оверхед
    # mpegts. Паспорт молчит (mp4 без тегов) - поправка наберётся по факту, как раньше.
    delivered = (video_mbit + AUDIO_MBIT) * TS_OVERHEAD if video_mbit > 0 else 0.0
    weights = _state.weights_of(keys, grid, delivered=delivered)
    if weights is None:
        print("карта без смещений - профиль тяжести не построить, играю как есть", flush=True)
        return None
    print(
        f"профиль тяжести: контейнер {weights.container:.1f} Мбит/с, "
        + (
            f"на ТВ уедет {delivered:.1f} (видео {video_mbit:.1f} по паспорту)"
            if delivered > 0
            else "веса видеодорожки в паспорте нет - поправку наберу по факту"
        ),
        flush=True,
    )
    return _state.Recoder(
        source=source,
        audio=audio,
        grid=grid,
        spare=spare,
        weights=weights,
        threshold=config.recode_at_mbit,
        # Потолок веса куска - тот же, которым меряет показ: у каждого приёмника свой
        # (:attr:`torrcast.profile.Profile.max_segment_bytes`).
        cap=profile.max_segment_bytes,
        encode=_state.Encode(preset=config.recode_preset, mbit=config.recode_mbit),
        ahead=config.recode_ahead,
        cache_mb=config.recode_cache_mb,
        head_wait=config.recode_head_wait,
        log=lambda text: print(text, flush=True),
    )
