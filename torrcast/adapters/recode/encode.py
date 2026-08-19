"""Чем перекодировать кусок: тот же кадр, тот же кодек, ниже битрейт.

Спрашивают его заход кодировщика, ужатие на месте и сплошной перекод."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from torrcast.adapters.ffmpeg.encode_args import encode_args
from torrcast.adapters.recode.encode_settings import (
    _KEY_SLACK,
    MAXRATE_GAIN,
    TONEMAP,
    VBV_SECONDS,
)
from torrcast.adapters.recode.fit_mbit import fit_mbit
from torrcast.adapters.recode.level_for import level_for
from torrcast.adapters.recode.scale_to import scale_to

if TYPE_CHECKING:
    from torrcast.adapters.stream_pack.grid import Grid


@dataclass(frozen=True, slots=True)
class Encode:
    """Чем перекодировать тяжёлый кусок: то же разрешение, тот же кодек, ниже битрейт."""

    preset: str = "veryfast"
    #: Целевой битрейт, Мбит/с. Умолчание и его замер -
    #: :attr:`torrcast.domain.config.Config.recode_mbit`.
    mbit: float = 9.0
    #: Ступень кадра ИСТОЧНИКА (:attr:`torrcast.domain.media.Media.frame`); ``0`` - не спрашивали.
    frame: int = 0
    #: Потолок кадра НАРУЖУ - самый большой кадр, который берёт приёмник
    #: (:attr:`torrcast.domain.profile.Profile.recode_frame`); ``0`` - потолка нет.
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

        Оба потолка, запас и пол цели живут в :func:`fit_mbit`: считает её и фоновый
        кодировщик, и ужатие на месте, и разойдись они хоть в одном знаке, в проекте
        появился бы третий источник правды о потолке.
        """
        return replace(self, mbit=fit_mbit(self.mbit, span, cap, cap_mbit))

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
        chain = [scale_to(self.ceiling)] if self.scaled else []
        if self.hdr:
            chain.append(TONEMAP)
        return ",".join(chain)

    def args(self, grid: Grid, slot: int, until: int) -> list[str]:
        """Аргументы видео для
        :func:`torrcast.adapters.stream_pack.ffmpeg_pack_command.ffmpeg_pack_command`.

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
