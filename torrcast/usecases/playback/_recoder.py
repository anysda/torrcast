"""Кодировщик тяжёлых кусков: нужен ли он этому показу и с какими порогами.

Зовёт его показ (:func:`_play`) и прогрев следующей серии (:func:`_next_warmer`).
"""

from __future__ import annotations

from pathlib import Path

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.config import Config
from torrcast.domain.media import AUDIO_MBIT, TS_OVERHEAD
from torrcast.domain.profile import CAUTIOUS, Profile
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
    voice: str = "",
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
    weights = _profile(grid, delivered, video_mbit_estimated)
    return _state.Recoder(
        source=source,
        audio=audio,
        voice=voice,
        grid=grid,
        spare=spare,
        weights=weights,
        threshold=config.recode_at_mbit,
        # Потолок веса куска - тот же, которым меряет показ: у каждого приёмника свой
        # (:attr:`torrcast.domain.profile.Profile.max_segment_bytes`).
        cap=profile.max_segment_bytes,
        # Куски кодировщика лежат рядом с кусками показа и зовутся так же: контейнер у
        # них обязан быть один, иначе готовый перекод для выкладки не существует.
        container=profile.segment_container,
        encode=_state.Encode(preset=config.recode_preset, mbit=config.recode_mbit),
        ahead=config.recode_ahead,
        cache_mb=config.recode_cache_mb,
        head_wait=config.recode_head_wait,
        log=lambda text: print(text, flush=True),
    )


def _profile(grid: MediaGrid, delivered: float, video_mbit_estimated: bool) -> HeavyProfile:
    """Профиль тяжести показа: по карте, которую принесла сетка, а нет карты — ровный.

    Профиль по карте считается из уже снятой карты: байты и секунды каждого сегмента
    известны до упаковки, и это ноль запросов к рою. Он знает тяжёлое место в лицо и
    потому даёт кодировщику работать впрок.

    🔴 Карта берётся у САМОЙ СЕТКИ (:attr:`torrcast.adapters.stream_pack.grid.Grid.keys`), а не у
    полки вторым заходом, и спрашивается она независимо от того, стоят ли границы на
    опорных кадрах. Прежде тут стояло правило «нет кадров - нет и карты», и объяснялось
    оно так: ровной сетка выходит ровно потому, что карты не получила. Правило было
    верным ровно до тех пор, пока у ровной сетки не появился второй повод рождаться -
    карта СНЯТАЯ, но отвергнутая как сетка
    (:func:`torrcast.adapters.stream_pack.grid_for.grid_for`): её кадры нарисованы, резать по
    ним нечем, а байты честные.

    🔴 Цена молчаливой потери профиля замерена живьём, парной мерой 3 на 3 на приставке
    («Матрица» 1999, паспорт без веса видеодорожки). Ровная сетка без профиля: все 41
    кусок ушли через ужатие на месте, упаковка на это время замирает
    (:func:`torrcast.adapters.recode.yield_to_shrink._yield_to_shrink`), снабжение падает ниже
    реального времени, указатель приёмника идёт 0.40-0.44x и откатывается назад на
    433-953 с. Сетка по кадрам на том же файле - 0.85-0.86x и ни одного отката. ⚠️ Наш
    собственный счётчик подгрузов при этом объявлял победу (11-12 против 0-1): куски он
    считает отданные, а не показанные, и на ровной сетке он потерь НЕ самодостаточен.

    Карты нет вовсе или она без смещений (кэш прошлой версии) — берётся ровный профиль
    (:meth:`torrcast.adapters.recode.weights.Weights.flat`): про каждый кусок известен
    один и тот же средний вес фильма. Тяжёлое место в лицо он не знает и потому объявляет
    тяжёлыми либо все куски, либо ни одного. Это грубо — и это ровно та грубость, которую
    можно себе позволить: она стоит процессора, а прежний отказ стоил показа.

    Какой профиль взят, говорится вслух и числом: молчаливая подмена одного другим — то
    же самое, из-за чего пропажу кусков расследовали живьём.
    """
    weights = _mapped(grid, delivered)
    if weights is not None:
        print(
            f"профиль тяжести: контейнер {weights.container:.1f} Мбит/с, "
            + (
                f"на ТВ уедет {delivered:.1f} Мбит/с "
                f"по {'оценке' if video_mbit_estimated else 'замеру'}"
                if delivered > 0
                else "веса видеодорожки в паспорте нет - поправку наберу по факту"
            )
            + ("" if grid.on_keys else " (карта не сетка, но вес по ней честный)"),
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


def _mapped(grid: MediaGrid, delivered: float) -> HeavyProfile | None:
    """Профиль по карте самой сетки; ``None`` — карты нет или она без смещений."""
    if grid.keys is None:
        return None
    weights: HeavyProfile | None = _state.weights_of(grid.keys, grid, delivered=delivered)
    if weights is None:
        print("карта без смещений - веса кусков по ней не построить", flush=True)
    return weights
