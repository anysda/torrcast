"""Чем перекодировать кусок: тот же кадр, тот же кодек, ниже битрейт.

Спрашивают его заход кодировщика, ужатие на месте и сплошной перекод."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from torrcast.adapters.ffmpeg.encode_args import encode_args
from torrcast.adapters.recode.encode_settings import (
    _KEY_SLACK,
    FIT_FLOOR,
    FIT_SLACK,
    MAXRATE_GAIN,
    TONEMAP,
    VBV_SECONDS,
)
from torrcast.adapters.recode.level_for import level_for
from torrcast.domain.media import AUDIO_MBIT, TS_OVERHEAD

if TYPE_CHECKING:
    from torrcast.adapters._legacy_stream_types import Grid


def _scale_to(frame: int) -> str:
    """Фильтр, ужимающий кадр в габарит ступени лестницы, - и ни пикселя вверх.

    🔴 Габарит, а не одна высота. Прямое ``scale=-2:1080`` судит по высоте, а высота
    ступени не задаёт: скоуп 3840×1600 - это тот же 2160p (:attr:`torrcast.stream.Media.frame`
    считает по 16:9-габариту), и ``-2:1080`` развернул бы его в 2592×1080 - кадр, который
    ШИРЕ 1080p и приёмнику по-прежнему не по зубам. Габарит 1920×1080 с сохранением
    пропорций даёт из него честные 1920×800.

    ``min(iw,…)`` - страховка от увеличения: ``force_original_aspect_ratio=decrease``
    ужимает габарит до пропорций входа, но САМ по себе мелкий вход растянул бы до
    габарита. Нам растягивать нечего: 720p должен остаться 720p.

    ``force_divisible_by=2`` - стороны обязаны быть чётными: у ``yuv420p`` цветность
    вдвое реже яркости, и нечётная сторона кодировщику просто не даётся.
    """
    return (
        f"scale=w=min(iw\\,{frame * 16 // 9}):h=min(ih\\,{frame})"
        ":force_original_aspect_ratio=decrease:force_divisible_by=2"
    )


@dataclass(frozen=True, slots=True)
class Encode:
    """Чем перекодировать тяжёлый кусок: то же разрешение, тот же кодек, ниже битрейт."""

    preset: str = "veryfast"
    #: Целевой битрейт, Мбит/с. Умолчание и его замер - :attr:`torrcast.state.Config.recode_mbit`.
    mbit: float = 9.0
    #: Ступень кадра ИСТОЧНИКА (:attr:`torrcast.stream.Media.frame`); ``0`` - не спрашивали.
    frame: int = 0
    #: Потолок кадра НАРУЖУ - самый большой кадр, который берёт приёмник
    #: (:attr:`torrcast.profile.Profile.recode_frame`); ``0`` - потолка нет.
    #:
    #: Два числа рядом, а не одно готовое, нарочно: перекод обязан знать и что пришло, и
    #: что приёмнику по зубам. Из первого считается, нужен ли скейл вообще, из второго -
    #: во что ужимать, а из их встречи - уровень в потоке (:func:`level_for`).
    ceiling: int = 0
    #: Источник в HDR (PQ или HLG) - картинку надо привести к SDR (:data:`TONEMAP`).
    hdr: bool = False

    @property
    def maxrate(self) -> float:
        """Потолок мгновенного битрейта. Выше цели на 8 % — иначе кап душит движение."""
        return self.mbit * MAXRATE_GAIN

    @property
    def bufsize(self) -> float:
        """Буфер VBV, Мбит: сколько кодеру разрешено копить впрок (:data:`VBV_SECONDS`).

        Считается от :attr:`maxrate`, а не от цели: потолок и есть то, что обещано
        приёмнику, и буфер - единственное, чем это обещание можно нарушить.
        """
        return self.maxrate * VBV_SECONDS

    def fit(self, span: float, cap: float, cap_mbit: float = 0.0) -> Encode:
        """Тот же перекод, но с целью, посчитанной под потолки ПРИЁМНИКА.

        🔴 Единственное место, где цель перекода считается из потолков. Спрашивают его
        двое - фоновый кодировщик (:meth:`Recoder._run`) и ужатие на месте
        (:meth:`torrcast.stream.Feed._shrink`), - и разойдись они хоть в одном знаке, в
        проекте появился бы третий источник правды о потолке.

        Потолков два, и они разной природы. ``cap`` - **вес** куска в байтах
        (:attr:`torrcast.profile.Profile.max_segment_bytes`): сегмент тяжелее его приёмник
        не доигрывает, а выбрасывает буфер и качает заново. Сколько мегабит в секунду в
        такой вес влезает, зависит от ДЛИНЫ куска, а она у сетки по опорным кадрам
        доходит до 20 секунд: прибитые 9 Мбит/с кладут в такой кусок 23 МБ при потолке 16,
        и не влезает сам перекод, а не только копия (TC-483). ``cap_mbit`` - **битрейт**,
        который приёмник тянет (:attr:`torrcast.profile.Profile.recode_at_mbit`): выше него
        он спотыкается независимо от веса. Ноль - про этот потолок не спрашивали.

        Считается от того, что получит приёмник, а не от голого видео: сверху лягут наш
        AAC (:data:`torrcast.stream.AUDIO_MBIT`) и оверхед mpegts
        (:data:`torrcast.stream.TS_OVERHEAD`), а сам кодер вправе идти до
        :attr:`maxrate`. Отсюда же и запас :data:`FIT_SLACK`.

        Вверх не перекодируем: цель не может стать выше той, что уже стоит
        (:attr:`mbit`), - потолок умеет только опустить её.
        """

        def room(delivered: float) -> float:
            """Сколько Мбит/с ВИДЕО просить, чтобы сегмент не вышел за ``delivered``."""
            return max(0.0, (delivered / TS_OVERHEAD - AUDIO_MBIT) / MAXRATE_GAIN)

        want = room(cap * 8 / (max(span, 0.1) * 1e6))
        if cap_mbit > 0:
            want = min(want, room(cap_mbit))
        return replace(self, mbit=max(FIT_FLOOR, min(self.mbit, want * FIT_SLACK)))

    @property
    def scaled(self) -> bool:
        """Ужимаем ли кадр: источник крупнее того, что берёт приёмник."""
        return self.ceiling > 0 and self.frame > self.ceiling

    @property
    def out_frame(self) -> int:
        """Ступень кадра, который уедет НАРУЖУ; ``0`` - кадра не спрашивали."""
        return self.ceiling if self.scaled else self.frame

    @property
    def mark(self) -> str:
        """Чем этот перекод отличается от прежних в имени каталога прогретого; пусто - ничем.

        Ключ прогретого собирает всё, от чего зависит СОДЕРЖИМОЕ куска
        (:func:`torrcast.usecases.warm.warm_key`), и ужатый кадр с тонемапом - ровно оно. Пустая
        строка на неужатом SDR не косметика: она оставляет ключи прежних прогонов теми же,
        какими они были, и прогретое прошлого показа находится.
        """
        return (f":{self.out_frame}p" if self.scaled else "") + (":sdr" if self.hdr else "")

    @property
    def filters(self) -> str:
        """Цепочка ``-vf``; пусто - фильтровать нечего, поток идёт как шёл.

        Порядок в цепочке замерен, а не выбран на глаз (TC-223): скейл стоит ПЕРВЫМ,
        тонемап работает уже на 1080p. Тонемап - самый дорогой фильтр в тракте, и цена
        его линейна по пикселям, так что вчетверо меньший кадр стоит вчетверо дешевле.
        """
        chain = [_scale_to(self.ceiling)] if self.scaled else []
        if self.hdr:
            chain.append(TONEMAP)
        return ",".join(chain)

    def args(self, grid: Grid, slot: int, until: int) -> list[str]:
        """Аргументы видео для :func:`torrcast.stream.ffmpeg_pack_command`.

        Принудительные опорные кадры стоят на границах сетки — без них сегментный муксер
        с ``-break_non_keyframes 0`` ждал бы ближайший кадр кодировщика и резал бы куда
        попало, а обещание ``EXT-X-INDEPENDENT-SEGMENTS`` в манифесте стало бы враньём.

        Профиль здесь НЕ задаётся, и это не забывчивость. ``-profile:v`` у x264 - потолок,
        а не пол: он умеет только запретить лишнее, а включить ничего не может. Замер:
        строка параметров, которую x264 пишет в поток, с ``-profile:v high`` и без него
        совпадает символ в символ - на ``ultrafast`` обе дают ``cabac=0 8x8dct=0`` и в SPS
        ``profile_idc=66`` (Constrained Baseline), на ``veryfast`` обе дают ``cabac=1`` и
        ``profile_idc=100`` (High). То есть флаг в коде читался как обещание High, а на
        самом быстром пресете наружу всё равно уходил Baseline. Потолок тут и не нужен:
        десятибитный источник обрезает ``-pix_fmt yuv420p`` (без него тот же вход даёт
        High 10), выше High подняться не на чем. Настоящий High на ``ultrafast`` стоит
        ``-x264-params cabac=1:8x8dct=1``, и это уже не переименование, а другой поток:
        замер на 1080p дал +24 % ко времени перекода (1.85 с → 2.30 с на 30 с материала)
        ровно на том пресете, который берут, когда времени и так нет.

        🔴 Уровень считается от КАДРА, который уедет наружу (:func:`level_for`), а не
        пишется строкой. Прибитые «4.1» на 2160p обещали декодеру кадр вчетверо меньше
        того, что лежит в потоке (TC-224).

        🔴 Буфер VBV считается от потолка и держится коротким (:data:`VBV_SECONDS`), а не
        берётся «две секунды цели». Длинный буфер - это разрешение копить неистраченное
        на тихих секундах и высыпать накопленное в первый же настоящий кадр: средний
        битрейт куска остаётся честным, а одна секунда внутри него улетает вдвое-втрое
        выше потолка приёмника. Ровно так умирал показ С НАЧАЛА фильма: заставка перед
        первым кадром почти ничего не стоит, кодер копил на ней весь буфер, и на 1.9-й
        секунде первого куска наружу уходило 25 Мбит за секунду при обещанных 9.7.

        🔴 Метки цвета ставятся ровно тогда, когда цвет и правда преобразован
        (:data:`TONEMAP`). Метка без преобразования - переклеенный ярлык: HDR-кадр,
        помеченный BT.709, приёмник разворачивает не той кривой. А SDR-источнику метки
        не нужны вовсе: его цвет мы не трогаем, и врать нам не о чем.
        """
        keys = (grid.start(k) - _KEY_SLACK for k in range(slot, min(until + 2, grid.count)))
        return encode_args(
            preset=self.preset,
            mbit=self.mbit,
            maxrate=self.maxrate,
            bufsize=self.bufsize,
            level=level_for(self.out_frame),
            keyframes=keys,
            filters=self.filters,
            hdr=self.hdr,
        )
