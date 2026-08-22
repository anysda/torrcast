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
from torrcast.usecases.playback.heavy_profile import HeavyProfile
from torrcast.usecases.playback.media_grid import MediaGrid


def _recoder(
    source: str,
    audio: int,
    grid: MediaGrid,
    spare: Path,
    config: Config,
    video_mbit: float = 0.0,
    profile: Profile = CAUTIOUS,
    video_mbit_estimated: bool = False,
) -> SpotRecoder | None:
    """Кодировщик тяжёлых кусков или ``None``, если он не нужен и не может помочь.

    Отказ остался ровно один и он честный: перекодирование выключено настройкой. Всё
    остальное — не отказ, а профиль тяжести похуже, и о том, какой именно взят, говорится
    вслух (:func:`_profile`).

    🔴 TC-693. Прежде отказов было три, и два из них стоили показа целиком. Сетка не по
    опорным кадрам считалась причиной не браться вовсе — а дальше тяжёлый кусок не
    ужимался, а ПРОПАДАЛ: выкладке было нечем его ужать, и она честно пропускала каждый
    (живой замер: 39 упакованных кусков из 39, ни кадра зрителю, три прогона из трёх).
    Резать ровную сетку копией и правда нельзя, но перекодом — можно: кодировщик сам
    ставит опорный кадр на каждой границе (:meth:`torrcast.adapters.recode.encode.Encode.args`),
    и перекодированный кусок ровной сетки самостоятелен. Цена замерена и оказалась не
    ценой: на ровной сетке секунда показа стоит на 3 % ДЕШЕВЛЕ (кусок длиннее, накладные
    те же), стык здоровый, вес влезает в осторожный потолок.
    """
    if not config.recode:
        return None
    # Сколько уедет на ТВ: видеодорожка идёт копией, звук всегда AAC, сверху оверхед
    # mpegts. Паспорт молчит (mp4 без тегов) - поправка наберётся по факту, как раньше.
    delivered = (video_mbit + AUDIO_MBIT) * TS_OVERHEAD if video_mbit > 0 else 0.0
    weights = _profile(source, grid, delivered, video_mbit_estimated)
    return _state.Recoder(
        source=source,
        audio=audio,
        grid=grid,
        spare=spare,
        weights=weights,
        threshold=config.recode_at_mbit,
        # Потолок веса куска - тот же, которым меряет показ: у каждого приёмника свой
        # (:attr:`torrcast.domain.profile.Profile.max_segment_bytes`).
        cap=profile.max_segment_bytes,
        encode=_state.Encode(preset=config.recode_preset, mbit=config.recode_mbit),
        ahead=config.recode_ahead,
        cache_mb=config.recode_cache_mb,
        head_wait=config.recode_head_wait,
        log=lambda text: print(text, flush=True),
    )


def _profile(
    source: str, grid: MediaGrid, delivered: float, video_mbit_estimated: bool
) -> HeavyProfile:
    """Профиль тяжести показа: по карте опорных кадров, а нет карты — ровный по паспорту.

    Профиль по карте считается из уже снятой карты: байты и секунды каждого сегмента
    известны до упаковки, и это ноль запросов к рою. Он знает тяжёлое место в лицо и
    потому даёт кодировщику работать впрок.

    ⚠️ Карта спрашивается ровно там, где она заведомо уже снята, — на сетке ПО ОПОРНЫМ
    КАДРАМ: такой сетки без карты не бывает, значит карта лежит в кэше и стоит ноль
    запросов. На ровной сетке спрашивать её второй раз нельзя: сетку строил тот же
    :func:`torrcast.adapters.stream_pack.grid_for.grid_for`, и ровной она вышла ровно потому,
    что карты не получил, — либо ему её запретила настройка, либо индекс контейнера
    оказался вруном. Второй заход за ней — это те же Range-запросы в рой на старте показа
    и ещё одна дорога, по которой наружу может выйти чужая ошибка.

    Карты нет (ровная сетка) или она без смещений (кэш прошлой версии) — берётся ровный
    профиль (:meth:`torrcast.adapters.recode.weights.Weights.flat`): про каждый кусок известен
    один и тот же средний вес фильма. Тяжёлое место в лицо он не знает и потому объявляет
    тяжёлыми либо все куски, либо ни одного. Это грубо — и это ровно та грубость, которую
    можно себе позволить: она стоит процессора, а прежний отказ стоил показа.

    Какой профиль взят, говорится вслух и числом: молчаливая подмена одного другим — то
    же самое, из-за чего пропажу кусков расследовали живьём.
    """
    weights = _mapped(source, grid, delivered) if grid.on_keys else None
    if weights is not None:
        print(
            f"профиль тяжести: контейнер {weights.container:.1f} Мбит/с, "
            + (
                f"на ТВ уедет {delivered:.1f} Мбит/с "
                f"по {'оценке' if video_mbit_estimated else 'замеру'}"
                if delivered > 0
                else "веса видеодорожки в паспорте нет - поправку наберу по факту"
            ),
            flush=True,
        )
        return weights
    if delivered > 0:
        print(
            f"профиль тяжести ровный: {delivered:.1f} Мбит/с на каждый кусок "
            f"по {'оценке' if video_mbit_estimated else 'замеру'} - "
            "тяжёлое место в лицо не знаю, ужимаю по среднему",
            flush=True,
        )
    else:
        print(
            "профиля тяжести нет: ни карты, ни веса дорожки в паспорте - "
            "тяжёлый кусок ужимаю по факту, когда он окажется на выкладке",
            flush=True,
        )
    return _state.flat_weights(grid.count, delivered)


def _mapped(source: str, grid: MediaGrid, delivered: float) -> HeavyProfile | None:
    """Профиль по карте опорных кадров; ``None`` — карты нет или она без смещений."""
    try:
        keys = _state.film_keys(source)
    except InfraError as exc:
        print(f"карта опорных кадров не снята ({why(exc)})", flush=True)
        return None
    weights: HeavyProfile | None = _state.weights_of(keys, grid, delivered=delivered)
    if weights is None:
        print("карта без смещений - веса кусков по ней не построить", flush=True)
    return weights
